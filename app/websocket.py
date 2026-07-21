import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from database import SessionLocal
from models import Alarm, AnalogTags, DigitalTags, Equipments

logger = logging.getLogger(__name__)




async def ws_tags(websocket: WebSocket):
    logger.info("WS: connection received")

    await websocket.accept()
    logger.info("WS: accepted")

    while True:
        logger.info("WS: querying database")

        db = SessionLocal()

        try:
            analog_rows = db.query(AnalogTags).all()
            logger.info("WS: queried analog tags")

            digital_rows = db.query(DigitalTags).all()
            logger.info("WS: queried digital tags")

            equipment_rows = db.query(Equipments).all()
            logger.info("WS: queried equipment")

            payload = {
                "analog": [row.__dict__ for row in analog_rows],
                "digital": [row.__dict__ for row in digital_rows],
                "equipment": [row.__dict__ for row in equipment_rows]
            }

            logger.info("WS: sending payload")
            await websocket.send_text(json.dumps(payload))
            logger.info("WS: payload sent")

        finally:
            db.close()

        await asyncio.sleep(1)