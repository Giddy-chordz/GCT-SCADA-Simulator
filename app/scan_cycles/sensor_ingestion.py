#=============CONTINOUSLY UPDATING SENSOR READINGS==========
from app.database import SessionLocal
from app.models import AnalogTags, DigitalTags
from app.sensor_data import AnalogSensor, sensors
import asyncio
import random

# ── GCT-TT-102 drift-modifier rates (°C per scan cycle, applied as a bias) ──
#
# The four operating regimes, in order of thermal severity:
#   CASE 1 — VRM running  + water lances open  → stable band, no bias
#   CASE 2 — VRM running  + water lances closed → slow upward drift
#             (high GCT load, air-only partial cooling)
#   CASE 3 — VRM stopped  + water lances open  → moderate upward drift
#             (VRM no longer diverting hot gas to raw-meal drying)
#   CASE 4 — VRM stopped  + water lances closed → fastest upward drift
#             (maximum thermal load, no water cooling)
#
# Values are deliberately small per-cycle biases — they accumulate over time,
# producing realistic slow trends rather than step changes.
_GCT_TT102_RATE_STABLE      =  0.00   # Case 1 — target band, no bias
_GCT_TT102_RATE_NO_WATER    =  0.12   # Case 2 — VRM on, air-only cooling
_GCT_TT102_RATE_NO_VRM      =  0.20   # Case 3 — VRM off, water cooling on
_GCT_TT102_RATE_NO_VRM_WATER=  0.45   # Case 4 — VRM off, no water (worst)

# ── VRM vibration idle baseline ───────────────────────────────────────────────
# When the mill drive is not running, vibration sensors return a near-zero
# idle value instead of normal operating-range noise.
_VIB_IDLE_MAX = 0.15   # max mm/s noise amplitude when stopped
_VIB_TAGS = ["VRM-VT-040", "VRM-VT-041", "VRM-VT-042"]


def _all_water_lances_open(db) -> bool:
    """Return True if ALL ten water-lance ZSO feedbacks are True."""
    for i in range(501, 511):
        tag = db.query(DigitalTags).filter(
            DigitalTags.tag_id == f"GCT-XV-{i}-ZSO"
        ).first()
        if not tag or not tag.binary_state:
            return False
    return True


def _vrm_mill_running(db) -> bool:
    """Return True if VRM-MD-010-XS binary_state is True."""
    xs = db.query(DigitalTags).filter(
        DigitalTags.tag_id == "VRM-MD-010-XS"
    ).first()
    return bool(xs and xs.binary_state)


def _vrm_mill_xs_running(db) -> bool:
    """Alias kept for readability — same as _vrm_mill_running."""
    return _vrm_mill_running(db)


#create function to update the process values in the analog_tag table
async def sensor_vals():
    while True:
        db = SessionLocal()
        try:
            # ── Phase 2a + 2b: update GCT-TT-102 drift_modifier ─────────────
            # Determine operating regime from live DB state and set the
            # drift_modifier on the in-memory AnalogSensor object accordingly.
            vrm_on   = _vrm_mill_running(db)
            water_on = _all_water_lances_open(db)

            gct_tt102 = sensors.get("GCT-TT-102")
            if gct_tt102 is not None:
                if vrm_on and water_on:
                    gct_tt102.drift_modifier = _GCT_TT102_RATE_STABLE
                elif vrm_on and not water_on:
                    # Air-only partial cooling: slow upward trend
                    gct_tt102.drift_modifier = _GCT_TT102_RATE_NO_WATER
                elif not vrm_on and water_on:
                    # VRM off, water still cooling: moderate upward trend
                    gct_tt102.drift_modifier = _GCT_TT102_RATE_NO_VRM
                else:
                    # VRM off + no water: fastest rise
                    gct_tt102.drift_modifier = _GCT_TT102_RATE_NO_VRM_WATER

            # ── Phase 3a: vibration idle override ────────────────────────────
            # Read VRM-MD-010-XS once per cycle for all three vibration tags.
            mill_running = vrm_on  # already fetched above

            # ── Write all sensor process values ──────────────────────────────
            for tag_id, data in sensors.items():
                row = db.query(AnalogTags).filter(AnalogTags.tag_id == tag_id).first()
                if not row:
                    continue

                if tag_id in _VIB_TAGS and not mill_running:
                    # Phase 3a — mill stopped: return near-zero idle noise,
                    # bypass normal AnalogSensor.read() to avoid accumulating
                    # random-walk value while the mill is not running.
                    idle_val = round(random.uniform(0.0, _VIB_IDLE_MAX), 2)
                    # Also keep the sensor's internal value anchored near zero
                    # so it doesn't drift away while idle.
                    data.value = idle_val
                    row.process_val = idle_val
                else:
                    row.process_val = data.read()

            db.commit()
        finally:
            db.close()

        await asyncio.sleep(1)
