## LOGIC FOR VRM TO START
STEP 0 — Pre-start permit:
  - Drive fault clear (MD-010-XF)
  - Hydraulic pump running (MD-070-XS)
  - Hydraulic pressure in range (PT-060)
  - Inlet temp in range 150-250°C (TT-030)

STEP 1 — Start separator, confirm running (MD-020-XS)

STEP 2 — Start main drive, confirm running (MD-010-XS)

STEP 3 — Lower rollers, confirm ALL 4 in DOWN position (ZSD x4)
  - If any roller fails to confirm → alarm, hold, no further progression

STEP 4 — VRM considered fully RUNNING

## TRIP CONDITIONS (any one triggers VRM-XS-001 = TRIPPED):

1. VRM-VT-040 ≥ H2   (mill body vibration)
2. VRM-VT-041 ≥ H2   (drive vibration)
3. VRM-VT-042 ≥ H2   (gearbox vibration)
4. VRM-TT-030 ≤ L2   (inlet temp too low — sticking risk)
5. VRM-TT-030 ≥ H2   (inlet temp too high — fire/CO risk)
6. VRM-MD-020-XF     (separator drive fault)
7. VRM-MD-010-XF     (main drive fault)
8. VRM-LS-0XX-ZSU during running, no operator command (unauthorized roller lift)
9. VRM-PT-060 ≤ L2   (hydraulic pressure too low)
10. VRM-PT-060 ≥ H2  (hydraulic pressure too high)
11. VRM-LSL-081       (hydraulic oil tank low level)

# BAG FILTER TRIP LOGIC
KBF-DP-800 ≥ H2 (severe clogging)
  → 60 min timer → system trip
  → Reasoning: excess pressure has a buffer path (VRM/calciner), tolerable delay

KBF-DP-800 ≤ L2 (suspected bag rupture)
  → 5 min timer → system trip
  → Reasoning: no buffer, continuous uncontrolled emissions, only delay = orderly shutdown prep

KBF-MD-801-XF (ID fan fault)
  → Immediate system-wide trip
  → Reasoning: loss of draft collapses entire gas path (kiln → GCT → bag filter → stack)

KBF-CS-805 = FALSE (LOGO PLC comm loss)
  → No automatic trip — procedural escalation to instrument supervisor
  → Reasoning: consistent with your VRM roller-mismatch decision — human verification, not system-enforced