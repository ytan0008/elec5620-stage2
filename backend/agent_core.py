"""Memory and tools for the four agents (Stage 1 report, sections 1.2 and 7).

Every agent has its own working memory (``agent_memories``): episodes it acted on
and lessons it learned, scoped to a learner or, for the Quality Manager, to the
whole cohort. Memory is recalled into every prompt and can also be searched with
a tool. Each agent gets a tool set for its own module; in REAL mode the model
decides which tools to call, and every call is logged as an agent event for the
developer console. Tools only read data, apart from ``save_memory``, so a model
can never release a result or change a prompt on its own.
"""
import functools
import json
import time
from datetime import datetime, timedelta, timezone
from langchain_core.tools import StructuredTool
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend.models import AgentEvent, AgentMemory, InstructorDecision, Escalation, Material, Plan, ResultPackage, SystemSetting
from backend import content as bank
from backend import notebook
from backend.config import settings
from backend.scoring import find_errors, text_features, LISTENING_BANDS, READING_BANDS, toefl_band

AGENT_NAMES = {"coordinator": "Learning Coordinator", "tutor": "AI Tutor", "assessment": "Assessment & Analytics", "quality": "Quality Manager"}
KEEP_PER_SCOPE = 200
SKILLS = ("writing", "speaking", "reading", "listening")


# ---------------------------------------------------------------- memory

def remember(db: Session, agent: str, user_id: int | None, text: str, kind: str = "episode", data: dict | None = None) -> AgentMemory:
    row = AgentMemory(agent=agent, user_id=user_id, kind=kind, text=text.strip()[:600], data=data or {})
    db.add(row)
    db.flush()
    scope = select(AgentMemory.id).where(AgentMemory.agent == agent, AgentMemory.user_id.is_(None) if user_id is None else AgentMemory.user_id == user_id)
    old = db.scalars(scope.order_by(AgentMemory.id.desc()).offset(KEEP_PER_SCOPE)).all()
    for item in old:
        db.delete(db.get(AgentMemory, item))
    return row


def recall(db: Session, agent: str, user_id: int | None, limit: int = 12, query: str = "", include_cohort: bool = False) -> list[str]:
    """Newest first; lessons outrank episodes; an optional keyword filter narrows the search."""
    conditions = [AgentMemory.agent == agent]
    if include_cohort and user_id is not None:
        conditions.append((AgentMemory.user_id == user_id) | AgentMemory.user_id.is_(None))
    else:
        conditions.append(AgentMemory.user_id.is_(None) if user_id is None else AgentMemory.user_id == user_id)
    rows = db.scalars(select(AgentMemory).where(*conditions).order_by(AgentMemory.id.desc()).limit(300)).all()
    if query:
        words = [w for w in query.lower().split() if len(w) > 2]
        rows = [r for r in rows if any(w in r.text.lower() for w in words)] or rows
    rows = sorted(rows[:max(limit * 3, limit)], key=lambda r: r.kind != "lesson")[:limit]
    return [f"[{r.created_at.date().isoformat() if r.created_at else ''}] {r.text}" for r in rows]


# ---------------------------------------------------------------- shared readers

def score_history(db: Session, user_id: int, skill: str | None = None, limit: int = 8) -> list[dict]:
    rows = db.scalars(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.state == "RELEASED",
                                                  ResultPackage.kind.in_([skill] if skill else list(SKILLS) + ["mock_exam"])).order_by(ResultPackage.id.desc()).limit(limit)).all()
    out = []
    for p in rows:
        payload = p.payload or {}
        out.append({"date": p.created_at.date().isoformat() if p.created_at else "", "kind": p.kind, "estimate": payload.get("estimated_overall"),
                    "criteria": payload.get("criteria") or payload.get("section_scores"), "issues": [c.get("issue") for c in payload.get("comments", [])[:4] if c.get("issue")]})
    return out


