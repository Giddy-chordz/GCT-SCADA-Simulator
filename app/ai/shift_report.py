"""
Feature 2 — AI Shift Handover Report.

Aggregates the alarm history and equipment state for the past N hours and
asks IBM Granite to write a concise, shift-operator-style handover brief
that an incoming operator can read in under two minutes.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.ai.gemini_client import call_granite
from app.models import Alarm, Equipments

logger = logging.getLogger(__name__)

# Tag-prefix → human-readable subsystem name used in the report
_SUBSYSTEM_NAMES: dict[str, str] = {
    "GCT": "Gas Conditioning Tower",
    "KLN": "Kiln",
    "VRM": "Vertical Roller Mill",
    "KBF": "Bag Filter / ID Fan",
}

# Severity ordering — L2 and H2 are critical trips; L1/H1 are warnings
_CRITICAL_TYPES = {"L2", "H2"}


def _prefix(tag_id: str) -> str:
    """Return the subsystem prefix from a tag ID (first dash-separated segment)."""
    return tag_id.split("-")[0]


async def generate_shift_report(db: Session, hours: int = 8) -> dict[str, Any]:
    """Query the last `hours` of alarms and equipment state, then ask Granite for a handover brief."""

    now          = datetime.utcnow()
    period_start = now - timedelta(hours=hours)

    # ── 1. Alarm history ─────────────────────────────────────────────────────
    alarms = (
        db.query(Alarm)
        .filter(Alarm.time_stamp >= period_start)
        .order_by(Alarm.time_stamp.asc())
        .all()
    )

    alarm_count    = len(alarms)
    critical_count = sum(1 for a in alarms if a.alarm_type in _CRITICAL_TYPES)

    # ── 2. Group alarms by subsystem and severity ────────────────────────────
    subsystem_summary: dict[str, dict[str, int]] = {}
    for a in alarms:
        pfx = _prefix(a.tag_id)
        subsystem_summary.setdefault(pfx, {})
        subsystem_summary[pfx][a.alarm_type or "UNKNOWN"] = (
            subsystem_summary[pfx].get(a.alarm_type or "UNKNOWN", 0) + 1
        )

    # ── 3. Unacknowledged active alarms ──────────────────────────────────────
    unacked = (
        db.query(Alarm)
        .filter(Alarm.alarm_active == True, Alarm.alarm_acknowledged == False)
        .order_by(Alarm.time_stamp.desc())
        .all()
    )

    # ── 4. Equipment snapshot — TRIPPED or STOPPED drives ────────────────────
    problem_equip = (
        db.query(Equipments)
        .filter(Equipments.status.in_(["TRIPPED", "STOPPED", "ALARM"]))
        .all()
    )

    # ── 5. Build prompt sections ─────────────────────────────────────────────

    # Chronological event list (cap at 30 lines to stay within token budget)
    MAX_EVENTS = 30
    event_lines = [
        f"  {a.time_stamp.strftime('%H:%M') if a.time_stamp else '?'}"
        f"  [{a.alarm_type or '?'}]  {a.tag_id}  {a.alarm_descr or ''}"
        for a in alarms[-MAX_EVENTS:]
    ]
    if len(alarms) > MAX_EVENTS:
        event_lines.insert(0, f"  (showing last {MAX_EVENTS} of {alarm_count} events)")
    events_block = "\n".join(event_lines) or "  None"

    # Per-subsystem count table
    summary_lines = []
    for pfx, counts in sorted(subsystem_summary.items()):
        name = _SUBSYSTEM_NAMES.get(pfx, pfx)
        count_str = ", ".join(f"{t}:{n}" for t, n in sorted(counts.items()))
        summary_lines.append(f"  {name}: {count_str}")
    summary_block = "\n".join(summary_lines) or "  No alarms"

    # Unacknowledged alarms (cap at 15)
    unacked_lines = [
        f"  {a.tag_id}  [{a.alarm_type}]  {a.alarm_descr or ''}"
        f"  @ {a.time_stamp.strftime('%H:%M') if a.time_stamp else '?'}"
        for a in unacked[:15]
    ]
    unacked_block = "\n".join(unacked_lines) or "  None — all alarms acknowledged"

    # Equipment needing attention
    equip_lines = [
        f"  {e.tag_id}  ({e.equip_description})  →  {e.status}"
        for e in problem_equip
        if e.io_type == "DO"   # only report commandable drives, not DI feedback rows
    ]
    equip_block = "\n".join(equip_lines) or "  All drives RUNNING or UNKNOWN"

    prompt = f"""You are an experienced cement plant shift supervisor writing a handover report.

SHIFT PERIOD: {period_start.strftime('%Y-%m-%d %H:%M')} UTC  →  {now.strftime('%H:%M')} UTC  ({hours}h)

ALARM COUNTS BY SUBSYSTEM
{summary_block}

KEY EVENTS (chronological)
{events_block}

UNRESOLVED / UNACKNOWLEDGED ALARMS
{unacked_block}

EQUIPMENT STATUS REQUIRING ATTENTION
{equip_block}

Write a handover brief the way one experienced shift operator would brief another.
Rules:
- Start with one sentence on overall plant status.
- List key events chronologically with timestamps.
- Clearly flag any unacknowledged alarms with ⚠ marker.
- State which equipment is TRIPPED or STOPPED and what the incoming operator must do.
- Direct language only — no filler phrases.
- Under 250 words total.
"""

    report_text = await call_granite(
        prompt,
        max_new_tokens=400,
        temperature=0.3,
        fallback_text=(
            f"[Shift Report — AI unavailable]\n"
            f"Period: {period_start.strftime('%Y-%m-%d %H:%M')} UTC to {now.strftime('%H:%M')} UTC\n"
            f"Total alarms: {alarm_count}  |  Critical: {critical_count}\n"
            f"Unacknowledged alarms: {len(unacked)}\n"
            f"Check alarm panel and equipment status manually."
        ),
    )

    return {
        "report_text":    report_text,
        "period_start":   period_start.isoformat(),
        "period_end":     now.isoformat(),
        "alarm_count":    alarm_count,
        "critical_count": critical_count,
        "generated_at":   now.isoformat(),
    }
