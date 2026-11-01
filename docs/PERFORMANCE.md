# Advanced technologies and measured performance

Measured on 1 November 2026 on one laptop (Intel Core i9-14900HX, 24 GB RAM, Windows 11) with the built-in LOCAL engine. The cloud model (GPT-6 Luna) was not measured because no API key was available for the test run. Each figure comes from `scripts/benchmark.py`, from the Docker deployment or from the CI history, as noted. Timings vary between runs on the same machine: an earlier run of the same script while other programs were busy was about 1.5–2 times slower.

## Technologies and what each one does for the system

| # | Technology | Where | What it improves | Evidence |
|---|---|---|---|---|
| 1 | **React 19 + TypeScript + Vite + Tailwind CSS** | `frontend/` | One typed single-page app for learners and the teacher; type errors are caught at build time; the production build is static files served by nginx | The type-check and build run in CI on every push; the built JavaScript is 0.96 MB |
| 2 | **FastAPI + Pydantic + SQLAlchemy 2 + Alembic** | `backend/`, `migrations/` | Validated request and AI output schemas, versioned database migrations that upgrade an existing database without data loss | API latency table below; Alembic upgrades run at every container start |
| 3 | **LangGraph + LangChain multi-agent workflows** | `backend/agents.py`, `agent_core.py` | Four agents with their own memory and tools, explicit hand-offs and a quality gate before anything reaches the learner | Each agent records its own step times (table below); every hand-off is visible in the teacher console |
| 4 | **OpenAI GPT-6 Luna through the Responses API with tool calling** | `backend/agents.py`, `config.py` | Conversation, examiner follow-ups, rubric feedback and new tests in REAL mode, with a bounded tool-calling loop and a final structured-result tool | Configured but not live-tested (no key); every result still passes the same quality gate as LOCAL mode |
| 5 | **Local AI model: offline Whisper speech recognition** (faster-whisper `base.en`, int8 on the CPU) | `backend/speech.py` | Spoken answers are recognised on our own server, without the browser's online service or a cloud key, so speaking practice works offline and recordings stay private | Speed and accuracy tables below |
| 6 | **Microphone devices in the browser** (MediaRecorder, Web Audio level metering, Web Speech API) | `frontend/src/voice.ts`, `exam/SpeakingStudio.tsx` | Hands-free spoken tests: the answer is sent after a pause, with a live microphone level and session recording for replay | Checked in a real browser with a fake microphone (Playwright) |
| 7 | **Docker Compose + nginx** | `compose.yaml`, `Dockerfile.*` | One command builds and runs the whole system; the speech model is built into the image so the first recognition needs no download | Start-up and first-recognition figures below |
| 8 | **CI/CD: GitHub Actions + Playwright end-to-end tests, linked to Jira** | `.github/workflows/ci.yml`, `frontend/e2e/` | Every push runs 76 backend tests, the frontend build and 3 browser tests; branch, commit and pull request names carry Jira keys, so Jira shows the code for each story | CI timings below |

## Offline speech recognition

Three spoken answers in an IELTS style (Part 1, Part 3 and a Part 2 long turn), produced with the Windows speech synthesiser from known text so that accuracy can be measured. Real learners' accented speech will give a higher error rate than this clean voice.

| Answer | Audio length | Recognition time (warm) | Real-time factor | Word error rate |
|---|---|---|---|---|
| Part 1 answer | 6.1 s | 0.70 s | 0.11 | 0 % |
| Part 3 answer | 8.0 s | 0.70 s | 0.09 | 0 % |
| Part 2 long turn | 15.6 s | 0.75 s | 0.05 | 0 % |

A real-time factor of 0.05–0.11 means a two-minute Part 2 answer is recognised in a few seconds on a CPU, without a GPU.

**Model in the Docker image.** The first recognition after start-up took **0.71 s** in the Docker deployment, where the model is built into the image and loaded when the server starts. In the development setup, where the model is loaded on the first request, the first recognition took **12.6 s** (21.6 s in the busier run).

## Other requests stay responsive during recognition

Recognition is CPU-heavy. It now runs in a worker thread (`run_in_threadpool`), so the server keeps answering other learners. While the Part 2 answer was being recognised, the health check was requested every 50 ms:

| | Median | 95th percentile | Maximum |
|---|---|---|---|
| Health check during recognition (14 requests) | 3.6 ms | 4.5 ms | 12.4 ms |

Before this change, recognition ran on the server's event loop, so every other request waited for the whole recognition (0.8 s for this answer, longer for a two-minute answer).

## API response times (LOCAL engine, real HTTP on the same machine)

| Request | What runs | Median | 95th percentile |
|---|---|---|---|
| `GET /api/me` (30 requests) | Authentication and one query | 3.9 ms | 4.5 ms |
| Tutor chat reply (10) | AI Tutor with memory and tools | 11.1 ms | 12.1 ms |
| Learning plan (5) | Coordinator → Assessment insights → Quality gate | 26.0 ms | 29.1 ms |
| Writing submission (10) | Tutor feedback → Assessment scoring → Quality gate → release | 62.3 ms | 63.5 ms |
| Performance analytics (10) | Assessment & Analytics over all verified results | 12.1 ms | 12.6 ms |
| Saved report (5) | Assessment report writing and quality check | 25.7 ms | 27.0 ms |
| Prepare a mock exam (3) | Assessment prepares four sections | 35.1 ms | 35.7 ms |

## Agent step times

Each agent records how long its own steps take (`agent_execution_events.duration_ms`, also shown per agent in the teacher console). From the same run:

| Agent | Steps | Median | 95th percentile |
|---|---|---|---|
| AI Tutor | 17 | 19 ms | 21 ms |
| Assessment & Analytics | 25 | 1 ms | 10 ms |
| Learning Coordinator | 6 | 4 ms | 4 ms |
| Quality Manager | 21 | 3 ms | 4 ms |

## Deployment and delivery

| Measure | Result | Source |
|---|---|---|
| Backend ready after start (migrations already applied) | 2.8 s | `scripts/benchmark.py` |
| Docker backend restart until healthy | 7.0 s | `docker compose restart backend` |
| Image sizes | backend 1.33 GB (includes the speech model), frontend 95 MB | `docker images` |
| Backend test suite | 76 tests in about 23 s | `pytest tests -q` |
| Full CI run (backend tests, frontend build, browser tests) | about 1.5–2 minutes | GitHub Actions history, 31 October 2026 |

## Reproducing the measurements

```powershell
.\.venv\Scripts\python scripts\benchmark.py <audio-folder>
```

The audio folder holds `clip1.wav` … with the spoken text in `clip1.txt` …. Ours were made with the Windows speech synthesiser (`System.Speech.Synthesis.SpeechSynthesizer`, default voice, rate 0). The script uses a fresh database in the system temp folder and port 8010, so it does not touch a running deployment.
