"""
AI Operator Copilot — a background task that watches the plant continuously
and speaks up ONLY when there's something worth telling the operator.

Design:
  - Runs every 15 seconds
  - Compares current plant state against the last check
  - Only calls the AI model when something NEW is happening
    (a tag newly crossed a warning/critical threshold, or equipment
    newly went to ALARM/TRIPPED that wasn't in that state last check)
  - Stores the resulting recommendation in an in-memory queue that the
    frontend polls (or pushes via WebSocket — see integration note below)
  - Does not repeat the same recommendation every cycle while a
    condition remains active; only fires again if the condition
    clears and then reoccurs, or a genuinely new condition appears
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import AnalogTags, Equipments
from app.ai.groq_client import call_granite

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 15

# In-memory store of pending copilot messages the frontend hasn't seen yet.
# Simple list is fine given the project's timeline; could move to a
# database table later if persistence across restarts is needed.
copilot_messages: list[dict] = []

# Tracks which conditions we've already recommended on, so we don't spam
# the same message every 15 seconds while a condition stays active.
# Key: a string identifying the condition, e.g. "GCT-TT-102:H1"
_seen_conditions: set[str] = set()


# ── Process-specific correlation knowledge ──────────────────────────────────
# These map an alarming tag to what an experienced operator would check
# or do first — mirrors the real interlock/process knowledge already
# encoded in the scan cycles.

_RECOMMENDATION_HINTS = {
    "GCT-TT-102": (
        "GCT outlet temperature is rising. Check whether air lances and "
        "water lances are open — cooling may be insufficient, especially "
        "if the VRM is not running (less hot gas is diverted to the mill, "
        "increasing GCT thermal load)."
    ),
    "VRM-VT-040": (
        "VRM mill body vibration is elevated. Check roller position "
        "feedback for a mismatch — a roller that hasn't reached its "
        "commanded position can cause uneven grinding load."
    ),
    "VRM-VT-041": (
        "VRM drive vibration is elevated. Check for mechanical looseness "
        "or bearing issues on the main drive."
    ),
    "VRM-VT-042": (
        "VRM gearbox vibration is elevated. Check gearbox lubrication "
        "and alignment."
    ),
    "VRM-PT-060": (
        "VRM hydraulic pressure is out of range. Roller position cannot "
        "be safely changed until pressure is restored — check the "
        "hydraulic pump status."
    ),
    "KBF-DP-800": (
        "Bag filter differential pressure is rising, indicating reduced "
        "cleaning effectiveness. Check the air receiver pressure and ID "
        "fan status."
    ),
    "KBF-TT-803": (
        "ID fan bearing temperature is rising. Check bearing lubrication; "
        "sustained high temperature can lead to bearing failure."
    ),
}

# Equipment-status-specific hints, keyed by (tag_id, status) rather than
# by analog threshold — used for trip/fault conditions where the guidance
# is about the NEXT operator action, not a root cause to investigate.
_EQUIPMENT_STATUS_HINTS = {
    ("KLN-KD-701", "TRIPPED"): (
        "Kiln main drive has tripped. Once the trip cause is cleared, "
        "start the barring gear (KLN-BG-702) to slowly rotate the kiln — "
        "this prevents the shell from bending under its own weight while "
        "hot and stationary, before the main drive can be safely restarted."
    ),
    ("KLN-KD-701-XS", "TRIPPED"): (
        "Kiln main drive has tripped. Once the trip cause is cleared, "
        "start the barring gear (KLN-BG-702) to slowly rotate the kiln — "
        "this prevents the shell from bending under its own weight while "
        "hot and stationary, before the main drive can be safely restarted."
    ),
    ("VRM-MD-010", "TRIPPED"): (
        "VRM mill drive has tripped. Check the trip cause (vibration, "
        "temperature, hydraulic pressure) before attempting reset. "
        "Rollers should remain in their current position until the cause "
        "is confirmed clear."
    ),
    ("KBF-MD-801", "TRIPPED"): (
        "ID fan has tripped. This affects draft through the entire "
        "kiln/GCT/bag filter gas path — expect the whole line to lose "
        "airflow. Address the ID fan fault before restarting anything "
        "upstream."
    ),
}


def _condition_key(tag_id: str, condition_type: str) -> str:
    """Build a unique key identifying a specific alarm condition, so we
    can track whether we've already recommended on it this episode."""
    return f"{tag_id}:{condition_type}"


