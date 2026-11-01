"""Transparent heuristics for personalising original speaking/writing practice.

The preference map is project-authored guidance based on task structure and
topic familiarity, not an official IELTS/TOEFL difficulty classification or a
validated measure of learner ability. All tasks retain their exam format.
"""
import math
import random
import re
from collections import defaultdict

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from backend import content as bank
from backend.models import Escalation, InstructorDecision, Material, MockExam, Plan, Practice, ResultPackage, Submission

# Each item lists suggested profiles and practice opportunities. These are
# deliberately explicit and auditable: an unknown/new item is never assigned an
# invented difficulty or focus. TOEFL keys match its distinct rubric.
PREFERENCES = {
    "ielts-writing-t1-library": ("beginner intermediate", "grammar lexical_resource coherence"),
    "ielts-writing-t1-commute": ("beginner intermediate", "grammar lexical_resource coherence"),
    "ielts-writing-t1-energy": ("intermediate advanced", "task_response lexical_resource coherence"),
    "ielts-writing-t1-spending": ("intermediate advanced", "task_response lexical_resource coherence"),
    "ielts-writing-t2-remote": ("beginner intermediate", "task_response grammar coherence"),
    "ielts-writing-t2-transport": ("beginner intermediate", "task_response grammar coherence"),
    "ielts-writing-t2-university": ("intermediate advanced", "task_response coherence lexical_resource"),
    "ielts-writing-t2-green": ("intermediate advanced", "task_response coherence lexical_resource"),
    "ielts-writing-t2-ai": ("advanced", "task_response coherence lexical_resource"),
    "ielts-writing-t2-tourism": ("advanced", "task_response coherence lexical_resource"),
    "ielts-speaking-0": ("beginner intermediate", "fluency grammar"),
    "ielts-speaking-1": ("beginner intermediate", "fluency grammar"),
    "ielts-speaking-2": ("beginner intermediate", "fluency grammar"),
    "ielts-speaking-3": ("beginner intermediate", "fluency grammar"),
    "ielts-speaking-4": ("intermediate advanced", "fluency lexical_resource"),
    "ielts-speaking-5": ("intermediate advanced", "fluency lexical_resource"),
    "toefl-writing-email": ("beginner intermediate", "language_use task_fulfillment"),
    "toefl-writing-discussion": ("intermediate advanced", "task_fulfillment organisation"),
    "toefl-speaking-campus": ("intermediate advanced", "topic_development"),
    "toefl-speaking-volunteer": ("beginner intermediate", "language_use"),
    "toefl-speaking-transport": ("intermediate advanced", "topic_development"),
}

VALID_CRITERIA = {
    ("IELTS", "writing"): {"task_response", "coherence", "lexical_resource", "grammar"},
    ("IELTS", "speaking"): {"fluency", "lexical_resource", "grammar"},
    ("TOEFL", "writing"): {"task_fulfillment", "organisation", "language_use"},
    ("TOEFL", "speaking"): {"language_use", "topic_development"},
}


