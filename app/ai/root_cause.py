"""
Feature 1 — AI Alarm Root-Cause Assistant.

Given an active alarm tag, this module collects every piece of correlated
process data, builds a compact engineering context, and asks IBM Granite to
reason like a senior automation engineer and identify the most probable root
cause with a suggested operator action.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai.gemini_client import call_granite as call_gemini
from app.models import Alarm, AnalogTags, DigitalTags, Equipments

logger = logging.getLogger(__name__)


# ── Subsystem tag catalogue ───────────────────────────────────────────────────
# Maps each subsystem prefix to the specific analog and digital tag IDs that
# are relevant to alarm root-cause analysis for that subsystem.

_SUBSYSTEM_ANALOG: dict[str, list[str]] = {
    "GCT": ["GCT-TT-101", "GCT-TT-102", "GCT-FT-201", "GCT-FT-202"],
    "KLN": ["GCT-TT-101", "GCT-TT-102", "GCT-FT-201", "GCT-FT-202"],
    "VRM": ["VRM-TT-030", "VRM-TT-031", "VRM-VT-040", "VRM-VT-041", "VRM-VT-042", "VRM-PT-060"],
    "KBF": ["KBF-DP-800", "KBF-VT-802", "KBF-TT-803", "KBF-PT-804"],
}

_SUBSYSTEM_DIGITAL: dict[str, list[str]] = {
    "GCT": ["GCT-MP-601-XS", "GCT-MP-601-XF", "GCT-LSH-301", "GCT-LSH-302",
            "KLN-KD-701-XS"],
    "KLN": ["KLN-KD-701-XS", "KLN-KD-701-XF", "KLN-BG-702-XS",
            "GCT-MP-601-XS"],
    "VRM": ["VRM-MD-010-XS", "VRM-MD-010-XF", "VRM-MD-020-XS",
            "VRM-LS-50-ZSU", "VRM-LS-51-ZSU", "VRM-LS-52-ZSU", "VRM-LS-53-ZSU",
            "VRM-LSH-080", "VRM-LSL-081"],
    "KBF": ["KBF-MD-801-XS", "KBF-MD-801-XF", "KBF-CS-805"],
}

# Cross-subsystem correlations: tags from OTHER subsystems that are
# process-connected to the given subsystem and must be included as context.
_CROSS_SUBSYSTEM_ANALOG: dict[str, list[str]] = {
    # Hotter gas from kiln routes to GCT when VRM trips — inlet load rises
    "GCT": ["VRM-TT-030"],
    # Bag filter gas conditioning quality is affected by GCT outlet temperature
    "KBF": ["GCT-TT-102"],
    # VRM has no cross-subsystem analog correlations beyond its own tags
    "VRM": [],
    "KLN": [],
}

_CROSS_SUBSYSTEM_DIGITAL: dict[str, list[str]] = {
    # VRM trip status routes extra hot gas to GCT, raising inlet load
    "GCT": ["VRM-MD-010-XS"],
    # ID fan status directly drives baghouse differential pressure
    "KBF": ["KLN-KD-701-XS"],
    "VRM": [],
    "KLN": [],
}


def _subsystem_of(tag_id: str) -> str:
    """Derive the subsystem prefix from a tag ID string (e.g. 'GCT-TT-102' → 'GCT')."""
    return tag_id.split("-")[0]


def _fmt_analog(row: AnalogTags) -> str:
    """Format a single AnalogTags row into a human-readable one-liner for the prompt."""
    val  = f"{row.process_val:.2f} {row.param_unit or ''}" if row.process_val is not None else "N/A"
    h2   = f"H2={row.h2_val}" if row.h2_val is not None else ""
    h1   = f"H1={row.h1_val}" if row.h1_val is not None else ""
    l1   = f"L1={row.l1_val}" if row.l1_val is not None else ""
    l2   = f"L2={row.l2_val}" if row.l2_val is not None else ""
    limits = " | ".join(x for x in [l2, l1, h1, h2] if x)
    return f"  {row.tag_id}: {val}  [{limits}]"


def _fmt_digital(tag_id: str, row: Optional[DigitalTags], equip: Optional[Equipments]) -> str:
    """Format a digital tag's binary state and equipment status into one line."""
    state  = "ON"  if (row and row.binary_state) else "OFF"
    status = equip.status if equip else "UNKNOWN"
    return f"  {tag_id}: {state}  (equip status: {status})"


