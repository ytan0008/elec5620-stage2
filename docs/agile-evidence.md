# Sprint reviews and retrospectives

Drafted from what the GitHub repository shows: commits, pull requests and CI runs on `ytan0008/elec5620-stage2`. Anything that happened outside GitHub (Jira board changes, meetings, chat, the Stage 1 report) isn't visible there, so each member should add their part where it says **Group to add**. Don't add anything that didn't happen.

Dates are Sydney time. People are shown by GitHub account; match them to names in the contribution statement. The correct name is **Menglu Lin** (as in the Stage 1 report).

The CSV backlog (`docs/jira-backlog.csv`) is an import aid, not a record of Jira work completed.

---

## Sprint 1 · 5–11 October

### Sprint review

- Planned: registration, profiles, database schema and acceptance criteria.
- Shown: nothing in the repository yet. The first commit is on 15 October.
- Tests: none yet (CI started with the first commit).
- **Group to add:** what was worked on this week (for example the Stage 1 report or presentation), Jira screenshots, who reviewed what.

### Retrospective

- **Group to add.** One fact from the record: none of this sprint's planned stories reached the repository during the sprint.

---

## Sprint 2 · 12–18 October

### Sprint review

- First working increment, 15–17 October:
  - The full app: FastAPI backend, React frontend, Docker Compose and GitHub Actions CI, with an offline (LOCAL) engine so it runs without an API key. Built by ytan0008 (27 of the 28 commits from 15 to 17 October).
  - PR #1 (bluepheonix9, 16 October): the agents split into the Stage 1 class-diagram classes (abstract `Agent`, the four agents, the `LLMService` interface, the `ResultStatus` enum) and the missing UC9 and UC10 flows. Merged the same day.
  - Jira set up: backlog CSV and REST sync script (issues KAN-1 to KAN-10 for UC1–UC10), GitHub for Jira linking, branch and commit conventions, and a pull request template (KAN-35).
  - KAN-1 seven-day sign-ins (PR #2): merged and reverted on 17 October, then reopened as PR #6.
  - KAN-5 and KAN-6 (PRs #4 and #5): opened and closed on 17 October, later combined into PR #8.
  - KAN-3: offline speech recognition (Whisper) on the server.
- Tests: 20 backend tests and 3 Playwright browser tests passed on 16 October (`docs/IMPLEMENTATION_STATUS.md`).
- CI: the first push failed (backend: `ModuleNotFoundError: No module named 'backend'`) and was fixed in the next commit. The main browser test timed out on a click on 15 and 17 October.
- **Group to add:** Jira sprint board or burndown screenshot, and who accepted which stories.

### Retrospective

- What helped: CI ran on every push, and the offline engine meant everyone could run the app without a key.
- What slowed or broke integration: most of the first increment came from one account in about two days, so other members' work joined later. PR #2 was merged and reverted on the same day.
- Quality issue: the end-to-end browser test timed out on 15 and 17 October (CI runs 38760004147 and 38998857714).
- Action for next sprint, owner, due date: **Group to add.**
- Did the previous action help? There was no recorded action from Sprint 1.

---

## Sprint 3 · 19–25 October

### Sprint review

- No commits or pull requests in the repository this week.
- **Group to add:** what was worked on (for example preparing UC7 and UC8, other coursework, Jira grooming), with evidence.

### Retrospective

- **Group to add.** One fact from the record: the repository was idle for 10 days (18–27 October).

---

## Sprint 4 · 26 October–1 November

### Sprint review

- 28 October:
  - UC7 adapted learning plan (KAN-7, PR #7). Commit by mmoh0605, merged by IamPeterPan two minutes after it was opened. 38 backend tests passed, including 11 for UC7, one per spec flow.
  - UC5 and UC6 mock exam, Assessment agent and full reports (KAN-5 and KAN-6, PR #8) by ytan0008, including the KAN-3 speech recognition work.
- 29 October: UC8 instructor review of escalated cases (KAN-8, PR #9). Commit by mmoh0605, opened and merged by IamPeterPan two minutes apart. 48 backend tests passed, including 10 for UC8.
- 31 October:
  - bluepheonix9 merged PRs #3 (Jira backlog) and #6 (seven-day sign-ins), which had been open since 17 October.
  - PR #10 (KAN-9) by bluepheonix9: UC9 retries the LLM once before the rule-based checks, as in the Stage 1 spec, plus a README table mapping every use case and class to the code. Merged by ytan0008.
  - bluepheonix9 checked UC1–UC8 against the Stage 1 use case specs, resolved PR #8's conflicts with `main`, and opened PR #11 (KAN-5: two bugs when a teacher releases a held mock) and PR #12 (KAN-3, KAN-4, KAN-6: retry and "temporarily unavailable" flows, the word-minimum choice, the report page's Try again, and an updated status document).
  - With `main`, #8, #11 and #12 combined: 69 backend tests and all 3 browser tests pass, and the frontend builds.
  - bluepheonix9 merged PRs #8, #11 and #12 once their checks passed (`main` at `e89bd4b`). A Canvas-style zip built from `main` with `scripts/package_source.py` (110 files) passes all 69 backend tests after unzipping, and `docker compose up --build` from the unzipped copy built and started the app in about 5 minutes from scratch (sign-in page on port 8080, offline engine, offline speech recognition on).
  - First test of cloud AI mode (`gpt-6-luna`, OpenAI key in a local `.env` only). The Learning Coordinator called four of its tools (plan history, notebook statistics, materials search for writing and speaking) before proposing a plan, which the Quality Manager held for the teacher because the model's confidence was below 0.7. The AI Tutor's writing feedback noticed that the essay answered a different question (Task Response 2), and the Quality Manager released it after an LLM consistency check.
- **Group to add:** Jira sprint board or burndown screenshot, and who accepted which stories.

### Retrospective

- What helped: one branch and pull request per use case, named with its Jira key; one test file per use case with one test per spec flow (`test_uc7.py`, `test_uc8.py`, `test_uc9_uc10.py`); checking the code against the Stage 1 specs found two real bugs (PR #11).
- What slowed or broke integration: PR #8 waited three days and picked up conflicts after PR #9 was merged; PRs #3 and #6 stayed open for 14 days; no pull request had a review comment, and PRs #7 and #9 were merged by their author within two minutes of opening.
- Quality issues:
  - The same browser test timed out on a click again (main after PR #7, run 40620767247; PR #10, which passed on a re-run). Across the project this click timeout appeared in four CI runs (15, 17, 28 and 31 October).
  - PR #12 first broke the browser test, because the new word-minimum step changed the writing flow. The test was updated to follow the new step.
  - Cloud AI mode was first tried on 31 October, the day before submission. Until then every demo and test ran on the offline engine.
- Action, owner, due date: **Group to add.** Suggestion from the record: one teammate reviews each pull request before it's merged.
- Did the previous action help? **Group to add.**

---

## Original sprint plan (from the backlog)

1. 5–11 October: registration, profiles, database schema and acceptance criteria.
2. 12–18 October: plan and practice vertical path with instructor-visible quality hold.
3. 19–25 October: four-section mock, reports, adaptation and materials.
4. 26 October–1 November: live deployment rehearsal, browser tests, bug fixes and evidence packaging.