def _recent_evidence(db: Session, user_id: int, exam: str, skill: str, target_score: float, limit: int = 5):
    """Use only this learner's released, same-exam, same-skill submissions."""
    valid = VALID_CRITERIA.get((exam, skill), set())
    if not valid:
        return [], 0
    minimum, maximum = (0, 9) if exam == "IELTS" else (1, 6)
    practice_rows = db.execute(
        select(ResultPackage.id, ResultPackage.payload)
        .join(Submission, Submission.package_id == ResultPackage.id)
        .join(Practice, Practice.id == Submission.practice_id)
        .where(ResultPackage.user_id == user_id, Submission.user_id == user_id, Practice.user_id == user_id,
               Practice.exam == exam, Practice.skill == skill, ResultPackage.kind == skill,
               ResultPackage.state == "RELEASED")
        .order_by(Submission.id.desc()).limit(limit)
    ).all()
    # A teacher can override only the section score while older criterion
    # details remain unchanged. Ignore corrected mocks until those details are
    # recomputed, rather than treating stale feedback as verified evidence.
    corrected = exists(select(InstructorDecision.id).join(Escalation, InstructorDecision.case_id == Escalation.id).where(
        Escalation.package_id == ResultPackage.id, InstructorDecision.decision == "correct"))
    mock_rows = db.execute(select(ResultPackage.id, ResultPackage.payload)
        .join(MockExam, MockExam.package_id == ResultPackage.id)
        .where(MockExam.user_id == user_id, MockExam.exam == exam, ResultPackage.user_id == user_id,
               ResultPackage.kind == "mock_exam", ResultPackage.state == "RELEASED", ~corrected)
        .order_by(ResultPackage.id.desc()).limit(limit)).all()
    rows = sorted([(row.id, row.payload, False) for row in practice_rows] +
                  [(row.id, row.payload, True) for row in mock_rows], key=lambda row: row[0], reverse=True)[:limit]
    scores = defaultdict(list)
    usable = 0
    for _, payload, is_mock in rows:
        if not isinstance(payload, dict):
            continue
        scale = str(payload.get("score_scale") or "").upper()
        if ("IELTS" in scale and exam != "IELTS") or ("TOEFL" in scale and exam != "TOEFL"):
            continue
        if is_mock:
            details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
            section = details.get(skill)
            if not isinstance(section, dict):
                continue
            outputs = [section] if skill == "speaking" else [value for value in section.values() if isinstance(value, dict)]
        else:
            outputs = [payload]
        per_result = defaultdict(list)
        for output in outputs:
            criteria = output.get("criteria")
            if not isinstance(criteria, dict):
                continue
            for key, value in criteria.items():
                if key in valid and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and minimum <= value <= maximum:
                    per_result[key].append(float(value))
        for key, values in per_result.items():
            scores[key].append(sum(values) / len(values))
        usable += int(bool(per_result))
    means = {key: sum(values) / len(values) for key, values in scores.items()}
    # A criterion is not called weak merely because it is relatively lowest:
    # it must be below the learner's stated target on the same exam scale.
    weak = sorted((key for key, value in means.items() if value < target_score), key=lambda key: (means[key], key))
    return weak, usable


def recent_weaknesses(db: Session, user_id: int, exam: str, skill: str, target_score: float) -> list[str]:
    return _recent_evidence(db, user_id, exam, skill, target_score)[0]


def active_plan_context(db: Session, user_id: int, exam: str, skill: str) -> dict:
    """Read only an accepted plan whose result has actually been released."""
    plan = db.scalar(select(Plan).join(ResultPackage, Plan.package_id == ResultPackage.id).where(
        Plan.user_id == user_id, Plan.status == "ACTIVE", ResultPackage.user_id == user_id,
        ResultPackage.state == "RELEASED").order_by(Plan.id.desc()))
    if not plan or not isinstance(plan.content, dict):
        return {"active": False, "skill_priority": False, "focus": [], "task": None}
    content = plan.content
    plan_exam = content.get("exam")
    if not plan_exam:
        # Legacy plans predate the exam field; linked catalogue materials are
        # valid provenance only when all surviving material IDs have one exam.
        resources = content.get("resources") if isinstance(content.get("resources"), list) else []
        ids = [r["material_id"] for r in resources if isinstance(r, dict) and isinstance(r.get("material_id"), int)]
        rows = db.scalars(select(Material).where(Material.id.in_(ids))).all() if ids else []
        exams = {material.exam for material in rows}
        if ids and len(rows) == len(set(ids)) and len(exams) == 1:
            plan_exam = next(iter(exams))
    if plan_exam != exam:
        return {"active": False, "skill_priority": False, "focus": [], "task": None}
    priorities = content.get("priorities") if isinstance(content.get("priorities"), list) else []
    activities = [a for a in content.get("activities", []) if isinstance(a, dict) and a.get("skill") == skill] if isinstance(content.get("activities"), list) else []
    text = " ".join(str(a.get(k, "")) for a in activities for k in ("title", "reason")).lower()
    aliases = {"fluency": ("fluency", "fluent"), "grammar": ("grammar", "grammatical"),
               "lexical_resource": ("vocabulary", "lexical"), "coherence": ("coherence", "cohesion"),
               "task_response": ("task response",), "task_fulfillment": ("task fulfillment", "task fulfilment"),
               "organisation": ("organisation", "organization"), "language_use": ("language use",),
               "topic_development": ("topic development",)}
    focus = [key for key, words in aliases.items() if key in VALID_CRITERIA.get((exam, skill), set()) and any(w in text for w in words)]
    task1 = bool(re.search(r"\btask\s*1\b", text))
    task2 = bool(re.search(r"\btask\s*2\b", text))
    task = "task1" if task1 and not task2 else "task2" if task2 and not task1 else None
    return {"active": True, "skill_priority": skill in priorities or bool(activities), "focus": focus, "task": task}