def previous_feedback(db: Session, user_id: int, skill: str) -> dict | None:
    p = db.scalar(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.kind == skill, ResultPackage.state == "RELEASED").order_by(ResultPackage.id.desc()))
    if not p:
        return None
    payload = p.payload or {}
    return {"date": p.created_at.date().isoformat() if p.created_at else "", "criteria": payload.get("criteria"), "estimate": payload.get("estimated_overall"),
            "issues": [{"issue": c.get("issue"), "suggestion": c.get("suggestion")} for c in payload.get("comments", [])[:6]], "summary": payload.get("summary")}


BAND_NOTES = {
    "IELTS": {
        "writing": {"task_response": "7: addresses all parts, clear position throughout, extended and supported ideas. 6: all parts addressed though some more fully; relevant position; some ideas under-developed. 5: only partly addresses the task; position unclear at times; limited development.",
                    "coherence": "7: logical progression, range of cohesive devices with some over/under-use, clear central topic per paragraph. 6: coherent overall, cohesion faulty or mechanical at times. 5: some organisation, lack of overall progression, inadequate or overused linkers.",
                    "lexical_resource": "7: sufficient range for flexibility and precision, less common items, awareness of style and collocation, occasional errors. 6: adequate range, attempts less common vocabulary with some inaccuracy. 5: limited range, noticeable errors in spelling/word formation.",
                    "grammar": "7: variety of complex structures, frequent error-free sentences, good control. 6: mix of simple and complex forms, some errors that rarely reduce communication. 5: limited range, attempts complex sentences with frequent errors."},
        "speaking": {"fluency": "7: speaks at length without noticeable effort, some hesitation, flexible discourse markers. 6: willing to speak at length, some loss of coherence from repetition or hesitation. 5: usually maintains flow but relies on repetition and slow speech.",
                     "lexical_resource": "7: flexible vocabulary on a variety of topics, some idiomatic items, effective paraphrase. 6: wide enough to discuss topics at length, paraphrases successfully. 5: manages familiar topics, limited flexibility.",
                     "grammar": "7: range of complex structures with some flexibility, frequent error-free sentences. 6: mix of simple and complex structures, limited flexibility. 5: basic forms reasonably accurate, limited complex structures."},
    },
    "TOEFL": {
        "writing": {"task_fulfillment": "5-6: fully addresses the task with well-elaborated, relevant ideas. 3-4: addresses the task with some elaboration gaps. 1-2: limited or off-task.",
                    "organisation": "5-6: clear progression and connections. 3-4: generally organised with some unclear links. 1-2: hard to follow.",
                    "language_use": "5-6: varied and precise vocabulary and syntax with few errors. 3-4: adequate range, noticeable errors. 1-2: frequent errors obscure meaning."},
        "speaking": {"language_use": "5-6: effective vocabulary and grammar with minor errors. 3-4: limited range, errors sometimes obscure meaning. 1-2: severely limited.",
                     "topic_development": "5-6: sustained, relevant and coherent elaboration. 3-4: relevant but limited development. 1-2: minimal or unconnected content."},
    },
}


# ---------------------------------------------------------------- tool sets