async def _build_prompt(tag_id: str, alarm_type: str, process_val: float,
                          setpoint: float, unit: str) -> str:
    """Build a short, operator-facing prompt for the AI model."""
    hint = _RECOMMENDATION_HINTS.get(tag_id, "")

    return (
        f"You are an AI copilot assisting a cement plant control room "
        f"operator. A condition has just occurred:\n\n"
        f"Tag: {tag_id}\n"
        f"Alarm type: {alarm_type}\n"
        f"Current value: {process_val} {unit}\n"
        f"Setpoint crossed: {setpoint} {unit}\n\n"
        f"Relevant process context: {hint}\n\n"
        f"Write ONE short, direct recommendation (maximum 40 words) "
        f"telling the operator what to check or do right now. "
        f"Speak like an experienced colleague, not a formal report. "
        f"No preamble, no 'I recommend that you' — just the direct action."
    )


async def _check_analog_tags(db) -> None:
    """Check all analog tags for newly-crossed thresholds and queue an
    AI recommendation for any that are newly alarming."""

    rows = db.query(AnalogTags).all()

    for row in rows:
        if row.process_val is None:
            continue

        alarm_type = None
        setpoint = None

        if row.l2_val is not None and row.process_val <= row.l2_val:
            alarm_type, setpoint = "L2", row.l2_val
        elif row.l1_val is not None and row.process_val <= row.l1_val:
            alarm_type, setpoint = "L1", row.l1_val
        elif row.h2_val is not None and row.process_val >= row.h2_val:
            alarm_type, setpoint = "H2", row.h2_val
        elif row.h1_val is not None and row.process_val >= row.h1_val:
            alarm_type, setpoint = "H1", row.h1_val

        key = _condition_key(row.tag_id, alarm_type) if alarm_type else None

        if alarm_type is None:
            # Condition cleared — allow it to trigger a fresh recommendation
            # if it reoccurs later.
            for possible in ("L1", "L2", "H1", "H2"):
                _seen_conditions.discard(_condition_key(row.tag_id, possible))
            continue

        if key in _seen_conditions:
            # Already recommended on this exact condition — stay quiet.
            continue

        # New condition — get a recommendation and queue it.
        _seen_conditions.add(key)

        prompt = await _build_prompt(
            row.tag_id, alarm_type, row.process_val, setpoint,
            row.param_unit or ""
        )
        recommendation = await call_granite(prompt)

        copilot_messages.append({
            "tag_id": row.tag_id,
            "alarm_type": alarm_type,
            "message": recommendation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seen": False,
        })

        logger.info("Copilot recommendation queued for %s (%s)", row.tag_id, alarm_type)


async def _check_equipment_status(db) -> None:
    """Check equipment for newly-tripped or newly-alarming status and
    queue a recommendation."""

    rows = db.query(Equipments).all()

    for row in rows:
        if row.status not in ("TRIPPED", "ALARM"):
            key_tripped = _condition_key(row.tag_id, "TRIPPED")
            key_alarm = _condition_key(row.tag_id, "ALARM")
            _seen_conditions.discard(key_tripped)
            _seen_conditions.discard(key_alarm)
            continue

        key = _condition_key(row.tag_id, row.status)
        if key in _seen_conditions:
            continue

        _seen_conditions.add(key)

        hint = _EQUIPMENT_STATUS_HINTS.get((row.tag_id, row.status), "")

        prompt = (
            f"You are an AI copilot assisting a cement plant control room "
            f"operator. Equipment {row.tag_id} ({row.equip_description}) "
            f"just went to {row.status} status.\n\n"
            f"Relevant process context: {hint}\n\n"
            f"Write ONE short, direct recommendation (maximum 40 words) "
            f"telling the operator what to check or do next. "
            f"Speak like an experienced colleague, not a formal report."
        )
        recommendation = await call_granite(prompt)

        copilot_messages.append({
            "tag_id": row.tag_id,
            "alarm_type": row.status,
            "message": recommendation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seen": False,
        })

        logger.info("Copilot recommendation queued for %s (%s)", row.tag_id, row.status)


async def ai_copilot() -> None:
    """Background task — watches the plant every 15 seconds and queues
    AI recommendations only when something new needs attention."""

    logger.info("AI copilot started")

    while True:
        db = SessionLocal()
        try:
            await _check_analog_tags(db)
            await _check_equipment_status(db)
        except Exception:
            logger.exception("AI copilot check failed")
        finally:
            db.close()

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)