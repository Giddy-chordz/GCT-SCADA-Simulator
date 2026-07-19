# GCT-SCADA-Simulator

An industrial SCADA/PLC simulator modeling a real cement plant control system, with an AI intelligence layer built on top — built by a student with hands-on practical experience in industrial automation.

**Live demo video:** [link here]
**Selected Challenge:** Wildcard Challenge — *Intelligent Systems for the Future of Work*

---

## Problem Statement

Industrial plant operators work with alarm systems that tell them *what* is wrong but never *why*. When an alarm fires in a real SCADA system, an operator sees a tag number and a red light — nothing more. Diagnosing the actual root cause requires manually cross-referencing multiple correlated systems, checking historical trends, and relying on years of hard-won experience. This diagnostic gap costs valuable time during critical events, increases operator cognitive load during high-stress situations, and means institutional knowledge about *why* certain conditions cause certain failures often lives only in the heads of experienced technicians — not in the system itself.

At the same time, most industrial software prototypes are built by developers who have never worked in a control room, resulting in simulators and dashboards that look plausible but don't reflect how real plant systems actually behave, interlock, and fail together.

---

## Solution Description

I built a full-fidelity SCADA/PLC simulator modeling a real cement plant — Gas Conditioning Tower (GCT), Vertical Roller Mill (VRM), Kiln, and Bag Filter — grounded in my own hands-on practical experience with these exact systems as an HND student in Electrical/Electronic Engineering working within industrial automation.

The simulator is not a static mockup. It models real process interdependencies:

```
Kiln → Hot Gas → VRM (drying) → GCT (cooling) → Bag Filter → ID Fan → Stack
```

A VRM trip genuinely increases thermal load on the GCT. A kiln cannot start barring gear while the main drive is running. Equipment start commands are rejected by real permissive interlocks — not decorative UI states.

To demonstrate the system's real value, the demo deliberately drives the plant into **abnormal operating conditions** — forcing alarm thresholds, triggering interlocks, and initiating trip sequences — showing exactly how the system detects, reasons about, and responds to real plant upsets, rather than only displaying an idle, healthy state.

On top of this working simulation, I layered an AI intelligence system that closes the diagnostic gap operators face every day. See **AI Approach and Architecture** below for full detail.

Beyond the operational benefit, this system also reduces the cost and time of training new operators. Instead of learning plant interdependencies purely through years of on-the-job exposure, a new operator can interact with the AI copilot's explanations and root-cause analyses as a real-time teaching tool — seeing not just what an interlock did, but why it exists and what process relationship it protects.

---

## AI Approach and Architecture

The AI layer consists of four features, each built on top of the same live process database:

### 1. Alarm Root-Cause Assistant
When an alarm fires, the system:
1. Identifies the triggering tag and its subsystem
2. Fetches **correlated tags** across the plant using encoded real process relationships (e.g., GCT outlet temperature is affected by air/water lance state *and* by whether the VRM is running, since a VRM trip reroutes more hot gas to the GCT)
3. Pulls a short window of recent alarm history to detect cascading sequences
4. Sends this structured context to an LLM with a prompt instructing it to reason like an experienced automation engineer — citing evidence, rating confidence, and recommending one concrete action
5. Returns a structured result: root cause summary, confidence level, evidence tags, and suggested action

### 2. Plant Health Score
A **deterministic**, non-LLM calculation (fast enough to run every WebSocket tick) that scores each subsystem 0–100 based on: percentage of tags currently in alarm, equipment running/stopped/tripped status, and how close active values are trending toward their alarm thresholds. An LLM-generated plain-language interpretation of the overall score is cached and refreshed every 60 seconds — separating cheap deterministic computation from more expensive AI calls.

### 3. Shift Handover Report
Queries all alarm activity over a configurable window (default 8 hours), groups it by subsystem and severity, and asks the LLM to write a plain-language handover brief — the way one experienced operator would verbally brief the next at shift change.

### 4. AI Operator Copilot
A background task that checks plant state every 15 seconds and **only speaks when something new needs attention** — a tag newly crossing a warning/critical threshold, or equipment newly entering ALARM/TRIPPED status. It does not repeat the same recommendation while a condition remains active, avoiding notification fatigue. Recommendations are grounded in real process knowledge — for example, when the kiln main drive trips, the copilot reminds the operator to start the barring gear once the fault clears, to prevent the kiln shell from warping while hot and stationary.

### Model Note
This project was built with the intent to use **IBM Granite via watsonx.ai**. During development, I confirmed that IBM Cloud account creation does not currently support Nigeria, and I do not have access to an international card for billing verification. Rather than block the project on this, I built the AI layer to be **model-agnostic** and use **Groq's free API (Llama 3.1)** as a functional equivalent. Every prompt, correlation-fetching function, and fallback-handling mechanism is identical regardless of which model powers it — switching to Granite once regional access is available requires changing only the API client file, not any surrounding logic.

---

## Selected Challenge Theme

**Wildcard Challenge — Intelligent Systems for the Future of Work**

This project fits the Wildcard theme directly: it uses intelligent automation and AI-driven decision support to help an individual (the plant operator) achieve better outcomes — faster diagnosis, proactive guidance, and reduced training time — in a real industrial work context.

---

## How IBM Bob Was Used

IBM Bob was used as my primary development partner throughout this project's build, including:

