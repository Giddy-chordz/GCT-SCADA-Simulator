import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal
from app.models import Alarm, AnalogTags, DigitalTags, Equipments
from app.scan_cycles import bagfilter_cycle, gct_cycle, vrm_cycle
from app.scan_cycles.sensor_ingestion import sensor_vals
from app.websocket import ws_tags
from app.ai.root_cause import analyze_alarm
from app.ai.shift_report import generate_shift_report
from app.ai.health_score import calculate_health_score

STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        # Sensor ingestion
        asyncio.create_task(sensor_vals(), name="sensor_vals"),

        # Bagfilter cycle
        asyncio.create_task(bagfilter_cycle.running(),    name="bagfilter_running"),
        asyncio.create_task(bagfilter_cycle.alarm(),      name="bagfilter_alarm"),
        asyncio.create_task(bagfilter_cycle.trip_reset(), name="bagfilter_trip_reset"),

        # GCT cycle
        asyncio.create_task(gct_cycle.running(),    name="gct_running"),
        asyncio.create_task(gct_cycle.alarm(),      name="gct_alarm"),
        asyncio.create_task(gct_cycle.trip_reset(), name="gct_trip_reset"),

        # VRM cycle
        asyncio.create_task(vrm_cycle.run_sequence(),    name="vrm_run_sequence"),
        asyncio.create_task(vrm_cycle.alarm(),           name="vrm_alarm"),
        asyncio.create_task(vrm_cycle.trip_reset(),      name="vrm_trip_reset"),
        asyncio.create_task(vrm_cycle.cascade_monitor(), name="vrm_cascade_monitor"),
    ]

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="GCT SCADA Simulator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Global Trip Countdown State
# ============================================

trip_state = {
    "active": False,
    "remaining": 0,
    "reason": "",
    "equipment": "",
    "started_at": None
}

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_hmi():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


# ── Equipment command endpoints ──────────────────────────────────────────────
# Convention:
#   DO tags  (e.g. VRM-MD-010)  are the command outputs — these are what the
#   operator clicks.  Their running feedback is the -XS sibling and fault
#   feedback is -XF.
#   Valve DO tags (GCT-XV-*)    have -ZSO (open) and -ZSC (closed) feedbacks.
#
# start  → assert -XS binary_state = True  (scan cycle sees it → RUNNING)
# stop   → de-assert -XS binary_state = False (scan cycle → STOPPED)
# reset  → de-assert -XF, set equip status STOPPED for the drive and XF tag
# ack    → mark all active alarms acknowledged for the tag and its feedbacks

def _xs_tag(tag_id: str) -> str:
    """Return the running-feedback tag for a DO command tag."""
    return tag_id + "-XS"

def _xf_tag(tag_id: str) -> str:
    """Return the fault-feedback tag for a DO command tag."""
    return tag_id + "-XF"

def _zso_tag(tag_id: str) -> str:
    """Return the open-feedback tag for a valve DO tag."""
    return tag_id + "-ZSO"

def _zsc_tag(tag_id: str) -> str:
    """Return the closed-feedback tag for a valve DO tag."""
    return tag_id + "-ZSC"

def _is_valve(tag_id: str) -> bool:
    return "-XV-" in tag_id

@app.get("/trip-status", tags=["Trips"])
async def get_trip_status():
    """
    Returns the active automatic trip countdown.
    """

    return {
        "active": trip_state["active"],
        "remaining": trip_state["remaining"],
        "reason": trip_state["reason"],
        "equipment": trip_state["equipment"],
        "started_at": trip_state["started_at"]
    }


