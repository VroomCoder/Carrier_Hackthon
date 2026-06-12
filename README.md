# NexaCore Growth Coach

AI-powered performance management for mid-size enterprises — goals, continuous feedback, reviews, and coaching grounded in your company OKRs and policy documents.

**Repository:** [github.com/VroomCoder/Carrier_Hackthon](https://github.com/VroomCoder/Carrier_Hackthon)

## Highlights

- **SMART goal calibration** — employees calibrate goals against live OKRs and policy; managers suggest goals with optional **Draft with AI**
- **Continuous feedback** — managers log ongoing feedback; real-time bias nudges on capture
- **Feedback synthesis** — cluster themes, detect bias against policy standards, quality gate before sharing
- **Mid-year & year-end reviews** — self-assessment, manager review, AI summary generation and review drafting
- **Employee achievements** — certifications and accomplishments feed self-assessment, coach briefs, and review drafts
- **Growth Coach** — policy-grounded chat with context brief from goals, feedback, and achievements
- **Team health (managers / HR)** — cycle progress, calibration status, and review readiness across direct reports
- **HR tools** — employee lookup, company OKRs, org structure, policy document management
- **Agent transparency** — every AI workflow emits a trace (loads, handoffs, decisions, confidence)

Data stays local: **SQLite** for structured data, **ChromaDB** for OKR and policy embeddings. LLM calls go to **Google Gemini** (cloud) or **Ollama** (fully local).

## Roles & navigation

| Role | Login | Sidebar |
|------|-------|---------|
| **HR** | PIN `admin` | Team health, Employee lookup, Company OKRs, Org structure, Policy docs |
| **Manager** | Employee + PIN `employee` (anyone with direct reports) | Full workflow + team health for their reports |
| **Employee** | Employee + PIN `employee` | Dashboard, goals, feedback, coach — self only |

Managers are derived from org hierarchy (direct reports in `employees.csv`), not a separate account type.

### Demo logins

| User | Employee ID | PIN | Notes |
|------|-------------|-----|-------|
| HR | — | `admin` | Org-wide access |
| Ravi Kumar (manager) | `NX01010` | `employee` | Engineering manager |
| Siddhant Muller | `NX01007` | `employee` | Has seeded achievements |
| Arjun Mehta | `NX01002` | `employee` | Has seeded achievements |

## Architecture

```
frontend/          React + Vite + Tailwind
backend/
  main.py          FastAPI app, seed on startup
  agents/          Feature routers + AI pipelines
  db/              SQLite repo + Chroma vector store
  data/            employees.csv, policies/*.docx, pmcoach.db (generated)
```

**AI agents** (with activity tracing): Goal Calibrator, Goal Suggestion Draft, Feedback Synthesiser, Feedback Summary, Review Drafter, Growth Coach, Coach Context Brief, Self-Assessment Suggest, Team Health Scoring, OKR Lookup.

**LangGraph orchestration** (pilot): feedback summary (`cluster → draft ⇄ evaluate`), synthesis (`load_context → synthesise → apply_gate`), review draft (`load_context → draft`). Other agents use direct async pipelines with the same trace hooks.

## Guardrails & safety

NexaCore applies **HR-focused guardrails** in feedback and synthesis workflows. It is not a general-purpose content moderation platform — there is no global toxicity filter, PII scanner, or prompt-injection layer on every agent.

### Input controls

| Control | Where | Behaviour |
|---------|--------|-----------|
| **Bias scan (advisory)** | Continuous Feedback → `POST /api/feedback/check-bias` | LLM scans draft text against an 8-type bias taxonomy (halo, horns, recency, gendered language, etc.) and returns flags with neutral rewrite suggestions. Shown as real-time nudges in the UI — does **not** block saving raw feedback. |
| **Length limits** | `bias_scan.py`, `synthesis_steps.py`, `llm_client.py` | Bias check input capped at 2,000 chars; synthesis input at 2,500; Gemini prompts truncated (~6,000 chars); coach chat limited to the last 6 turns. |
| **Role-based access** | `auth.py` + API routers | Employees see self only; managers see direct reports; HR sees org-wide. Unauthorized employee access returns 403. |
| **Policy grounding** | Calibrator, coach, synthesiser | Top policy chunks retrieved via semantic search before prompting — reduces off-policy answers but is not a hard block. |

Implementation: `backend/agents/bias_scan.py`, `backend/agents/continuous_feedback.py`.

### Output controls

| Control | Where | Behaviour |
|---------|--------|-----------|
| **Synthesis bias gate (hard)** | Feedback Synthesiser → `POST /api/synthesise/finalise` | If objectivity score **< 70** and **high-severity** bias flags are present, finalisation is blocked until the manager acknowledges each flagged passage. |
| **Quality evaluator loop** | Feedback summary (LangGraph) | Draft → evaluate → retry (up to 3 attempts) if quality score **< 7**; confidence marked `low` after max retries. |
| **Structured JSON** | Synthesis, summaries, bias scan | Agents expect JSON responses; parse failures surface as 422 errors instead of silently accepting malformed output. |
| **Prompt constraints** | Coach, calibrator, review agents | System prompts require evidence grounding, professional tone, and citation of policy only when relevant excerpts are present. |

The synthesis gate logic lives in `compute_gate()` in `backend/agents/bias_scan.py` and is applied via `apply_synthesis_gate()` in the LangGraph synthesis pipeline.


For production, add a shared moderation layer on all LLM inputs/outputs and human review for high-stakes drafts (reviews, PIPs).

## Setup

### Prerequisites

- **Python 3.10–3.12** (3.12 recommended; 3.14 not supported)
- **Node.js 18+** (for frontend)
- **LLM:** Gemini API key *or* [Ollama](https://ollama.com/download) with a pulled model

### 1. Environment

```bash
cd backend
cp .env.example .env
```

**Gemini (recommended for hackathon demos):**

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Get a key at [Google AI Studio](https://aistudio.google.com/apikey).

**Ollama (fully local):**

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
```

Install Ollama, open the app, then `ollama pull llama3.1`. Verify with `curl http://localhost:11434/api/tags`.

### 2. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

First startup ingests `data/employees.csv`, seeds OKRs and org nodes, indexes policy `.docx` files from `data/policies/`, and syncs vector embeddings.

**Optional data (replace before first run or edit in UI):**

| Path | Purpose |
|------|---------|
| `backend/data/employees.csv` | HRIS export (25 demo employees included) |
| `backend/data/policies/*.docx` | Company policy docs (auto-ingested) |

If Python 3.12 is missing, use [uv](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
UV_SYSTEM_CERTS=1 uv python install 3.12
UV_SYSTEM_CERTS=1 uv venv .venv --python 3.12
source .venv/bin/activate
UV_SYSTEM_CERTS=1 uv pip install -r requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

If `npm` is not found, load nvm (`source ~/.zshrc`) or use `./run-dev.sh`.

### 4. Open the app

**http://localhost:5173**

API docs: **http://localhost:8000/docs**

## Adding policy documents

- **Drop** `.docx` files into `backend/data/policies/` and restart the backend, or
- **Upload** via the Policy Documents panel in the UI (no restart needed)

Every agent retrieves the most relevant policy chunks via semantic search before building prompts.

## Switching the LLM

Edit `backend/.env` and restart the backend. The dashboard shows LLM health (provider, model, reachability).

| Provider | Config | Notes |
|----------|--------|-------|
| Gemini | `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, optional `GEMINI_MODEL` | Default `gemini-2.0-flash` |
| Ollama | `LLM_PROVIDER=ollama`, `OLLAMA_MODEL` | See [ollama.com/library](https://ollama.com/library) |

Lightweight Ollama options: `phi3:mini`, `llama3.2:3b`, `llama3.2:1b`, `gemma2:2b`, `mistral`, `llama3.1` (best quality).

## Troubleshooting

### `pydantic-core` / SSL / Rust build errors (Python 3.14)

Use Python 3.12, or upgrade pip and reinstall:

```bash
pip install --upgrade pip certifi
pip install -r requirements.txt
```

### Hugging Face 403 / `cas-server.xethub.hf.co`

Ensure `.env` includes (already in `.env.example`):

```env
HF_HUB_DISABLE_XET=1
```

Then restart the backend.

### Blank frontend / Tailwind errors

Run `npm run dev` from `frontend/` (not the repo root). Hard-refresh the browser after backend restarts.

## Project layout

```
pm-coach/
├── README.md
├── backend/
│   ├── main.py
│   ├── agents/           # API routes + AI pipelines
│   ├── db/               # SQLite + Chroma
│   ├── data/             # CSV, policies, generated DB
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/components/   # UI panels
    ├── src/utils/nav.ts  # HR role-based navigation
    └── package.json
```

## Security note

Never commit `backend/.env` — it may contain API keys. Use `.env.example` as the template.

## License

Hackathon / demo project — adjust licensing as needed for your organisation.