- **Architecture design** — planning the FastAPI backend structure, WebSocket streaming approach, and background async task organization
- **Endpoint generation** — building the grouped operator command endpoints (roller raise/lower, lance open/close, permissive-checked mill start)
- **Debugging** — diagnosing and fixing real production issues during development, including a critical silent-crash bug in the alarm evaluation loop
- **Code review and refinement** — iterating on interlock logic, cascade behavior between subsystems, and cross-checking implementation against the real process behavior I described

Bob was used in both Ask mode (understanding and reviewing existing code) and Agent mode (implementing new features directly), functioning as a genuine collaborator across the build rather than a one-off tool.

---

## What It Simulates

| Subsystem | What It Does |
|---|---|
| **Kiln** | Main drive / barring gear (mutually exclusive), kiln feed interlock |
| **VRM (Vertical Roller Mill)** | Grinds raw material; roller position (raise/lower), hydraulic system, separator, start permissives |
| **GCT (Gas Conditioning Tower)** | Cools hot kiln gas before the bag filter using air and water lances |
| **Bag Filter** | Filters conditioned gas before it reaches the stack via the ID fan |

---

## Core Features Summary

- **Process Simulation** — realistic sensor value generation (drift, noise, spikes), ISA-standard tag naming, normalized SQLAlchemy schema
- **Alarm & Interlock Engine** — four-tier alarm hierarchy (L1/L2/H1/H2), automatic dedup and auto-clear, timed trip sequences with live countdown, cross-subsystem cascades, mutual-exclusion interlocks, grouped operator commands
- **Industrial HMI Frontend** — real SCADA visual standards (not a SaaS dashboard), live WebSocket streaming, equipment faceplates with Start/Stop/Reset/Acknowledge, process mimic diagram, trend sparklines
- **AI Intelligence Layer** — root-cause assistant, plant health score, shift handover reports, proactive copilot (all detailed above)

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, Alembic
- **Real-time:** WebSockets, asyncio background tasks
- **Frontend:** Vanilla HTML/CSS/JS — industrial HMI styling, no framework
- **AI:** Groq API (Llama 3.1) — functional equivalent to IBM Granite (see Model Note above)
- **Dev tooling:** IBM Bob

---

## Project Structure

```
app/
├── main.py                    # FastAPI app, lifespan, all endpoints
├── database.py                 # SQLAlchemy session setup
├── models.py                   # Equipments, AnalogTags, DigitalTags, Alarm, GroupStatus
├── seed.py                     # Database seeding — tag definitions & setpoints
├── websocket.py                 # /ws/tags — live plant state streaming
├── scan_cycles/
│   ├── sensor_ingestion.py     # Sensor value simulation (drift/noise/spike)
│   ├── gct_cycle.py            # GCT/Kiln: running(), alarm(), trip_reset()
│   ├── vrm_cycle.py            # VRM: run_sequence(), alarm(), trip_reset()
│   └── bagfilter_cycle.py      # Bag Filter: running(), alarm(), trip_reset()
├── ai/
│   ├── groq_client.py          # Shared AI model client
│   ├── root_cause.py           # Alarm root-cause analysis
│   ├── shift_report.py         # Shift handover report generation
│   ├── health_score.py         # Plant health scoring
│   └── ai_copilot.py           # Proactive operator recommendation engine
└── static/
    └── index.html               # Industrial HMI frontend
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL
- A [Groq API key](https://console.groq.com/) (free tier, no card required)

### Setup

```bash
git clone https://github.com/Giddy-chordz/GCT-SCADA-Simulator.git
cd GCT-SCADA-Simulator

python -m venv gctenv
gctenv\Scripts\activate      # Windows
source gctenv/bin/activate   # macOS/Linux

pip install -r requirements.txt

# Create a .env file with:
#   DATABASE_URL=postgresql://user:password@localhost/gct_scada
#   GROQ_API_KEY=your_key_here

alembic upgrade head
python app/seed.py
uvicorn app.main:app --reload
```

Then open `http://localhost:8000` in your browser.

---

## API Overview

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `WS /ws/tags` | Live plant state stream |
| `POST /cmd/{tag_id}/start` \| `stop` \| `reset` \| `ack` | Individual equipment commands |
| `POST /cmd/vrm-rollers/{raise\|lower}` | Grouped roller position control |
| `POST /cmd/vrm-mill/start` | VRM mill start with full permissive check |
| `POST /cmd/gct-air-lances/{open\|close}` | Grouped air lance control |
| `POST /cmd/gct-water-lances/{open\|close}` | Grouped water lance control |
| `GET /trip-status` | Live trip countdown state |
| `GET /ai/root-cause/{tag_id}` | AI root-cause analysis for an active alarm |
| `GET /ai/shift-report?hours=8` | AI-generated shift handover report |
| `GET /ai/health-score` | Plant health scoring |
| `GET /ai/copilot-messages` | Pending proactive AI recommendations |

Full interactive API docs available at `/docs` once running.

---

## Known Limitations / Future Work

- Equipment dynamics (pressure buildup/decay, valve travel time, motor start delays) use simplified drift-rate modifiers rather than full physics-based ramping
- Predictive drift-to-failure detection was scoped out for this submission
- Some feedback consistency edge cases are not fully hardened

Documented, not hidden — the priority was a working, honest system over a fragile, over-scoped one.

---

## About the Builder

Built by **Gideon Oyegbami**, currently an Electrical/Electronic Engineering student, with hands-on practical experience in industrial automation and instrumentation — Allen-Bradley PLCs, SCADA/HMI systems, process instrumentation, and industrial networking.

This project reflects real domain exposure combined with self-taught backend development (Python, FastAPI, SQLAlchemy) and IBM Bob as a development partner throughout the build.