@app.post("/cmd/vrm-mill/start", tags=["Commands"])
async def cmd_vrm_mill_start():
    """Start VRM mill drive (VRM-MD-010) with all required permissives checked (1d).

    Permissives (all must pass):
      1. Hydraulic pump (VRM-MD-070-XS) running
      2. Hydraulic pressure (VRM-PT-060) ≥ l1_val
      3. Separator (VRM-MD-020-XS) running
      4. Rollers in grinding/lower mode (all ZSD True)
      5. No active trip on VRM group (VRM-XS-001 — no active XF fault)
    """
    db = SessionLocal()
    try:
        # 1. Hydraulic pump running
        hyd_xs = db.query(DigitalTags).filter(DigitalTags.tag_id == "VRM-MD-070-XS").first()
        if not hyd_xs or not hyd_xs.binary_state:
            raise HTTPException(
                status_code=400,
                detail="VRM mill start blocked: hydraulic pump (VRM-MD-070) is not running."
            )

        # 2. Hydraulic pressure above threshold
        pt060 = db.query(AnalogTags).filter(AnalogTags.tag_id == "VRM-PT-060").first()
        if not pt060 or pt060.process_val < pt060.l1_val:
            actual  = round(pt060.process_val, 1) if pt060 else "N/A"
            minimum = pt060.l1_val if pt060 else "N/A"
            raise HTTPException(
                status_code=400,
                detail=f"VRM mill start blocked: hydraulic pressure (VRM-PT-060) is {actual} bar, below minimum {minimum} bar."
            )

        # 3. Separator running
        sep_xs = db.query(DigitalTags).filter(DigitalTags.tag_id == "VRM-MD-020-XS").first()
        if not sep_xs or not sep_xs.binary_state:
            raise HTTPException(
                status_code=400,
                detail="VRM mill start blocked: separator (VRM-MD-020) is not running."
            )

        # 4. All rollers in grinding/lower mode
        for zsd_id in _ROLLER_ZSD_TAGS:
            zsd = db.query(DigitalTags).filter(DigitalTags.tag_id == zsd_id).first()
            if not zsd or not zsd.binary_state:
                raise HTTPException(
                    status_code=400,
                    detail=f"VRM mill start blocked: rollers are not in grinding position ({zsd_id} is not True). Lower rollers first."
                )

        # 5. No active trip / fault on VRM-MD-010-XF
        xf_di = db.query(DigitalTags).filter(DigitalTags.tag_id == "VRM-MD-010-XF").first()
        if xf_di and xf_di.binary_state:
            raise HTTPException(
                status_code=400,
                detail="VRM mill start blocked: active fault on VRM-MD-010-XF. Reset the drive first."
            )

        # All permissives passed — assert running feedback
        xs = db.query(DigitalTags).filter(DigitalTags.tag_id == "VRM-MD-010-XS").first()
        xs_equip = db.query(Equipments).filter(Equipments.tag_id == "VRM-MD-010-XS").first()
        do_equip = db.query(Equipments).filter(Equipments.tag_id == "VRM-MD-010").first()
        if xs:       xs.binary_state = True
        if xs_equip: xs_equip.status = "RUNNING"
        if do_equip:
            do_equip.status = "RUNNING"
            do_equip.manual_override = True

        db.commit()
        return {"ok": True, "tag_id": "VRM-MD-010", "action": "start"}
    finally:
        db.close()


