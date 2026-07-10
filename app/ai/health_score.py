"""
Feature 3 — Plant Health Score.

Computes a deterministic 0-100 health score per subsystem every time it is
called (no LLM needed for the number itself — pure arithmetic so it is fast
enough to run on every WebSocket tick).  A one-line Granite text
interpretation of the overall score is cached for 60 seconds to stay within
API rate limits while still keeping the dashboard meaningful.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai.gemini_client import call_granite
from app.models import Alarm, AnalogTags, DigitalTags, Equipments

logger = logging.getLogger(__name__)

# ── Subsystem tag catalogue (mirrors root_cause.py groupings) ────────────────

_SUBSYSTEM_ANALOG: dict[str, list[str]] = {
    "GCT": ["GCT-TT-101", "GCT-TT-102", "GCT-FT-201", "GCT-FT-202"],
    "VRM": ["VRM-TT-030", "VRM-TT-031", "VRM-VT-040", "VRM-VT-041", "VRM-VT-042", "VRM-PT-060"],
    "KBF": ["KBF-DP-800", "KBF-VT-802", "KBF-TT-803", "KBF-PT-804"],
}

_SUBSYSTEM_EQUIPMENT: dict[str, list[str]] = {
    "GCT": ["KLN-KD-701", "GCT-MP-601"],
    "VRM": ["VRM-MD-010", "VRM-MD-020", "VRM-MD-070"],
    "KBF": ["KBF-MD-801"],
}

# Tags that represent critical running-state feedbacks for each subsystem
_SUBSYSTEM_DIGITAL: dict[str, list[str]] = {
    "GCT": ["KLN-KD-701-XS", "GCT-MP-601-XS"],
    "VRM": ["VRM-MD-010-XS", "VRM-MD-020-XS"],
    "KBF": ["KBF-MD-801-XS", "KBF-CS-805"],
}

_SUBSYSTEM_NAMES: dict[str, str] = {
    "GCT": "Gas Conditioning Tower",
    "VRM": "Vertical Roller Mill",
    "KBF": "Bag Filter / ID Fan",
}

# ── 60-second interpretation cache ───────────────────────────────────────────

_interp_cache: Optional[str]  = None
_interp_cache_ts: float       = 0.0   # unix timestamp of last refresh
_INTERP_TTL: float            = 60.0  # seconds between Granite calls


# ── Helper: analog proximity penalty ─────────────────────────────────────────

def _proximity_penalty(row: AnalogTags) -> float:
    """Return a 0–1 penalty score based on how close a reading is to any alarm limit.

    0.0 = safely in the middle of the operating band.
    1.0 = at or beyond a limit (alarm already active on this dimension).
    """
    val = row.process_val
    if val is None:
        return 0.0

    worst: float = 0.0

    if row.h2_val is not None and row.h1_val is not None and row.h2_val > row.h1_val:
        band = row.h2_val - row.h1_val
        if band > 0:
            worst = max(worst, min(1.0, max(0.0, (val - row.h1_val) / band)))

    if row.l2_val is not None and row.l1_val is not None and row.l1_val > row.l2_val:
        band = row.l1_val - row.l2_val
        if band > 0:
            worst = max(worst, min(1.0, max(0.0, (row.l1_val - val) / band)))

    return worst


def _score_subsystem(
    subsystem: str,
    db: Session,
) -> dict[str, Any]:
    """Compute a 0-100 health score for one subsystem using live DB data.

    Score components (each out of 100, weighted equally):
      A — Alarm fraction : 100 × (1 − active_alarms / total_tags)
      B — Equipment state: 100 × (running_drives / total_drives)
      C — Analog proximity: 100 × (1 − mean_proximity_penalty)
    Final = mean(A, B, C), clamped to [0, 100].
    """
    analog_ids  = _SUBSYSTEM_ANALOG.get(subsystem, [])
    equip_ids   = _SUBSYSTEM_EQUIPMENT.get(subsystem, [])
    digital_ids = _SUBSYSTEM_DIGITAL.get(subsystem, [])

    total_tags  = len(analog_ids) + len(digital_ids)

    # A — Alarm fraction
    active_alarm_tags: set[str] = set()
    if total_tags:
        all_tag_ids = analog_ids + digital_ids
        active_alarms = (
            db.query(Alarm.tag_id)
            .filter(Alarm.tag_id.in_(all_tag_ids), Alarm.alarm_active == True)
            .distinct()
            .all()
        )
        active_alarm_tags = {row.tag_id for row in active_alarms}
    score_a = 100.0 * (1.0 - len(active_alarm_tags) / max(total_tags, 1))

    # B — Equipment running fraction
    running_count = 0
    total_drives  = len(equip_ids)
    for eid in equip_ids:
        equip = db.query(Equipments).filter(Equipments.tag_id == eid).first()
        if equip and equip.status == "RUNNING":
            running_count += 1
        elif equip and equip.status in ("TRIPPED", "ALARM"):
            running_count -= 1   # penalise trips harder than a plain STOP
    score_b = 100.0 * (max(0, running_count) / max(total_drives, 1))

    # C — Analog proximity
    penalties: list[float] = []
    for atid in analog_ids:
        row = db.query(AnalogTags).filter(AnalogTags.tag_id == atid).first()
        if row:
            penalties.append(_proximity_penalty(row))
    mean_penalty = sum(penalties) / len(penalties) if penalties else 0.0
    score_c = 100.0 * (1.0 - mean_penalty)

    final = max(0.0, min(100.0, (score_a + score_b + score_c) / 3.0))

    return {
        "score":          round(final, 1),
        "alarm_fraction": round(score_a, 1),
        "equipment_score": round(score_b, 1),
        "proximity_score": round(score_c, 1),
        "active_alarm_count": len(active_alarm_tags),
        "drives_running":     max(0, running_count),
        "drives_total":       total_drives,
    }


async def calculate_health_score(db: Session) -> dict[str, Any]:
    """Compute per-subsystem health scores, overall score, and a cached Granite interpretation."""
    global _interp_cache, _interp_cache_ts

    now = datetime.utcnow()

    # ── Per-subsystem scores (pure arithmetic, no I/O wait) ──────────────────
    subsystems: dict[str, dict[str, Any]] = {}
    for prefix, name in _SUBSYSTEM_NAMES.items():
        result = _score_subsystem(prefix, db)
        subsystems[prefix] = {"name": name, **result}

    scores = [v["score"] for v in subsystems.values()]
    overall = round(sum(scores) / len(scores), 1) if scores else 0.0

    # ── Granite text interpretation (60-second cache) ─────────────────────────
    now_ts = time.monotonic()
    need_refresh = (
        _interp_cache is None
        or (now_ts - _interp_cache_ts) >= _INTERP_TTL
    )

    if need_refresh:
        sub_lines = "\n".join(
            f"  {v['name']}: {v['score']}/100 "
            f"(alarms:{v['active_alarm_count']} drives:{v['drives_running']}/{v['drives_total']})"
            for v in subsystems.values()
        )
        prompt = (
            f"You are a cement plant control room supervisor.\n"
            f"Overall plant health score: {overall}/100.\n"
            f"Subsystem breakdown:\n{sub_lines}\n\n"
            f"Write exactly ONE plain-English sentence (max 30 words) that a shift "
            f"operator would say when briefed on this score. Be direct and specific."
        )

        new_text = await call_granite(
            prompt,
            max_new_tokens=60,
            temperature=0.3,
            fallback_text=f"Plant health is {overall}/100 — review subsystem scores for details.",
        )
        _interp_cache    = new_text
        _interp_cache_ts = now_ts

    return {
        "overall_score":   overall,
        "interpretation":  _interp_cache,
        "subsystems":      subsystems,
        "generated_at":    now.isoformat(),
        "interp_cached":   not need_refresh,
    }