def select_question(exam: str, skill: str, avoid: set[str] | None, proficiency: str,
                    weak_criteria: list[str], rng: random.Random | None = None,
                    plan_focus: dict | None = None, evidence_count: int = 0):
    """Prefer unseen compatible tasks; rank with documented, uncalibrated rules."""
    rng = rng or random.Random()
    pool = {"writing": bank.WRITING, "speaking": bank.SPEAKING}[skill]
    items = [item for item in pool.values() if item.get("exam") == exam]
    if not items:
        raise ValueError("No practice questions available for the selected exam and skill")
    fresh = [item for item in items if item["id"] not in (avoid or set())]
    candidates = fresh or items
    plan_focus = plan_focus or {}
    allowed = VALID_CRITERIA.get((exam, skill), set())
    verified_focus = next((key for key in weak_criteria if key in allowed), None)
    plan_criterion = next((key for key in plan_focus.get("focus", []) if key in allowed), None)
    focus = verified_focus or plan_criterion
    plan_task = plan_focus.get("task")
    def score(item):
        levels, tags = PREFERENCES.get(item["id"], ("", ""))
        return (3 if proficiency in levels.split() else 0) + (8 if focus and focus in tags.split() else 0) + (2 if plan_task and item.get("task") == plan_task else 0)
    best = max(score(item) for item in candidates)
    item = rng.choice([candidate for candidate in candidates if score(candidate) == best])
    levels, tags = PREFERENCES.get(item["id"], ("", ""))
    notes = []
    if proficiency in levels.split():
        notes.append(f"A project-authored task preference matches your self-reported {proficiency} level")
    else:
        notes.append(f"The selected question has no preference tag for your self-reported {proficiency} level")
    if verified_focus:
        if verified_focus in tags.split():
            notes.append(f"it provides practice for {verified_focus.replace('_', ' ')}, an area below your target in recent released results")
        else:
            notes.append(f"no remaining tagged question matched your recent {verified_focus.replace('_', ' ')} focus")
    elif plan_criterion:
        notes.append(f"your active plan mentions {plan_criterion.replace('_', ' ')}" + (" and this task is tagged for that practice" if plan_criterion in tags.split() else ", but no matching tagged question remained"))
    elif plan_focus.get("active") and plan_focus.get("skill_priority"):
        notes.append(f"your active plan includes {skill}; it does not specify a criterion to target")
    elif not plan_focus.get("active"):
        notes.append("no released active plan with verified exam provenance was available for additional guidance")
    if plan_task and item.get("task") == plan_task:
        notes.append(f"your active plan specifically mentions {plan_task.replace('task', 'Task ')}")
    if not verified_focus:
        notes.append("no recent released criterion below your target was available")
    if not fresh:
        notes.append("all available questions were previously seen, so a question was repeated")
    return item, {"rationale": "; ".join(notes) + ". These preferences are heuristic, not official difficulty levels.",
                  "profile_level": proficiency, "focus": focus, "evidence_count": evidence_count,
                  "variety": "unseen" if fresh else "repeat",
                  "fallback": "repeat" if not fresh else "no_focus_match" if focus and focus not in tags.split() else "no_matching_tags" if not best else None}