@app.post("/cmd/{tag_id}/start", tags=["Commands"])
async def cmd_start(tag_id: str):
    """Assert running feedback (or open feedback for valves) so the scan cycle
    picks up RUNNING on its next iteration."""
    db = SessionLocal()
    try:
        equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
        if not equip:
            raise HTTPException(status_code=404, detail=f"{tag_id} not found")
        if equip.io_type not in ("DO",):
            raise HTTPException(status_code=400, detail=f"{tag_id} is not a commandable output")

        # ── 1a. Kiln Drive / Barring Gear mutual exclusion ─────────────────
        if tag_id == "KLN-KD-701":
            bg_xs = db.query(DigitalTags).filter(DigitalTags.tag_id == "KLN-BG-702-XS").first()
            if bg_xs and bg_xs.binary_state:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot start kiln main drive (KLN-KD-701): barring gear (KLN-BG-702) is currently running. Stop barring gear first."
                )
        if tag_id == "KLN-BG-702":
            kd_xs = db.query(DigitalTags).filter(DigitalTags.tag_id == "KLN-KD-701-XS").first()
            if kd_xs and kd_xs.binary_state:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot start barring gear (KLN-BG-702): kiln main drive (KLN-KD-701) is currently running. Stop main drive first."
                )

        # ── 2e. Kiln feed requires main drive running ───────────────────────
        if tag_id == "KLN-FEED-703":
            kd_xs = db.query(DigitalTags).filter(DigitalTags.tag_id == "KLN-KD-701-XS").first()
            if not kd_xs or not kd_xs.binary_state:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot start kiln feed (KLN-FEED-703): kiln main drive (KLN-KD-701) is not running. Start main drive first."
                )
        # ────────────────────────────────────────────────────────────────────

        if _is_valve(tag_id):
            # Open the valve: assert ZSO, de-assert ZSC
            zso = db.query(DigitalTags).filter(DigitalTags.tag_id == _zso_tag(tag_id)).first()
            zsc = db.query(DigitalTags).filter(DigitalTags.tag_id == _zsc_tag(tag_id)).first()
            if zso: zso.binary_state = True
            if zsc: zsc.binary_state = False
            equip.status = "RUNNING"
        else:
            # Motor/pump drive: assert XS running feedback
            xs = db.query(DigitalTags).filter(DigitalTags.tag_id == _xs_tag(tag_id)).first()
            xs_equip = db.query(Equipments).filter(Equipments.tag_id == _xs_tag(tag_id)).first()
            if xs:       xs.binary_state = True
            if xs_equip: xs_equip.status = "RUNNING"
            equip.status = "RUNNING"

        # Operator has explicitly started — prevent scan cycle from overriding
        equip.manual_override = True

        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "start"}
    finally:
        db.close()


@app.post("/cmd/{tag_id}/stop", tags=["Commands"])
async def cmd_stop(tag_id: str):
    """De-assert running feedback (or close valve) so the scan cycle picks up
    STOPPED on its next iteration."""
    db = SessionLocal()
    try:
        equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
        if not equip:
            raise HTTPException(status_code=404, detail=f"{tag_id} not found")
        if equip.io_type not in ("DO",):
            raise HTTPException(status_code=400, detail=f"{tag_id} is not a commandable output")

        if _is_valve(tag_id):
            zso = db.query(DigitalTags).filter(DigitalTags.tag_id == _zso_tag(tag_id)).first()
            zsc = db.query(DigitalTags).filter(DigitalTags.tag_id == _zsc_tag(tag_id)).first()
            if zso: zso.binary_state = False
            if zsc: zsc.binary_state = True
            equip.status = "STOPPED"
        else:
            xs = db.query(DigitalTags).filter(DigitalTags.tag_id == _xs_tag(tag_id)).first()
            xs_equip = db.query(Equipments).filter(Equipments.tag_id == _xs_tag(tag_id)).first()
            if xs:       xs.binary_state = False
            if xs_equip: xs_equip.status = "STOPPED"
            equip.status = "STOPPED"

        # Operator has explicitly stopped — prevent scan cycle from overriding
        equip.manual_override = True

        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "stop"}
    finally:
        db.close()


@app.post("/cmd/{tag_id}/reset", tags=["Commands"])
async def cmd_reset(tag_id: str):
    """Clear a TRIPPED/ALARM drive back to STOPPED: de-assert XF fault
    feedback and reset both the command tag and XS/XF equipment statuses."""
    db = SessionLocal()
    try:
        equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
        if not equip:
            raise HTTPException(status_code=404, detail=f"{tag_id} not found")
        if equip.io_type not in ("DO",):
            raise HTTPException(status_code=400, detail=f"{tag_id} is not a commandable output")

        # Reset command tag; clear manual override so the scan cycle resumes control
        equip.status = "STOPPED"
        equip.manual_override = False

        # De-assert XF fault feedback DI and reset its equipment status
        xf_id    = _xf_tag(tag_id)
        xf_di    = db.query(DigitalTags).filter(DigitalTags.tag_id == xf_id).first()
        xf_equip = db.query(Equipments).filter(Equipments.tag_id == xf_id).first()
        if xf_di:    xf_di.binary_state = False
        if xf_equip: xf_equip.status    = "STOPPED"

        # De-assert XS running feedback DI and reset its equipment status
        xs_id    = _xs_tag(tag_id)
        xs_di    = db.query(DigitalTags).filter(DigitalTags.tag_id == xs_id).first()
        xs_equip = db.query(Equipments).filter(Equipments.tag_id == xs_id).first()
        if xs_di:    xs_di.binary_state = False
        if xs_equip: xs_equip.status    = "STOPPED"

        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "reset"}
    finally:
        db.close()


