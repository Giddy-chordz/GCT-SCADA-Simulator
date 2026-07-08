import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models import Alarm, AnalogTags, DigitalTags, Equipments

logger = logging.getLogger(__name__)


async def ws_tags(websocket: WebSocket):
    await websocket.accept()
    db = SessionLocal()
    try:
        while True:
            analog_rows  = db.query(AnalogTags).all()
            digital_rows = db.query(DigitalTags).all()
            equip_rows   = db.query(Equipments).all()

            # Build a set of tag_ids that have at least one active alarm
            active_alarm_tags = {
                row.tag_id
                for row in db.query(Alarm).filter(Alarm.alarm_active == True).all()
            }

            # Active alarm records (for alarm summary panel)
            alarm_rows = (
                db.query(Alarm)
                .filter(Alarm.alarm_active == True)
                .order_by(Alarm.time_stamp.desc())
                .all()
            )

            analog_data = [
                {
                    "tag_id":       row.tag_id,
                    "process_val":  row.process_val,
                    "param_unit":   row.param_unit,
                    "l1_val":       row.l1_val,
                    "l2_val":       row.l2_val,
                    "h1_val":       row.h1_val,
                    "h2_val":       row.h2_val,
                    "alarm_active": row.tag_id in active_alarm_tags,
                }
                for row in analog_rows
            ]

            digital_data = [
                {
                    "tag_id":       row.tag_id,
                    "binary_state": row.binary_state,
                }
                for row in digital_rows
            ]

            equip_data = []
            for row in equip_rows:
                if not row.io_type:
                    logger.warning(
                        "WebSocket: tag %s has missing/null io_type — "
                        "command faceplate will treat it as read-only",
                        row.tag_id,
                    )
                equip_data.append({
                    "tag_id":            row.tag_id,
                    "equip_description": row.equip_description,
                    "status":            row.status,
                    "io_type":           row.io_type,
                    "manual_override":   row.manual_override,
                })

            alarm_data = [
                {
                    "alarm_id":    row.alarm_id,
                    "tag_id":      row.tag_id,
                    "alarm_type":  row.alarm_type,
                    "alarm_descr": row.alarm_descr,
                    "time_stamp":  row.time_stamp.isoformat() if row.time_stamp else None,
                }
                for row in alarm_rows
            ]

            payload = json.dumps({
                "analog_tags":  analog_data,
                "digital_tags": digital_data,
                "equipments":   equip_data,
                "active_alarms": alarm_data,
            })
            await websocket.send_text(payload)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