class Toolkit:
    """Builds an agent's tools bound to one database session and learner, and records every call."""

    def __init__(self, db: Session, agent: str, user_id: int | None, exam: str = "IELTS"):
        self.db, self.agent, self.user_id, self.exam = db, agent, user_id, exam
        self.calls: list[dict] = []

    def _wrap(self, fn, name: str, description: str) -> StructuredTool:
        @functools.wraps(fn)  # Keeps fn's signature so the tool's argument schema is inferred from it.
        def run(*args, **kwargs):
            started = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # A failing tool must not break the agent loop.
                result = {"error": type(exc).__name__}
            self.calls.append({"tool": name, "args": {k: str(v)[:80] for k, v in kwargs.items()}, "ms": int((time.perf_counter() - started) * 1000)})
            return result
        return StructuredTool.from_function(func=run, name=name, description=description)

    def call(self, name: str, **kwargs):
        """Run a tool directly (used by the LOCAL engine and by graph nodes)."""
        tool = next(t for t in self.tools() if t.name == name)
        return tool.invoke(kwargs)

    # --- tools shared by every agent
    def _recall(self, query: str = "") -> list[str]:
        return recall(self.db, self.agent, self.user_id, 10, query, include_cohort=True)

    def _save(self, note: str) -> str:
        remember(self.db, self.agent, self.user_id, note, "note", {"by": "model"})
        return "saved"

    def _notebook(self) -> dict:
        s = notebook.stats(self.db, self.user_id)
        return {k: s[k] for k in ("mistakes_by_type", "grammar_issues", "due_words", "counts") if k in s}

    def tools(self) -> list[StructuredTool]:
        common = [self._wrap(self._recall, "recall_memory", "Search this agent's own memory of earlier sessions with the learner (and cohort lessons). Optional keyword query."),
                  self._wrap(self._save, "save_memory", "Store one short durable note in this agent's memory for future sessions (e.g. an observed pattern). Use sparingly.")]
        return common + getattr(self, f"_tools_{self.agent}")()

    # --- Learning Coordinator: profile, plans, materials
    def _tools_coordinator(self):
        def plan_history() -> list[dict]:
            plans = self.db.scalars(select(Plan).where(Plan.user_id == self.user_id).order_by(Plan.id.desc()).limit(5)).all()
            return [{"version": p.version, "kind": p.kind, "status": p.status, "priorities": (p.content or {}).get("priorities"), "title": (p.content or {}).get("title")} for p in plans]

        def search_materials(skill: str = "") -> list[dict]:
            rows = self.db.scalars(select(Material).where(Material.exam == self.exam, *( [Material.skill == skill] if skill else []))).all()
            return [{"id": m.id, "title": m.title, "skill": m.skill, "level": m.level, "description": m.description[:160]} for m in rows[:12]]

        def verified_scores(skill: str = "") -> list[dict]:
            return score_history(self.db, self.user_id, skill or None)

        return [self._wrap(plan_history, "get_plan_history", "Earlier learning plans for this learner with their status (accepted, rejected, superseded) and priorities."),
                self._wrap(verified_scores, "get_verified_scores", "Released (quality-checked) results, newest first; optional skill filter."),
                self._wrap(self._notebook, "get_notebook_stats", "Learner's notebook statistics: most frequent wrong question types, grammar issues, words due for review."),
                self._wrap(search_materials, "search_materials", "Study materials in the library for the learner's exam; optional skill filter.")]

    # --- AI Tutor: practice, feedback, vocabulary
    def _tools_tutor(self):
        def last_feedback(skill: str) -> dict | None:
            return previous_feedback(self.db, self.user_id, skill)

        def lookup_word(word: str) -> dict:
            entry = notebook.offline_lookup(word)
            return {"word": word, "phonetic": entry.get("phonetic"), "meanings": entry.get("meanings", [])[:3], "translation": entry.get("translation")} if entry else {"word": word, "found": False}

        def check_grammar(text: str) -> list[dict]:
            return find_errors(text)[:8]

        def measure_text(text: str) -> dict:
            features = text_features(text)
            return {k: v for k, v in features.items() if not isinstance(v, list) or len(v) < 15}

        def question_bank(skill: str, topic: str = "") -> list[dict]:
            items = [i for i in bank.ALL.values() if i["kind"] == skill and i.get("exam", "IELTS") == self.exam]
            if topic:
                items = [i for i in items if topic.lower() in json.dumps(i).lower()] or items
            return [{"id": i["id"], "title": i["title"], "task_type": bank.task_type(i)} for i in items[:8]]

        return [self._wrap(last_feedback, "get_previous_feedback", "The learner's previous released feedback for a skill (criteria and issues), to say which problems were fixed and which remain."),
                self._wrap(self._notebook, "get_notebook_stats", "Mistake book, grammar book and word book statistics for the learner."),
                self._wrap(lookup_word, "lookup_word", "Offline learner dictionary: phonetics, definitions and Chinese meaning of an English word."),
                self._wrap(check_grammar, "check_grammar", "Rule-based grammar checker; returns sentence-level errors with corrections."),
                self._wrap(measure_text, "measure_text", "Objective text measures: word count, lexical diversity, linkers, complex structures, repeated words."),
                self._wrap(question_bank, "search_question_bank", "Exam-format practice items in the bank for a skill (writing, speaking, reading, listening) and optional topic.")]

    # --- Assessment & Analytics: rubrics, conversion, history
    def _tools_assessment(self):
        def descriptors(skill: str) -> dict:
            return BAND_NOTES.get(self.exam, {}).get(skill, {})

        def convert(skill: str, correct: int, total: int = 40) -> float:
            if self.exam == "TOEFL":
                return toefl_band(correct / max(total, 1))
            raw = round(correct * 40 / max(total, 1))
            return next(band for minimum, band in (LISTENING_BANDS if skill == "listening" else READING_BANDS) if raw >= minimum)

        def history(skill: str = "") -> list[dict]:
            return score_history(self.db, self.user_id, skill or None)

        def measure_text(text: str) -> dict:
            features = text_features(text)
            return {k: v for k, v in features.items() if not isinstance(v, list) or len(v) < 15}

        return [self._wrap(descriptors, "get_band_descriptors", "Public band-descriptor summary for each criterion of the learner's exam and the given skill (writing or speaking)."),
                self._wrap(convert, "convert_raw_score", "Convert a listening/reading raw score to an IELTS band or TOEFL 1-6 level."),
                self._wrap(history, "get_score_history", "Learner's released scores by skill, newest first, to judge trends and consistency."),
                self._wrap(measure_text, "measure_text", "Objective text measures used as scoring evidence.")]

    # --- Operations & Quality Manager: thresholds, human decisions, cohort patterns
    def _tools_quality(self):
        def threshold() -> float:
            row = self.db.get(SystemSetting, "quality_threshold")
            return float(row.value) if row else settings().quality_threshold

        def human_decisions(kind: str = "") -> list[dict]:
            rows = self.db.execute(select(InstructorDecision, ResultPackage.kind).join(Escalation, Escalation.id == InstructorDecision.case_id)
                                   .join(ResultPackage, ResultPackage.id == Escalation.package_id).order_by(InstructorDecision.id.desc()).limit(30)).all()
            return [{"kind": k, "decision": d.decision, "note": (d.note or "")[:160], "corrected": list((d.correction or {}).get("criteria", {}) or {})} for d, k in rows if not kind or k == kind][:10]

        def cohort_issue(issue: str) -> dict:
            since = datetime.now(timezone.utc) - timedelta(days=7)
            rows = self.db.scalars(select(ResultPackage).where(ResultPackage.created_at >= since, ResultPackage.kind.in_(["writing", "speaking"]))).all()
            learners = {p.user_id for p in rows if any(issue.lower() in str(c.get("issue", "")).lower() for c in (p.payload or {}).get("comments", []))}
            return {"issue": issue, "learners_7d": len(learners), "results_7d": len(rows)}

        def hold_rate() -> dict:
            since = datetime.now(timezone.utc) - timedelta(days=7)
            total = self.db.scalar(select(func.count()).select_from(ResultPackage).where(ResultPackage.created_at >= since)) or 0
            held = self.db.scalar(select(func.count()).select_from(ResultPackage).where(ResultPackage.created_at >= since, ResultPackage.state.in_(["HELD", "HUMAN_REVIEW"]))) or 0
            return {"results_7d": total, "held_7d": held}

        return [self._wrap(threshold, "get_quality_threshold", "The instructor's current confidence threshold for releasing results."),
                self._wrap(human_decisions, "get_instructor_decisions", "Recent human-instructor decisions on escalated results (approve, correct, request information) to learn from earlier false alarms and corrections."),
                self._wrap(cohort_issue, "count_cohort_issue", "How many learners received the same feedback issue in the last 7 days (curriculum-gap detection)."),
                self._wrap(hold_rate, "get_hold_rate", "Number of results produced and held in the last 7 days.")]

    def log(self, workflow: str, mode: str) -> None:
        """Write the recorded tool calls as agent events and clear them."""
        for call in self.calls:
            self.db.add(AgentEvent(user_id=self.user_id, workflow=workflow, agent=AGENT_NAMES[self.agent], phase="tool", detail=call, mode=mode, duration_ms=call["ms"]))
        self.calls = []
        self.db.flush()