async def analyze_alarm(tag_id: str, db: Session) -> dict[str, Any]:
    """Query live plant data for an alarmed tag and ask Granite for the root cause."""

    generated_at = datetime.utcnow().isoformat()

    # ── 1. Fetch the active alarm row ────────────────────────────────────────
    alarm_row: Optional[Alarm] = (
        db.query(Alarm)
        .filter(Alarm.tag_id == tag_id, Alarm.alarm_active == True)
        .order_by(Alarm.time_stamp.desc())
        .first()
    )

    if not alarm_row:
        # No active alarm — return a clean informational response
        return {
            "tag_id": tag_id,
            "root_cause_summary": "No active alarm found for this tag.",
            "confidence": "low",
            "evidence_tags": [],
            "suggested_action": "Verify tag ID and check alarm panel.",
            "generated_at": generated_at,
        }

    subsystem = _subsystem_of(tag_id)

    # ── 2. Collect correlated analog data ────────────────────────────────────
    analog_ids  = _SUBSYSTEM_ANALOG.get(subsystem, [])
    analog_ids += _CROSS_SUBSYSTEM_ANALOG.get(subsystem, [])
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_analog: list[str] = []
    for t in analog_ids:
        if t not in seen:
            seen.add(t)
            unique_analog.append(t)

    analog_rows: dict[str, AnalogTags] = {}
    for t in unique_analog:
        row = db.query(AnalogTags).filter(AnalogTags.tag_id == t).first()
        if row:
            analog_rows[t] = row

    # ── 3. Collect correlated digital data ───────────────────────────────────
    digital_ids  = _SUBSYSTEM_DIGITAL.get(subsystem, [])
    digital_ids += _CROSS_SUBSYSTEM_DIGITAL.get(subsystem, [])
    seen = set()
    unique_digital: list[str] = []
    for t in digital_ids:
        if t not in seen:
            seen.add(t)
            unique_digital.append(t)

    digital_rows: dict[str, tuple[Optional[DigitalTags], Optional[Equipments]]] = {}
    for t in unique_digital:
        dig   = db.query(DigitalTags).filter(DigitalTags.tag_id == t).first()
        equip = db.query(Equipments).filter(Equipments.tag_id == t).first()
        digital_rows[t] = (dig, equip)

    # ── 4. Fetch 5-minute alarm history for the same subsystem ───────────────
    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
    recent_alarms = (
        db.query(Alarm)
        .filter(
            Alarm.time_stamp >= five_min_ago,
            Alarm.alarm_active == True,
        )
        .order_by(Alarm.time_stamp.asc())
        .all()
    )
    # Filter to the same subsystem
    subsystem_recent = [
        a for a in recent_alarms
        if _subsystem_of(a.tag_id) == subsystem
    ]

    # ── 5. Build structured prompt ───────────────────────────────────────────
    alarm_ts = alarm_row.time_stamp.isoformat() if alarm_row.time_stamp else "unknown"

    analog_block = "\n".join(
        _fmt_analog(r) for r in analog_rows.values()
    ) or "  (none available)"

    digital_block = "\n".join(
        _fmt_digital(t, dig, eq) for t, (dig, eq) in digital_rows.items()
    ) or "  (none available)"

    history_block = (
        "\n".join(
            f"  {a.time_stamp.isoformat() if a.time_stamp else '?'}  "
            f"{a.tag_id}  {a.alarm_type}  {a.alarm_descr or ''}"
            for a in subsystem_recent
        )
        or "  (no other alarms in past 5 minutes)"
    )

    evidence_tags = list(analog_rows.keys()) + list(digital_rows.keys())

    prompt = f"""You are a senior automation engineer with deep cement plant experience.
Analyze the following SCADA alarm and identify the root cause.

TRIGGERING ALARM
  Tag     : {tag_id}
  Type    : {alarm_row.alarm_type}
  Desc    : {alarm_row.alarm_descr or 'N/A'}
  Time    : {alarm_ts}

ANALOG PROCESS VALUES (current value  [setpoints])
{analog_block}

DIGITAL / DRIVE STATUS
{digital_block}

RECENT ALARM HISTORY — same subsystem, past 5 minutes
{history_block}

INSTRUCTIONS
- Identify the single most likely root cause using the evidence above.
- Cite the specific tag IDs that point to this cause.
- Rate your confidence: high, medium, or low.
- Suggest exactly one concrete operator action to address the root cause.
- Write in plain English, no hedging, under 150 words.
- Format your answer EXACTLY as:
  ROOT CAUSE: <one sentence>
  EVIDENCE: <comma-separated tag IDs>
  CONFIDENCE: <high|medium|low>
  ACTION: <one sentence>
"""

    ai_text = await call_gemini(
        prompt,
        max_new_tokens=250,
        temperature=0.2,
        fallback_text=(
            "ROOT CAUSE: Unable to determine — AI service unavailable.\n"
            "EVIDENCE: N/A\nCONFIDENCE: low\n"
            "ACTION: Review alarm history manually and consult P&ID."
        ),
    )

    # ── 6. Parse structured Granite response ─────────────────────────────────
    def _extract(label: str) -> str:
        """Pull the text after a labelled line from Granite's response."""
        for line in ai_text.splitlines():
            if line.strip().upper().startswith(label.upper() + ":"):
                return line.split(":", 1)[1].strip()
        return ""

    root_cause  = _extract("ROOT CAUSE")  or ai_text[:120]
    evidence    = _extract("EVIDENCE")    or ""
    confidence  = _extract("CONFIDENCE")  or "low"
    action      = _extract("ACTION")      or "Review alarm panel and escalate to process engineer."

    # Normalise confidence to one of the three valid values
    confidence = confidence.lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

    # Merge Granite-cited tags with the tags we actually queried
    cited: list[str] = [t.strip() for t in evidence.split(",") if t.strip()]
    all_evidence = list(dict.fromkeys(cited + evidence_tags))   # deduplicated, cited first

    return {
        "tag_id":             tag_id,
        "root_cause_summary": root_cause,
        "confidence":         confidence,
        "evidence_tags":      all_evidence,
        "suggested_action":   action,
        "generated_at":       generated_at,
    }