@app.post("/cmd/{tag_id}/ack", tags=["Commands"])
async def cmd_ack(tag_id: str):
    """Acknowledge all active unacknowledged alarms for this tag and its
    running/fault feedback siblings."""
    db = SessionLocal()
    try:
        equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
        if not equip:
            raise HTTPException(status_code=404, detail=f"{tag_id} not found")

        # Collect the tag itself plus any XS/XF siblings
        tags_to_ack = [tag_id, _xs_tag(tag_id), _xf_tag(tag_id)]

        alarms = db.query(Alarm).filter(
            Alarm.tag_id.in_(tags_to_ack),
            Alarm.alarm_active == True,
            Alarm.alarm_acknowledged == False,
        ).all()
        for a in alarms:
            a.alarm_acknowledged = True
        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "ack", "acked": len(alarms)}
    finally:
        db.close()


# ── Grouped interlock command endpoints ─────────────────────────────────────
#
# These replace individual tag control for roller positions and lance valves.
# All interlock checks live here; the individual /cmd/{tag_id}/start|stop
# routes for those tags remain valid for direct DO commands (e.g. test/maint)
# but the grouped endpoints are the operator-facing interface.

_ROLLER_ZSU_TAGS = [f"VRM-LS-{i}-ZSU" for i in range(50, 54)]
_ROLLER_ZSD_TAGS = [f"VRM-LS-{i}-ZSD" for i in range(50, 54)]
_AIR_LANCE_TAGS  = [f"GCT-XV-{i}" for i in range(401, 411)]
_WATER_LANCE_TAGS = [f"GCT-XV-{i}" for i in range(501, 511)]


@app.post("/cmd/vrm-rollers/{action}", tags=["Commands"])
async def cmd_vrm_rollers(action: str):
    """Grouped roller position command.  action must be 'raise' or 'lower'.

    Raise  → all ZSU True,  all ZSD False  (rollers up / maintenance mode)
    Lower  → all ZSD True,  all ZSU False  (rollers down / grinding mode)

    Permissives for both actions (1c):
      • VRM-MD-070-XS (hydraulic pump) must be running
      • VRM-PT-060 process_val must be ≥ l1_val (minimum operating pressure)
    """
    if action not in ("raise", "lower"):
        raise HTTPException(status_code=400, detail="action must be 'raise' or 'lower'")

    db = SessionLocal()
    try:
        # ── 1c. Hydraulic permissive check ──────────────────────────────────
        hyd_xs = db.query(DigitalTags).filter(DigitalTags.tag_id == "VRM-MD-070-XS").first()
        if not hyd_xs or not hyd_xs.binary_state:
            raise HTTPException(
                status_code=400,
                detail="Cannot move rollers: hydraulic pump (VRM-MD-070) is not running."
            )

        pt060 = db.query(AnalogTags).filter(AnalogTags.tag_id == "VRM-PT-060").first()
        if not pt060 or pt060.process_val < pt060.l1_val:
            actual  = round(pt060.process_val, 1) if pt060 else "N/A"
            minimum = pt060.l1_val if pt060 else "N/A"
            raise HTTPException(
                status_code=400,
                detail=f"Cannot move rollers: hydraulic pressure (VRM-PT-060) is {actual} bar, below minimum operating threshold of {minimum} bar."
            )
        # ────────────────────────────────────────────────────────────────────

        if action == "raise":
            zsu_val, zsd_val = True, False
        else:
            zsu_val, zsd_val = False, True

        for zsu_id, zsd_id in zip(_ROLLER_ZSU_TAGS, _ROLLER_ZSD_TAGS):
            zsu = db.query(DigitalTags).filter(DigitalTags.tag_id == zsu_id).first()
            zsd = db.query(DigitalTags).filter(DigitalTags.tag_id == zsd_id).first()
            if zsu: zsu.binary_state = zsu_val
            if zsd: zsd.binary_state = zsd_val

        db.commit()
        return {"ok": True, "action": action, "rollers": "up" if action == "raise" else "down"}
    finally:
        db.close()


