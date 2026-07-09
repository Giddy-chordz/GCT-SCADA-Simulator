import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal
from app.models import Alarm, DigitalTags, Equipments
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
        asyncio.create_task(vrm_cycle.run_sequence(), name="vrm_run_sequence"),
        asyncio.create_task(vrm_cycle.alarm(),        name="vrm_alarm"),
        asyncio.create_task(vrm_cycle.trip_reset(),   name="vrm_trip_reset"),
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
