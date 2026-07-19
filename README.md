# GCT-SCADA-Simulator
# GCT-SCADA-Simulator

An industrial SCADA/PLC simulator modeling a real cement plant control system — built by an Automation & Instrumentation Technician who works with these exact systems daily.

This project replicates the process control logic, interlocks, and alarm behavior of a **Gas Conditioning Tower (GCT)**, **Vertical Roller Mill (VRM)**, **Kiln**, and **Bag Filter** — the systems found in a real cement production line — with an AI intelligence layer built on top for root-cause analysis, shift reporting, and live operator guidance.

Built for the IBM AI Builders Challenge (Wildcard Challenge — *Intelligent Systems for the Future of Work*).

---

## Why This Project Exists

Most SCADA simulators are built by developers who've never stood in a control room. This one is different: every interlock, alarm setpoint, and trip sequence is modeled on real cement plant behavior — because I maintain these exact systems as my day job.

The goal wasn't to build a pretty dashboard. It was to build a system that *thinks* like a real plant — where a VRM trip actually increases thermal load on the GCT, where a kiln can't start barring gear while the main drive is running, and where an AI copilot understands *why* an alarm fired, not just *that* it fired.

---

## What It Simulates

| Subsystem | What It Does |
|---|---|
| **Kiln** | Main drive / barring gear (mutually exclusive), kiln feed interlock |
| **VRM (Vertical Roller Mill)** | Grinds raw material; roller position (raise/lower), hydraulic system, separator, start permissives |
| **GCT (Gas Conditioning Tower)** | Cools hot kiln gas before the bag filter using air and water lances |
| **Bag Filter** | Filters conditioned gas before it reaches the stack via the ID fan |

The process chain is modeled as a real dependency graph — not independent components:

```
Kiln → Hot Gas → VRM (drying) → GCT (cooling) → Bag Filter → ID Fan → Stack
```

A VRM trip means more hot gas reaches the GCT. A closed water lance with the VRM running means GCT temperature climbs. These aren't decorative — they drive real alarm and trip behavior.

---

## Core Features

### 🏭 Process Simulation
- Realistic sensor value generation (drift, instrument noise, occasional spikes) per tag
- ISA-standard tag naming and I/O classification (AI / DI / DO / CALC)
- Normalized SQLAlchemy schema: `Equipments`, `AnalogTags`, `DigitalTags`, `Alarm`, `GroupStatus`

### 🚨 Alarm & Interlock Engine
- Four-tier alarm hierarchy (L1 / L2 / H1 / H2) with automatic creation, deduplication, and auto-clearing
- Timed trip sequences (120s countdown) matching real protective interlock philosophy
- Cross-subsystem cascades: auxiliary failures (hydraulic pump, separator) can trip the mill; kiln trips require barring gear
- Mutual-exclusion interlocks (kiln main drive vs. barring gear)
- Grouped operator commands: raise/lower all rollers together, open/close all lances together — not individual valve-by-valve control

### 🖥️ Industrial HMI Frontend
- Built to real SCADA visual standards (Siemens WinCC / ABB / Schneider style) — not a SaaS dashboard
- Live WebSocket data streaming, no polling
- Equipment faceplates with Start / Stop / Reset / Acknowledge controls
- Live trip countdown panel synced to real backend timer state
- Process mimic diagram, trend sparklines, alarm summary, per-subsystem detail screens

### 🤖 AI Intelligence Layer
- **Alarm Root-Cause Assistant** — reasons across correlated tags to explain *why* an alarm fired, not just that it did (e.g., links a GCT temperature alarm to an upstream VRM trip)
- **Shift Handover Report** — AI-generated plain-language summary of the last N hours of plant activity
- **Plant Health Score** — live, deterministic 0–100 score per subsystem, with a cached AI interpretation refreshed periodically
- **Operator Copilot** — a background watcher that proactively surfaces recommendations only when something genuinely needs attention (e.g., "kiln has tripped — start barring gear once cleared")

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, Alembic
- **Real-time:** WebSockets, asyncio background tasks
- **Frontend:** Vanilla HTML/CSS/JS (no framework) — industrial HMI styling
- **AI:** Groq API (Llama 3.1) — used as a functional equivalent to IBM Granite due to regional watsonx.ai access restrictions (see note below)
- **Dev tooling:** IBM Bob (agentic coding assistant) used throughout development

---

## A Note on AI Model Choice

This project was built for an IBM challenge with the intent to use IBM Granite via watsonx.ai. During development, I confirmed with the challenge organizers that IBM Cloud account creation does not currently support Nigeria, and I do not have access to an international card for billing verification.

Rather than block the project, I built the AI layer to be model-agnostic and swapped in **Groq's free API** as a functional substitute. The architecture (prompt construction, correlation logic, fallback handling) is identical regardless of which model powers it — switching back to Granite once regional access is available requires changing only the API client, not the surrounding logic.

**IBM Bob** was used extensively throughout the build — for architecture design, endpoint generation, and debugging — as the actual development assistant for this project.

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
# Clone the repo
git clone https://github.com/Giddy-chordz/GCT-SCADA-Simulator.git
cd GCT-SCADA-Simulator

# Create a virtual environment
python -m venv gctenv
gctenv\Scripts\activate      # Windows
source gctenv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
# Create a .env file with:
#   DATABASE_URL=postgresql://user:password@localhost/gct_scada
#   GROQ_API_KEY=your_key_here

# Run database migrations
alembic upgrade head

# Seed the database with tag definitions
python app/seed.py

# Start the app
uvicorn app.main:app --reload
```

Then open `http://localhost:8000` in your browser.

---

## API Overview

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `WS /ws/tags` | Live plant state stream (analog, digital, equipment, active alarms) |
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

Built under real time constraints — some simplifications were deliberate:

- Equipment dynamics (pressure buildup/decay, valve travel time, motor start delays) use simplified drift-rate modifiers rather than full physics-based ramping
- Predictive drift-to-failure detection was scoped out for this submission
- Some feedback consistency edge cases (e.g., simultaneous open/closed valve feedback) are not fully hardened

These are documented, not hidden — the priority was a working, honest system over a fragile, over-scoped one.

---

## About the Builder

Built by **Gideon Oyegbami (Reon)**, an Automation & Instrumentation Technician at Lafarge Africa, with ~4 years of experience in industrial automation — Allen-Bradley PLCs, SCADA/HMI systems, process instrumentation, and industrial networking.

This project reflects real domain knowledge from daily work on cement plant control systems, combined with self-taught backend development (Python, FastAPI, SQLAlchemy) and this project's use of IBM Bob as a development partner.

---

## License

Built for the IBM AI Builders Challenge. See repository for license details.
