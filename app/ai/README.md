# GCT SCADA Simulator — AI Intelligence Layer

Built on **IBM Granite** (via watsonx.ai) for the IBM AI Builders Challenge,  
Wildcard track: *Intelligent Systems for the Future of Work*.

---

## Prerequisites — watsonx.ai Setup

Before any AI endpoint will return a real Granite response, you need four
environment variables in your `.env` file:

```env
# IBM Cloud API key — cloud.ibm.com → Manage → Access (IAM) → API keys
WATSONX_API_KEY=your_ibm_cloud_api_key

# watsonx.ai project ID — watsonx.ai → open your project → Manage → General
WATSONX_PROJECT_ID=your_project_id

# Base URL for your watsonx.ai service instance (region-specific)
WATSONX_URL=https://us-south.ml.cloud.ibm.com

# Granite model to use — leave blank to default to granite-3-3-8b-instruct
GRANITE_MODEL_ID=ibm/granite-3-3-8b-instruct
```

**If these variables are not set the endpoints still work** — they return a
clearly labelled fallback response instead of an error, so a live demo is
never broken by a missing key.

### SDK alternative
If you prefer the official Python SDK over raw HTTP:
```bash
pip install ibm-watsonx-ai
```
Then replace the `httpx` calls in `app/ai/granite_client.py` with the
`ModelInference` class.  The REST approach used here has zero extra
dependencies.

---

## API Endpoints

### Feature 1 — Alarm Root-Cause Analysis

```
GET /ai/root-cause/{tag_id}
```

Given an **active alarm tag**, fetches correlated analog/digital process data
across subsystems, builds an engineering context window, and asks Granite to
identify the most likely root cause, cite evidence tags, rate confidence, and
suggest one operator action.

**Cross-subsystem correlations encoded:**
- `GCT-TT-102` (outlet temp) ← `GCT-FT-201/202` + `VRM-MD-010-XS` (VRM trip routes extra heat to GCT)
- `KBF-DP-800` (ΔP) ← `KBF-MD-801-XS` (ID fan) + `GCT-TT-102` (hot gas conditioning)
- `VRM-VT-040/041/042` (vibration) ← `VRM-LS-50–53-ZSU` (roller position)

**Response shape:**
```json
{
  "tag_id":             "GCT-TT-102",
  "root_cause_summary": "High outlet temperature caused by low water flow ...",
  "confidence":         "high",
  "evidence_tags":      ["GCT-FT-202", "GCT-FT-201", "VRM-MD-010-XS"],
  "suggested_action":   "Increase water lance flow rate on GCT-FT-202.",
  "generated_at":       "2025-06-30T14:22:05"
}
```

**Test with curl:**
```bash
curl http://localhost:8000/ai/root-cause/GCT-TT-102
```

---

### Feature 2 — AI Shift Handover Report

```
GET /ai/shift-report?hours=8
```

Queries the last `hours` hours of alarm history (default 8, max 24), groups
events by subsystem, identifies unacknowledged alarms, and asks Granite to
write a concise shift handover brief in the voice of an experienced cement
plant operator.

**Query parameters:**
| Param   | Type | Default | Range |
|---------|------|---------|-------|
| `hours` | int  | `8`     | 1–24  |

**Response shape:**
```json
{
  "report_text":    "Plant was largely stable through the shift. At 06:14 a GCT-TT-102 H2 ...",
  "period_start":   "2025-06-30T06:00:00",
  "period_end":     "2025-06-30T14:00:00",
  "alarm_count":    12,
  "critical_count": 3,
  "generated_at":   "2025-06-30T14:00:00"
}
```

**Test with curl:**
```bash
# Default 8-hour report
curl http://localhost:8000/ai/shift-report

# 4-hour report
curl "http://localhost:8000/ai/shift-report?hours=4"
```

---

### Feature 3 — Plant Health Score

```
GET /ai/health-score
```

Returns a **0–100 health score per subsystem** (GCT, VRM, KBF) computed from
three deterministic components:

| Component | Weight | Description |
|-----------|--------|-------------|
| Alarm fraction | 1/3 | `100 × (1 − active_alarms / total_tags)` |
| Equipment state | 1/3 | `100 × (running_drives / total_drives)`; tripped drives penalised |
| Analog proximity | 1/3 | How close analog values are to alarm thresholds |

The overall score is the mean of subsystem scores.

A **one-line Granite text interpretation** of the overall score is cached for
60 seconds to keep API calls within budget while the score itself refreshes
every WebSocket tick.

**Response shape:**
```json
{
  "overall_score":  87.4,
  "interpretation": "Plant is operating normally with minor temperature creep in the GCT.",
  "subsystems": {
    "GCT": { "name": "Gas Conditioning Tower", "score": 91.2, "active_alarm_count": 0, ... },
    "VRM": { "name": "Vertical Roller Mill",    "score": 85.0, "active_alarm_count": 1, ... },
    "KBF": { "name": "Bag Filter / ID Fan",     "score": 86.0, "active_alarm_count": 0, ... }
  },
  "generated_at":  "2025-06-30T14:22:10",
  "interp_cached": false
}
```

**Test with curl:**
```bash
curl http://localhost:8000/ai/health-score
```

---

## File Map

```
app/ai/
├── __init__.py          # package marker
├── granite_client.py    # shared async Granite/watsonx.ai HTTP client + IAM token cache
├── root_cause.py        # Feature 1: analyze_alarm()
├── shift_report.py      # Feature 2: generate_shift_report()
├── health_score.py      # Feature 3: calculate_health_score()
└── README.md            # this file
```

## Interactive API docs

With the app running, visit **http://localhost:8000/docs** — all three
endpoints appear under the **AI** tag with full request/response schemas.
