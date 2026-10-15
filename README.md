# CertifyAI · Pixel Academy — ELEC5620 Stage 2

An AI-assisted IELTS and TOEFL (2026 format) preparation system with four LangGraph agent roles, a human instructor and a mandatory quality gate, presented as a surreal animated pixel-art world. Your AI companion is a pixel witch (**Luna**) or a pixel boy (**Kai**) — switch any time in **Settings**.

## What you can do

| Area | Features |
|---|---|
| **Listening** | Real exam-format parts with multi-speaker scripts read aloud in distinct voices (IELTS Parts 1–4; TOEFL Choose-a-Response, conversation, announcement, academic talk). Exam mode plays once with reading pauses; practice mode allows pause, replay and 0.8–1.3× speed. Form/note completion, multiple choice, matching. Marked against hidden keys, raw score → band conversion, transcript with highlighted answer evidence. |
| **Reading** | Academic passages with TRUE/FALSE/NOT GIVEN, YES/NO/NOT GIVEN, matching headings, MCQ, sentence/summary completion; TOEFL Complete-the-Words, daily-life and academic passages. Timer, evidence highlighting after marking. |
| **Writing** | Task 1 with rendered bar/line/pie charts, Task 2 essays, TOEFL email and academic discussion. Timer, word count, autosaved drafts, criterion scores, sentence-level corrections, rewrites, revision history with score change. |
| **Speaking** | A live spoken test: the avatar examiner speaks every question aloud, listens through your microphone (hands-free turn-taking), runs Part 1 → Part 2 cue card (1 min prep, 2 min talk) → Part 3, or TOEFL Listen & Repeat + Interview. Session audio is recorded for replay. Feedback on fluency (speech rate, fillers), vocabulary and grammar. Plus **Free talk** voice conversation with corrections. |
| **Mock exam** | Short (~90 min) or full-length (~2 h 45 min) computer-delivered mock with all four sections, persistent timer, autosave, live speaking examiner, per-section scores and detailed review. |
| **Everywhere** | Floating AI companion with voice in/out, question bank with AI task generation, learning plan, analytics, materials, knowledge graph, agent activity trace, instructor review and quality operations. |

## Quick start (Windows PowerShell)

Prerequisites: Python 3.11+ and Node.js 24 LTS.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m backend.seed
.\.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000
```

Second window:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open `http://localhost:5173` in **Chrome or Edge** (needed for microphone speech recognition; Edge's "Natural" voices sound best). Instructor: `instructor@example.com` / `ChangeMe123!` unless changed in `.env`. Optional sample learner data: `python -m backend.demo_seed` (creates `demo.learner@example.com` / `DemoLearner123!`).

## AI engine: local or cloud

- **No API key (default)** — the built-in engine runs fully offline: the curated exam-format test bank (6 IELTS listening parts incl. one complete 4-part test, 3 academic reading passages, 10 writing tasks, 6 full speaking tests, plus a TOEFL 2026 set), a transparent rule-based rubric analyser (length, paragraphing, cohesive devices, lexical diversity, academic vocabulary, sentence complexity, common-error detection with corrections, speech rate and fillers), a scripted examiner that follows the real test structure, and a rule-based tutor for chat. Writing and speaking tasks can be generated from any topic.
- **Cloud AI** — set `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL` for any OpenAI-compatible provider such as DeepSeek) and restart the backend. The model then writes natural conversation, examiner follow-ups, rubric feedback with model answers, and brand-new listening/reading tests on any topic. Generated tests pass the Quality Manager (e.g. every completion answer must appear in the audio script) before use.
- **Voice** — with an OpenAI key, `SERVER_SPEECH=true` uses cloud text-to-speech (distinct voices per speaker, cached) and Whisper transcription. Otherwise the browser's own voices and speech recognition are used automatically.

The header badge and **Settings** show the active engine.

## Architecture and quality invariant

`backend/agents.py` defines the LangGraph `StateGraph` workflows (Coordinator → Quality Manager → release / human wait; Tutor → Assessment & Analytics → Quality Manager). `backend/content/` holds the structured test bank, `backend/scoring.py` objective marking, band conversion and the local analyser, `backend/examiner.py` the speaking-test state machine, `backend/speech.py` server TTS/STT. Answer keys never leave the server before submission.

`result_packages` is the release boundary: learners see a payload only in `RELEASED`. Held results go to the instructor queue. The 0.70 confidence threshold is adjustable in Quality Operations. Confidence values are self-reports, not calibrated probabilities. Scores are **unofficial estimates**; pronunciation is never scored from a transcript. Exam content is original and written for this project; official IELTS samples are linked, not republished.

## Verification

```powershell
.\.venv\Scripts\python -m pytest tests -q
Set-Location frontend
npm.cmd run build
npm.cmd run test:e2e
```

## Docker

```powershell
docker compose up --build
```

Open `http://localhost:8080`. Set `JWT_SECRET`, instructor credentials and (optionally) `OPENAI_API_KEY` in `.env` first.

## Troubleshooting

- **Microphone does nothing**: use Chrome/Edge on `localhost` or HTTPS and allow microphone access. You can always type answers.
- **No voice**: check system volume; the speaker icon in the chat toggles spoken replies. Listening audio always plays.
- **"needs a cloud AI model"** when generating listening/reading: add an API key, or use the built-in tests in the Question bank.
- **409 on mock creation**: accept a learning plan first. **Quality hold**: sign in as the instructor and resolve the case.
- **Database table missing**: run `python -m alembic upgrade head`.
