# CertifyAI — ELEC5620 Stage 2 prototype

An AI assisted IELTS and TOEFL preparation system with four executable LangGraph agent roles, a human instructor, persistent results and a mandatory quality gate. The source is designed to be downloaded from Canvas and run without an API key in **DEMO MODE**.

## Quick start on Windows PowerShell

Prerequisites: Python 3.11+ and Node.js 24 LTS. From the repository root:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m backend.seed
.\.venv\Scripts\python -m backend.demo_seed
.\.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000
```

In a second PowerShell window:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open `http://localhost:5173`. API docs are at `http://localhost:8000/docs`.

Demo learner: `demo.learner@example.com` / `DemoLearner123!`. The demo seed creates an active IELTS plan, one verified writing result and one unresolved contradictory result. Instructor: `instructor@example.com` / `ChangeMe123!` unless changed in `.env`. Change both instructor credentials and `JWT_SECRET` before any network deployment. Seed scripts are idempotent for the fixed demo account; `demo_seed` will add new sample submissions each time.

The UI also supports registering a fresh learner. In Settings, the current mode is shown. Writing practice has explicit demo controls to produce normal, low confidence, contradictory or malformed outputs. Held results expose only the hold message to the learner; sign in as the instructor to inspect evidence and approve, correct or request more information.

Run `python -m scripts.package_source` to create `ELEC5620-Stage2-Source.zip` for Canvas. It contains the source, migration, tests, documentation and Stage 1 PDF, with no local virtual environment, installed Node packages, database or credentials.

## Docker alternative

Copy `.env.example` to `.env`, set a private `JWT_SECRET` and instructor password, then run:

```powershell
docker compose up --build
```

Open `http://localhost:8080`. SQLite data and uploaded audio use named Docker volumes. The backend container applies Alembic migrations and seeds the instructor/material catalog on startup. To add demonstration learner data:

```powershell
docker compose exec backend python -m backend.demo_seed
```

## Real AI mode

Set `DEMO_MODE=false`, `OPENAI_API_KEY`, and optionally `LLM_MODEL` in `.env`. The shared LangChain `ChatOpenAI` adapter produces Pydantic structured plans, feedback, consistency verdicts, recommendations and report narratives. `TRANSCRIPTION_MODEL` may be set to an available audio transcription model; if absent or the service fails, audio is retained and the UI requests a manually entered transcript. Do not put credentials in source control. LLM calls receive exam settings, anonymised progress and submitted learning text, without account name or email.

Real mode requires an external provider account and has not been live tested here because no API key was supplied. Invalid structured output is held for instructor review. An unavailable provider during output generation cannot issue a verified result. The numbers labelled `confidence` are model self-reports and **are not calibrated probabilities**. Tune the 0.70 threshold only after evaluating labelled examples; the Stage 1 false alarm and detection targets remain unvalidated.

## Architecture and quality invariant

`backend/agents.py` defines executable LangGraph `StateGraph` workflows. Plan creation/adaptation runs Learning Coordinator → Quality Manager → conditional release or durable human wait. Writing/speaking runs AI Tutor → Assessment & Analytics → Quality Manager → conditional release or durable human wait. The provider adapter centralises model calls and includes LangChain tools for skill priority and criterion mean. Other agent handoffs use persisted agent events and the same quality service. The workflow monitor reads those real events.

`result_packages` is the release boundary. The learner API returns `payload` only in `RELEASED`. Quality checks persist structured field, criterion confidence, threshold, score range and contradiction verdicts. Held packages create escalation cases. The instructor can change the 0.70 default threshold in Quality Operations; the change is saved and audited. Instructor decisions and audits persist in SQLite; approval/correction releases the package. A held workflow remains in the database so human decisions can resume it after a server restart. Automated weekly plan proposals can be run with `python -m backend.scheduled_review` from a scheduler. Curriculum gap notices are logged when the same feedback issue occurs for five learners in seven days.

This is an **educational preparation prototype**. Scores and readiness are estimates. IELTS uses 0–9 band style estimates; TOEFL uses its [2026 1–6 scale](https://www.ets.org/toefl/test-takers/ibt/scores/understand-scores.html). The mock exam is explicitly reduced length but keeps listening, reading, writing and speaking, per-section persistence and completeness checks. Reading and listening passages are short demo text tasks. Speaking audio is recordable and stored; pronunciation is marked unavailable without an audio scoring service. No text transcript is treated as pronunciation evidence.

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
Set-Location frontend
npm.cmd run build
npm.cmd run test:e2e
```

Playwright starts a separate demo database and backend automatically. For a clean rehearsal, use a fresh checkout, copy `.env.example`, run migrations, seed the catalog and demo data, start both servers, register a new learner, accept a plan, submit writing twice (normal and low confidence), review the held case as instructor, then revisit the learner result, request adaptation and inspect the dashboard/workflow monitor. Docker provides the same app on port 8080.

## Stage 1 traceability and current limits

The Stage 1 report in the root is the design source. [Traceability and status](docs/IMPLEMENTATION_STATUS.md) records what each use case actually does and what remains incomplete. The [Jira import backlog](docs/jira-backlog.csv) assigns four one-week sprints; [review templates](docs/agile-evidence.md) support honest sprint evidence.

Current limits: no calibrated score validation, no official full-length examination, no audio listening clips, no configured pronunciation assessor, no live provider verification, and no load or accessibility audit. Draft autosave is in the browser; mock answers persist in SQLite. The frontend currently bundles all routes in one JavaScript chunk. For a production deployment, add email verification, password reset, rate limits, stronger secret management, object storage and security monitoring.

## Troubleshooting

- `node` or `npm` missing: install Node.js 24 LTS and reopen PowerShell. Use `npm.cmd` when PowerShell blocks `npm.ps1`.
- Database table missing: run `python -m alembic upgrade head` using the same Python interpreter and `DATABASE_URL` as the server.
- `401`: sign in again; tokens expire after 24 hours. `403`: the account role cannot access that route.
- `409` on mock creation: accept a verified plan first. `409` on exam submit: fill and save all four sections.
- Quality hold: log in as the instructor and resolve the case. A hold deliberately hides the underlying payload from the learner.
- Microphone failure: allow browser microphone access, use localhost/HTTPS, or enter a transcript manually. Text-based feedback will not score pronunciation.
- Real mode provider failure: confirm API key, model name and network access. Return to `DEMO_MODE=true` for a fully offline demonstration.
