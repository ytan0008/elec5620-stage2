# Stage 1 to Stage 2 implementation status

Source: `ELEC5620_Wed_09-11 Group3.pdf`, especially use case specifications on pages 25–37 and UC9 states on page 47. The implementation follows the four agent roles and the human founder. Stage 1 assumes model confidence is calibrated; this prototype explicitly treats it as an uncalibrated model self-report. TOEFL scoring was updated in January 2026, so this implementation uses the new 1–6 scale.

| Use case | Implemented and verified | Remaining gap |
|---|---|---|
| UC1 Register/profile | Learner registration, hashed password, validation, persisted profile editing, role checks, one-time 30-minute password reset, SMTP delivery in real mode and labelled on-screen demo link; API and Playwright coverage | Email verification and persistent recovery rate limits |
| UC2 Plan | Coordinator StateGraph, rationale, activities, requested changes, acceptance/rejection, active plan and tasks; API/Playwright coverage | Extensive plan quality evaluation |
| UC3 Speaking | Prompt, timer, browser recording/upload and replay, manual transcript, text feedback, attempts, quality gate; API coverage | No speech pronunciation scorer; real transcription requires configured provider |
| UC4 Writing | Prompt, timer, word counter, browser draft, submission, criterion feedback, revision history and score delta, quality gate; API/Playwright coverage | Comparative prose diff and streaming comments |
| UC5 Mock | Four-section reduced prototype, save/resume, completeness check, distinct exam score scales, quality gate; API coverage | Full-length exam/audio listening and validated scoring rubrics |
| UC6 Reports | Recharts skill/history charts, verified-only aggregation, weak/strong skills, repeated issue counts, saved quality-checked reports; API coverage | Predictive model calibration; more granular error taxonomy |
| UC7 Adaptation | Manual and scheduler-compatible weekly trigger, progress-aware proposal, acceptance/rejection preserving active plan; API coverage | Automatic scheduler deployment and resource-level change explanations |
| UC8 Human review | Queue, evidence, confidence, decisions, correction, further-info state, decision history and audit; API coverage | Multi-instructor assignment and notification delivery |
| UC9 Quality | Structured, instructor-adjustable threshold, required-field, range, rule/LLM consistency checks; one bounded retry, durable hold/release and audit; API/Playwright coverage | Empirical false positive/false negative evaluation |
| UC10 Materials | Seeded catalog, filters, detail viewer, relevance tracking, ranking, quality-checked recommendations; API coverage | Larger curated library and efficacy measurement |

Other architecture: SQLAlchemy models and Alembic migrations; FastAPI bearer auth with password-reset session revocation; LangChain shared provider adapter; LangGraph conditional edges; persisted workflow events; Docker Compose; GitHub Actions; `.env.example`; reproducible demo data. See README for commands and current verification results.

Clean-source rehearsal on 14 October 2026: extracted the generated source ZIP into a separate directory, applied both Alembic migrations, seeded instructor/material/demo records, created a fresh Python virtual environment from `requirements.txt`, passed 6 backend tests, ran `npm ci`, and built the frontend. The workspace browser suite passed 2 tests. Docker Compose was subsequently built and launched on Docker Desktop: both containers stayed up, the homepage returned HTTP 200, `/api/health` returned `{"status":"ok","mode":"DEMO"}`, demo data was seeded inside the backend container, and demo learner login succeeded through the nginx proxy. Live LLM mode remains untested because provider credentials were not supplied. `npm audit --omit=dev` reported zero production dependency advisories; the full audit reported seven advisories in development dependencies, mainly the Tailwind 3 toolchain.

Password recovery increment on 15 October 2026: applied migration `c32c9f81d2aa` to the local and persistent Docker databases, passed 9 backend tests and 3 browser tests, rebuilt both Docker images, and completed register → demo reset link → new password login through `localhost:8080`. SMTP delivery was verified with a test double; an external SMTP service has not been live tested. The new frontend build passed TypeScript and Vite checks.

Quality invariant: learners receive a generated `payload` only if its result package state is `RELEASED`. Reports and plans also pass the quality service. Instructor evidence is role restricted. The current model-based scores and readiness are prototype estimates, never official IELTS or TOEFL results.
