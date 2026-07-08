import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal
from app.models import Alarm, DigitalTags, Equipments
from app.scan_cycles import bagfilter_cycle, gct_cycle, vrm_cycle
from app.scan_cycles.sensor_ingestion import sensor_vals
from app.websocket import ws_tags

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
    allow_origins=["http://127.0.0.1:5500/"],
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

@app.post("/cmd/{tag_id}/start", tags=["Commands"])
async def cmd_start(tag_id: str):
    """Set equipment status to RUNNING and assert its running feedback DI."""
    db = SessionLocal()
    try:
        equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
        if not equip:
            raise HTTPException(status_code=404, detail=f"{tag_id} not found")
        equip.status = "RUNNING"
        # Assert running feedback digital tag if it exists
        di = db.query(DigitalTags).filter(DigitalTags.tag_id == tag_id).first()
        if di:
            di.binary_state = True
        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "start"}
    finally:
        db.close()


@app.post("/cmd/{tag_id}/stop", tags=["Commands"])
async def cmd_stop(tag_id: str):
    """Set equipment status to STOPPED and de-assert its running feedback DI."""
    db = SessionLocal()
    try:
        equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
        if not equip:
            raise HTTPException(status_code=404, detail=f"{tag_id} not found")
        equip.status = "STOPPED"
        di = db.query(DigitalTags).filter(DigitalTags.tag_id == tag_id).first()
        if di:
            di.binary_state = False
        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "stop"}
    finally:
        db.close()


@app.post("/cmd/{tag_id}/reset", tags=["Commands"])
async def cmd_reset(tag_id: str):
    """Clear TRIPPED/ALARM status back to STOPPED and reset fault DI."""
    db = SessionLocal()
    try:
        equip = db.query(Equipments).filter(Equipments.tag_id == tag_id).first()
        if not equip:
            raise HTTPException(status_code=404, detail=f"{tag_id} not found")
        if equip.status in ("TRIPPED", "ALARM"):
            equip.status = "STOPPED"
        # Clear fault feedback digital tag (XF suffix) if present
        fault_id = tag_id.replace("-XS", "-XF") if tag_id.endswith("-XS") else tag_id + "-XF"
        di_fault = db.query(DigitalTags).filter(DigitalTags.tag_id == fault_id).first()
        if di_fault:
            di_fault.binary_state = False
        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "reset"}
    finally:
        db.close()


@app.post("/cmd/{tag_id}/ack", tags=["Commands"])
async def cmd_ack(tag_id: str):
    """Acknowledge all active alarms for this tag."""
    db = SessionLocal()
    try:
        alarms = db.query(Alarm).filter(
            Alarm.tag_id == tag_id,
            Alarm.alarm_active == True,
            Alarm.alarm_acknowledged == False,
        ).all()
        for a in alarms:
            a.alarm_acknowledged = True
        db.commit()
        return {"ok": True, "tag_id": tag_id, "action": "ack", "acked": len(alarms)}
    finally:
        db.close()


app.add_api_websocket_route("/ws/tags", ws_tags)