@app.post("/cmd/gct-air-lances/{action}", tags=["Commands"])
async def cmd_gct_air_lances(action: str):
    """Grouped air lance command.  action must be 'open' or 'close'.

    Open  → all GCT-XV-401…410 ZSO True,  ZSC False
    Close → all GCT-XV-401…410 ZSO False, ZSC True
    """
    if action not in ("open", "close"):
        raise HTTPException(status_code=400, detail="action must be 'open' or 'close'")

    db = SessionLocal()
    try:
        zso_val = action == "open"
        zsc_val = not zso_val
        new_status = "RUNNING" if zso_val else "STOPPED"

        for tag_id in _AIR_LANCE_TAGS:
            zso = db.query(DigitalTags).filter(DigitalTags.tag_id == f"{tag_id}-ZSO").first()
            zsc = db.query(DigitalTags).filter(DigitalTags.tag_id == f"{tag_id}-ZSC").first()
            do_equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
            if zso: zso.binary_state = zso_val
            if zsc: zsc.binary_state = zsc_val
            if do_equip: do_equip.status = new_status

        db.commit()
        return {"ok": True, "action": action, "air_lances": action + "d"}
    finally:
        db.close()


@app.post("/cmd/gct-water-lances/{action}", tags=["Commands"])
async def cmd_gct_water_lances(action: str):
    """Grouped water lance command.  action must be 'open' or 'close'.

    Open  → all GCT-XV-501…510 ZSO True,  ZSC False
    Close → all GCT-XV-501…510 ZSO False, ZSC True
    """
    if action not in ("open", "close"):
        raise HTTPException(status_code=400, detail="action must be 'open' or 'close'")

    db = SessionLocal()
    try:
        zso_val = action == "open"
        zsc_val = not zso_val
        new_status = "RUNNING" if zso_val else "STOPPED"

        for tag_id in _WATER_LANCE_TAGS:
            zso = db.query(DigitalTags).filter(DigitalTags.tag_id == f"{tag_id}-ZSO").first()
            zsc = db.query(DigitalTags).filter(DigitalTags.tag_id == f"{tag_id}-ZSC").first()
            do_equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
            if zso: zso.binary_state = zso_val
            if zsc: zsc.binary_state = zsc_val
            if do_equip: do_equip.status = new_status

        db.commit()
        return {"ok": True, "action": action, "water_lances": action + "d"}
    finally:
        db.close()


# ── AI endpoints ──────────────────────────────────────────────────────────────

@app.get("/ai/root-cause/{tag_id}", tags=["AI"])
async def ai_root_cause(tag_id: str):
    """Return an IBM Granite-generated root-cause analysis for an active alarm tag."""
    db = SessionLocal()
    try:
        result = await analyze_alarm(tag_id, db)
        return JSONResponse(content=result)
    finally:
        db.close()


@app.get("/ai/shift-report", tags=["AI"])
async def ai_shift_report(hours: int = Query(default=8, ge=1, le=24)):
    """Return an IBM Granite-generated shift handover report covering the last `hours` hours."""
    db = SessionLocal()
    try:
        result = await generate_shift_report(db, hours=hours)
        return JSONResponse(content=result)
    finally:
        db.close()


@app.get("/ai/health-score", tags=["AI"])
async def ai_health_score():
    """Return per-subsystem and overall plant health scores, with a cached Granite interpretation."""
    db = SessionLocal()
    try:
        result = await calculate_health_score(db)
        return JSONResponse(content=result)
    finally:
        db.close()


app.add_api_websocket_route("/ws/tags", ws_tags)
