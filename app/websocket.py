import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models import Alarm, AnalogTags, DigitalTags, Equipments

logger = logging.getLogger(__name__)


async def ws_tags(websocket: WebSocket):
    """
    Streams the latest plant state to the HMI once per second.

    A new SQLAlchemy session is created every cycle so updates made by
    command endpoints or scan cycles are immediately visible to the client.
    """

    await websocket.accept()

    try:
        while True:
            db = SessionLocal()

            try:
                # -----------------------------
                # Query latest database state
                # -----------------------------
                analog_rows = db.query(AnalogTags).all()
                digital_rows = db.query(DigitalTags).all()
                equip_rows = db.query(Equipments).all()

                alarm_rows = (
                    db.query(Alarm)
                    .filter(Alarm.alarm_active == True)
                    .order_by(Alarm.time_stamp.desc())
                    .all()
                )

                active_alarm_tags = {
                    alarm.tag_id for alarm in alarm_rows
                }

                # -----------------------------
                # Analog tags
                # -----------------------------
                analog_data = [
                    {
                        "tag_id": row.tag_id,
                        "process_val": row.process_val,
                        "param_unit": row.param_unit,
                        "l1_val": row.l1_val,
                        "l2_val": row.l2_val,
                        "h1_val": row.h1_val,
                        "h2_val": row.h2_val,
                        "alarm_active": row.tag_id in active_alarm_tags,
                    }
                    for row in analog_rows
                ]

                # -----------------------------
                # Digital tags
                # -----------------------------
                digital_data = [
                    {
                        "tag_id": row.tag_id,
                        "binary_state": row.binary_state,
                    }
                    for row in digital_rows
                ]

                # -----------------------------
                # Equipment
                # -----------------------------
                equip_data = []

                for row in equip_rows:

                    if row.io_type is None:
                        logger.warning(
                            "Equipment %s has NULL io_type",
                            row.tag_id,
                        )

                    equip_data.append(
                        {
                            "tag_id": row.tag_id,
                            "equip_description": row.equip_description,
                            "status": row.status,
                            "io_type": row.io_type,
                            "manual_override": row.manual_override,
                        }
                    )

                # -----------------------------
                # Active alarms
                # -----------------------------
                alarm_data = [
                    {
                        "alarm_id": row.alarm_id,
                        "tag_id": row.tag_id,
                        "alarm_type": row.alarm_type,
                        "alarm_descr": row.alarm_descr,
                        "time_stamp": (
                            row.time_stamp.isoformat()
                            if row.time_stamp
                            else None
                        ),
                    }
                    for row in alarm_rows
                ]

                payload = {
                    "analog_tags": analog_data,
                    "digital_tags": digital_data,
                    "equipments": equip_data,
                    "active_alarms": alarm_data,
                }

                await websocket.send_text(json.dumps(payload))

            finally:
                # Always release the session before sleeping
                db.close()

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")

    except Exception:
        logger.exception("Unhandled exception in ws_tags")

        try:
            await websocket.close()
        except Exception:
            pass