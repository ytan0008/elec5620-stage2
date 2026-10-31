# CertifyAI · Pixel Academy

An AI-powered IELTS and TOEFL (2026 format) preparation platform, built as a **one-person AI company**: four AI agents and one human instructor work together to give learners personalised practice, feedback they can trust and a realistic estimate of their exam readiness.

ELEC5620 Stage 2 implementation · Group 3 (Wednesday 09–11). The design follows our Stage 1 report, `ELEC5620_Wed_09-11 Group3.pdf`, in this repository.

---

## Contents

1. [What the system does](#1-what-the-system-does)
2. [Quick start with Docker (recommended)](#2-quick-start-with-docker-recommended)
3. [Turning on the cloud AI model (optional)](#3-turning-on-the-cloud-ai-model-optional)
4. [Accounts and a first walkthrough](#4-accounts-and-a-first-walkthrough)
5. [Running without Docker (for development)](#5-running-without-docker-for-development)
6. [Features in detail](#6-features-in-detail)
7. [The four AI agents](#7-the-four-ai-agents)
8. [Architecture](#8-architecture)
9. [Project structure](#9-project-structure)
10. [Configuration reference](#10-configuration-reference)
11. [Testing](#11-testing)
12. [Canvas submission package](#12-canvas-submission-package) · [Jira backlog](#jira-backlog)
13. [Troubleshooting](#13-troubleshooting)
14. [Limitations and honesty notes](#14-limitations-and-honesty-notes)
15. [Credits and licences](#15-credits-and-licences)

---

## 1. What the system does

There are two kinds of user:

- **Learners** practise all four skills in real exam format, talk to an AI tutor that remembers them, keep notebooks of mistakes and new words, take full mock exams and follow a personalised study plan.
- **The instructor (teacher)** gets a developer console. It shows what every agent is doing, what each agent remembers, detected anomalies and learner problem reports. The instructor also reviews any AI result that the Quality Manager held back.

The interface is a surreal, animated pixel-art world. The learner's AI companion is a pixel witch (**Luna**) or a pixel boy (**Kai**); you can switch in **Settings**.

**Every AI result passes a quality gate before a learner sees it.** If a score contradicts its own feedback, or the AI is not confident enough, the result is held and sent to the instructor.

The system runs in two modes:

| Mode | When | What happens |
|---|---|---|
| **LOCAL** | No API key (default) | Everything runs offline. It uses a curated exam-format test bank, a rule-based marking engine, a scripted speaking examiner and a rule-based tutor. No internet or payment needed. |
| **REAL** | An OpenAI API key is set | GPT-6 Luna writes the conversation, feedback, examiner follow-ups, plans, reports and brand-new tests. Cloud voices and transcription are also used. |

---

## 2. Quick start with Docker (recommended)

This is the easiest way for group members to run the project. It works on Windows, macOS and Linux.

### Prerequisites

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/). It must be **running** (whale icon in the system tray) before you continue.

### Steps

```bash
git clone https://github.com/ytan0008/elec5620-stage2.git
cd elec5620-stage2
docker compose up --build
```

The first build takes a few minutes. When the log goes quiet, open **http://localhost:8080** in **Chrome or Edge**.

You do **not** need to create a `.env` file. The defaults in `.env.example` start the app in LOCAL mode.

### Everyday commands

| Task | Command |
|---|---|
| Start in the background | `docker compose up -d` |
| Stop | `docker compose down` |
| Rebuild after pulling new code | `git pull` then `docker compose up -d --build` |
| See backend logs | `docker compose logs -f backend` |
| Reset all data (accounts, results) | `docker compose down -v` (**deletes the database volume**) |

Database migrations and seed data run automatically every time the backend container starts.

---

## 3. Turning on the cloud AI model (optional)

1. Copy the example settings file:
   - Windows PowerShell: `Copy-Item .env.example .env`
   - macOS / Linux: `cp .env.example .env`
2. Open `.env` and replace `xxx` with your own key:
   ```
   OPENAI_API_KEY=sk-...your key...
   ```
3. Restart: `docker compose up -d`.
4. The badge in the header and the **Settings** page should now show **REAL** mode.

> **Never commit `.env` or paste your key into code, issues or chat.** `.env` is already in `.gitignore`. While the key is `xxx` or empty, the app stays in LOCAL mode instead of failing.

The default model is **`gpt-6-luna`**, the cheapest and fastest GPT-6 model. It is called through the OpenAI **Responses API** with two reasoning settings:

- `LLM_REASONING_EFFORT=none` for fast replies (chat, the speaking examiner, word look-ups)
- `LLM_SCORING_EFFORT=low` for scoring, plans, reports and quality verdicts

To use another OpenAI-compatible provider (for example DeepSeek), set `OPENAI_BASE_URL` and `LLM_MODEL`, make both reasoning settings empty and set `LLM_USE_RESPONSES_API=false`. Cloud voice needs an endpoint that offers `/audio` (OpenAI does). Otherwise the browser's own voices and speech recognition are used automatically.

---

## 4. Accounts and a first walkthrough

| Role | How to sign in |
|---|---|
| **Instructor / teacher** | `instructor@example.com` / `ChangeMe123!` (change with `INSTRUCTOR_EMAIL` / `INSTRUCTOR_PASSWORD` in `.env`) |
| **Learner** | Click **Sign up** and create any account |
| **Sample learner with history** (local development only) | Run `python -m backend.demo_seed`, then sign in as `demo.learner@example.com` / `DemoLearner123!` |

Learners and the teacher use the same sign-in page. The system sends each role to its own area: learners to the dashboard, the teacher to the developer console. To use both at once, open the teacher account in a private/incognito window.

### Suggested 10-minute tour

1. **Sign up as a learner.** The setup assistant interviews you (by voice or text) about your exam, level, target score, exam date and study time. It then builds your **learning portrait**.
2. **Learning plan:** generate a plan and accept it. The mock exam unlocks after this.
3. **Speaking:** start a full test. The avatar examiner speaks each question and listens through your microphone.
4. **Writing:** write a short Task 2 essay and submit it. You get criterion scores and sentence-level corrections. Submit again to see **"Compared with your last attempt"**.
5. **Reading or Listening:** answer, submit, then select any word in the passage to save it to your **Word book**.
6. **AI Tutor:** say "I don't know the word *mitigate*", "remember that I work night shifts" or "quiz me".
7. **Notebooks:** see your Mistake, Word, Grammar and Sentence books.
8. **Sign in as the teacher** (in a private window) and open **Developer console**, **Agent activity**, **Agent memory**, **Anomalies** and **Review queue**.

---

## 5. Running without Docker (for development)

Use this if you want hot reload while editing the code.

### Prerequisites

- Python **3.11+** (3.12 recommended)
- Node.js **24 LTS**

### Backend (terminal 1)

Windows PowerShell:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m backend.seed
.\.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000
```

macOS / Linux:

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m backend.seed
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

### Frontend (terminal 2)

```bash
cd frontend
npm ci          # on Windows PowerShell use: npm.cmd ci
npm run dev     # on Windows PowerShell use: npm.cmd run dev
```

Open **http://localhost:5173**. The Vite dev server forwards `/api` requests to the backend on port 8000.

After pulling changes that add database tables, run `alembic upgrade head` again.

---

## 6. Features in detail

### Learner side

| Area | What you get |
|---|---|
| **Onboarding** | Conversational setup assistant (voice or text) that captures exam, level, target, date, weekly hours and priority skills. Produces a quality-checked learning portrait. |
| **Learning plan** | Weekly activities with a reason for each priority. You can accept, reject or request changes (for example "more speaking"). Plans adapt to verified results after your request, every week, or after a mock exam: each major change comes with a reason and study resources, and your current plan stays active until you accept (or when there is not enough data) |
| **Listening** | IELTS Parts 1–4 and TOEFL 2026 tasks with multi-speaker scripts read aloud in distinct voices. Exam mode plays once; practice mode allows pause, replay and 0.8–1.3× speed. Form/note completion, multiple choice and matching. Marked against hidden keys, converted to a band, with a transcript that highlights where each answer is. |
| **Reading** | Academic passages with TRUE/FALSE/NOT GIVEN, YES/NO/NOT GIVEN, matching headings, multiple choice and completion. TOEFL Complete-the-Words, daily-life and academic passages. Timer and evidence highlighting after marking. |
| **Writing** | Task 1 with rendered bar/line/pie charts, Task 2 essays, TOEFL email and academic discussion. Timer, word count, autosaved drafts, criterion scores, sentence-level corrections, "level-up" rewrites, a model answer (REAL mode), revision history and a comparison with your previous attempt. |
| **Speaking** | Live spoken test: Part 1 → Part 2 cue card (1 min preparation, 2 min talk) → Part 3, or TOEFL Listen & Repeat + Interview. Hands-free turn-taking through the microphone; the session is recorded for replay. Feedback on fluency (speech rate, fillers), vocabulary and grammar. Also **Free talk** voice conversation with gentle corrections. |
| **Mock exam** | Short (~90 min) or full-length (~2 h 45 min) computer-delivered mock covering all four sections. Persistent timer, autosave, live speaking examiner, section scores and a detailed review. |
| **AI Tutor** | Full-page tutor plus a floating assistant on every page. Remembers your background, goals, difficulties and verified progress across conversations; you can view and delete these memories. "Coach me" builds today's plan from your notebooks. |
| **Notebooks** | **Mistake book:** every wrong listening, reading or mock answer, statistics on which question types you miss most, retry and spaced review. **Word book:** select any word anywhere, or tell the tutor; saved with phonetics, Chinese meaning, definition and source sentence; flashcards with spaced repetition. **Grammar book:** errors from feedback with corrections, counted by type. **Sentence book:** improved rewrites and saved sentences, tagged by structure. |
| **Dictionary** | Select a word to see phonetics, Chinese meaning and definitions. Works offline. **During tests a word can be saved but its meaning stays hidden** until the test ends; the tutor is also locked during a mock. |
| **Progress** | Performance charts from verified results only, strengths and weaknesses, repeated issues, quality-checked reports, knowledge graph and study-material recommendations. |
| **Report a problem** | "Score looks wrong?" on every result sends a report to the teacher; replies appear in **Settings → My reports**. |

### Teacher side (developer console)

| Page | Purpose |
|---|---|
| **Developer console** | Engine mode and model, activity in the last 24 h and 7 days, hold rate, active learners and per-agent latency. |
| **Agent activity** | Live trace of every perception, decision, tool call, hand-off, quality check and release, filterable by agent, learner and slow steps. |
| **Agent memory** | What each of the four agents remembers (episodes and lessons). |
| **Anomalies** | Automatic detection of model failures, provider outages, quality holds, high hold rates, slow steps, speech failures, sudden score drops, curriculum gaps, inactive learners and learner reports. Each can be acknowledged. |
| **Learner reports** | Problem reports from learners, with replies. |
| **Review queue** | Results held by the Quality Manager. The teacher is notified, sees the learner's earlier results, previous decisions and highlighted conflicts, and can approve, override with a corrected result, or request more information. Marking yourself away queues new cases until you are available again. |
| **Quality operations** | Quality-check history and the adjustable confidence threshold (default 0.70). |

---

## 7. The four AI agents

These follow the roles in Stage 1 report sections 1.2 and 7. Each agent has **its own memory** and **its own tools**. In REAL mode the model decides which tools to call (at most `AGENT_TOOL_ROUNDS` rounds) and then submits a structured answer.

| Agent | Responsibility | Memory | Tools |
|---|---|---|---|
| **Learning Coordinator** | Onboarding, learner portrait, learning plans and adaptation, material recommendations, hand-offs | Plans proposed, accepted or rejected; change requests | plan history, verified scores, notebook statistics, material search |
| **AI Tutor** | Practice in all four skills, prompts, immediate detailed feedback, conversation | Feedback given and its main issues, plus the learner-editable tutor memory | previous feedback, notebook statistics, dictionary, grammar checker, text measures, question bank |
| **Assessment & Analytics** | Scoring against the rubrics, trends, reports and readiness | Estimates and score changes per skill | band descriptors, raw-score → band conversion, score history, text measures |
| **Operations & Quality Manager** | Consistency and confidence checks, holding and escalating results, curriculum-gap detection | Holds per learner; lessons from the teacher's review decisions (shared across all learners) | quality threshold, instructor decisions, cohort issue counts, hold rate |

Notes on the design:

- Every agent can also `recall_memory` and `save_memory`.
- Tools only **read** data, apart from saving a memory. No model can release a result or change its own prompts.
- Tool calls appear in **Agent activity**; memories appear in **Agent memory**.
- **No fine-tuning is used.** The agents rely on rubric tools, memory and the quality gate. These are auditable and need no training data.

---

## 8. Architecture

The system uses a layered architecture with centralised quality control (Stage 1 report, section 4.2).

```
 Presentation   React + Vite (learner app, teacher console)              frontend/
      │  REST /api
 Agent layer    LangGraph StateGraphs                                    backend/agents.py
                Coordinator ─┐                                           backend/agent_core.py
                Tutor → Assessment & Analytics ─┼─→ Quality Manager ─→ RELEASE
                                                └──────────────────→ HOLD → Instructor review
 Service layer  ProviderAdapter (one LLM interface, LOCAL or REAL),      backend/agents.py
                exam content, scoring, examiner, speech, dictionary      backend/content, scoring.py, examiner.py, speech.py, notebook.py
 Data layer     SQLAlchemy + Alembic (SQLite)                            backend/models.py, migrations/
```

Key rules:

- **One LLM interface.** Every model call goes through `ProviderAdapter`, so the provider can be changed or run offline without touching the agents.
- **Release boundary.** Each AI output is stored as a `result_package`. Learners only see packages in state `RELEASED`; held packages wait for the teacher.
- **Structured output with confidence.** Results below the threshold, or with contradictions between scores and comments, are held.
- **Answer keys stay on the server** until a test is submitted.
- **Privacy.** Account identity is not sent to the model; requests contain only exam goals, learning text and scores.

Stack: FastAPI, SQLAlchemy 2, Alembic, LangGraph, LangChain (`langchain-openai`, `langchain-core`), Pydantic, React 19, TypeScript, Vite, Tailwind CSS, Recharts, Playwright, Docker Compose with nginx.

---

## 9. Project structure

```
├── backend/
│   ├── main.py              FastAPI app: all REST endpoints
│   ├── agents.py            LangGraph workflows, ProviderAdapter (LOCAL / REAL), quality gate
│   ├── agent_core.py        Per-agent memory and tool sets
│   ├── models.py            Database models
│   ├── schemas.py           Pydantic request and structured-output schemas
│   ├── config.py            Settings loaded from .env
│   ├── content/             Exam-format test bank (IELTS listening/reading/writing/speaking, TOEFL 2026)
│   ├── scoring.py           Objective marking, band conversion, local rubric analyser
│   ├── examiner.py          Speaking-test state machine
│   ├── local_tutor.py       Offline tutor replies
│   ├── notebook.py          Notebooks, tutor memory, dictionary
│   ├── monitoring.py        Teacher console metrics and anomaly detection
│   ├── speech.py            Cloud text-to-speech and transcription
│   ├── onboarding.py        Setup-assistant questions and parsing
│   ├── knowledge.py         Knowledge graph
│   ├── recovery.py          Password reset (on-screen link or SMTP)
│   ├── seed.py              Seeds the instructor, materials and question bank
│   ├── demo_seed.py         Optional sample learner with history
│   ├── scheduled_review.py  Weekly plan adaptation (run by cron / Task Scheduler)
│   └── data/                Bundled ECDICT dictionary subset + licence
├── frontend/
│   ├── src/                 React app (pages, pixel art, exam components, notebooks, teacher console)
│   ├── e2e/                 Playwright browser tests
│   ├── nginx.conf           Production web server config (Docker)
│   └── Dockerfile
├── migrations/              Alembic database migrations
├── tests/                   Backend tests (pytest)
├── scripts/package_source.py  Builds the Canvas zip
├── docs/                    Implementation status, agile evidence, Jira backlog
├── compose.yaml             Docker Compose (backend + frontend on port 8080)
├── Dockerfile.backend
├── requirements.txt
├── .env.example             All settings with safe defaults (copy to .env)
└── ELEC5620_Wed_09-11 Group3.pdf   Stage 1 report
```

See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for how each use case (UC1–UC10) from the Stage 1 report is implemented, and what is still missing.

---

## 10. Configuration reference

All settings live in `.env`; `.env.example` lists every one of them with defaults.

| Variable | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | `xxx` | Your OpenAI key. `xxx` or empty = LOCAL mode. |
| `OPENAI_BASE_URL` | empty | Another OpenAI-compatible endpoint (empty = OpenAI). |
| `LLM_MODEL` | `gpt-6-luna` | Chat/reasoning model. |
| `LLM_REASONING_EFFORT` | `none` | Reasoning effort for fast tasks (chat, examiner, words). |
| `LLM_SCORING_EFFORT` | `low` | Reasoning effort for scoring, plans, reports, quality verdicts. |
| `LLM_USE_RESPONSES_API` | `true` | Use the Responses API (needed for tools + reasoning). |
| `AGENT_TOOL_ROUNDS` | `3` | Maximum tool-call rounds per agent decision. |
| `SERVER_SPEECH` | `true` | Use cloud voice when a key is set; otherwise browser voice. |
| `TTS_MODEL` / `TRANSCRIPTION_MODEL` | `gpt-4o-mini-tts` / `whisper-1` | Cloud speech models. |
| `SPEECH_BASE_URL` | empty | Separate endpoint for speech (empty = same as OpenAI). |
| `LOCAL_STT` / `LOCAL_STT_MODEL` | `true` / `base.en` | Offline speech recognition of spoken answers on the server (faster-whisper). Used when there is no key or the cloud fails, so speaking works even when the browser's online recognition is unavailable. |
| `DEMO_MODE` | `false` | `true` forces LOCAL mode even with a key (used by tests). |
| `QUALITY_THRESHOLD` | `0.70` | Initial confidence threshold (also adjustable in the console). |
| `INSTRUCTOR_EMAIL` / `INSTRUCTOR_PASSWORD` | `instructor@example.com` / `ChangeMe123!` | Teacher account created at startup. |
| `JWT_SECRET` | placeholder | **Change before any public deployment.** |
| `SESSION_DAYS` | `7` | Days a sign-in stays valid. When it expires the app returns to the sign-in page. |
| `DATABASE_URL` | `sqlite:///./elec5620.db` | Database (Docker uses its own volume). |
| `CORS_ORIGINS` | localhost:5173 | Allowed browser origins in development. |
| `PUBLIC_BASE_URL` | `http://localhost:8080` | Used in password-reset links. |
| `PASSWORD_RESET_LINK_ON_SCREEN` | `true` | Show reset links on screen when no mail server is set (local use only). |
| `SMTP_*` | empty | Optional mail server for password-reset emails. |

---

## 11. Testing

```powershell
# Backend: 48 tests (workflows, quality gate, plan adaptation (UC7), instructor review (UC8), agents' memory and tools, notebooks, console, exam lock)
.\.venv\Scripts\python -m pytest tests -q

# Frontend type-check and production build
cd frontend
npm.cmd run build

# Browser end-to-end tests (first time only: npx playwright install chromium)
npm.cmd run test:e2e
```

On macOS/Linux use `.venv/bin/python` and `npm` instead of `npm.cmd`. The end-to-end tests start their own backend (LOCAL mode, separate `e2e.db`) and frontend. GitHub Actions runs the backend and frontend checks on every push (`.github/workflows/ci.yml`).

---

## 12. Canvas submission package

```powershell
.\.venv\Scripts\python scripts\package_source.py
```

This creates `ELEC5620-Stage2-Source.zip` from every file tracked by git. The zip never contains `.env`, databases, recordings or dependencies. It is not committed to the repository; generate it when you submit.

---

### Jira backlog

`docs/jira-backlog.csv` holds the whole backlog: 6 epics (one per area and owner, following the Stage 1 use-case authors), stories with acceptance criteria, tasks and sub-tasks. `scripts/jira_sync.py` creates it in Jira Cloud through the REST API in the CSV order (UC1–UC10 become KAN-1 to KAN-10), with parent links, story points, assignees (the Stage 1 use-case authors; other items stay unassigned), status, and Sprint 1–4 on a Scrum board (otherwise `sprint-N` labels).

1. Create a Jira API token at <https://id.atlassian.com/manage-profile/security/api-tokens> (it starts with `ATATT`).
2. In `.env`, set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` and `JIRA_PROJECT_KEY`.
3. Dry run (checks access, changes nothing): `python scripts/jira_sync.py`
4. Create the issues: `python scripts/jira_sync.py --apply`

Running it again skips issues that already exist (each carries a `bk-<ID>` label). Members without a matching Jira user are named in the description; assign them in Jira.

### Linking work to Jira

The Jira project is connected to this repository with the **GitHub for Jira** app. Any branch, commit or pull request that contains an issue key (for example `KAN-3`) appears in that issue's **Development** panel in Jira.

| What | Convention | Example |
|---|---|---|
| Branch | `KAN-<n>-short-description` | `KAN-3-part3-followups` |
| Commit | Start with the issue key | `KAN-3 Add Part 3 follow-up questions` |
| Pull request title | Start with the issue key | `KAN-3 Speaking Part 3 follow-ups` |

**Smart commits** also update Jira from a commit message, when your git email matches your Jira account email (`git config user.email`):

```
KAN-3 #comment Examiner now asks follow-ups #time 2h #done
```

`#comment` adds a comment, `#time` logs work and `#done` (or any status name such as `#in-progress`) moves the issue.

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| `docker compose` says it cannot connect | Start Docker Desktop and wait until it says it is running. |
| Port 8080 already in use | Stop the other program, or change `"8080:80"` in `compose.yaml` (for example `"8081:80"`). |
| Microphone does nothing | Use Chrome or Edge on `localhost` (or HTTPS) and allow microphone access. You can always type answers. |
| "Speech recognition error: network" | The browser's own recognition service cannot be reached. With `LOCAL_STT=true` (default) answers are recognised offline on the server instead; rebuild with `docker compose up -d --build`. |
| No voice | Check the system volume; the speaker icon in the chat toggles spoken replies. Edge's "Natural" voices sound best in LOCAL mode. |
| "needs a cloud AI model" when generating listening/reading | Add an API key, or use the built-in tests in the **Question bank**. |
| Mock exam returns 409 | Accept a learning plan first. |
| "Your result is being double-checked" | The Quality Manager held it. Sign in as the teacher and resolve it in **Review queue**. |
| Teacher login fails after changing the password in `.env` | The old password is already stored in the database. Reset the data (`docker compose down -v`) or use the old password. |
| "no such table" errors (local development) | Run `python -m alembic upgrade head`. |
| Still in LOCAL mode after adding a key | Check that the key is in `.env` (not `.env.example`), then restart with `docker compose up -d`. |

---

## 14. Limitations and honesty notes

- All scores are **unofficial estimates**, not official IELTS or TOEFL results.
- Confidence values are the model's self-reports, not calibrated probabilities. The instructor adjusts the threshold.
- Pronunciation is never scored from a transcript; there is no acoustic pronunciation scorer.
- All exam content is original and written for this project. Official IELTS samples are linked, not republished.
- Cloud AI and cloud speech need your own API key and cost money per use. LOCAL mode is free.

---

## 15. Credits and licences

- Group 3, ELEC5620 (Wednesday 09–11): Naratorn Pisedtasalasai, Menglu Lin, Yuxuan Tang, Mohamed Azim, Suhani Saha.
- Offline dictionary: a 43,000-entry subset of [ECDICT](https://github.com/skywind3000/ECDICT), MIT licence (`backend/data/ECDICT-LICENSE`).
- Pixel fonts: Pixelify Sans, Press Start 2P and VT323 (Google Fonts, SIL Open Font License).
