"""UC7 Receive Adapted Learning Plan Based on Progress (Stage 1 report, UC7).

Flow, with the Stage 1 alternate and exception flow numbers:
  trigger (weekly review | learner request | major assessment, UC5)
  -> 3a  not enough verified evidence: keep the existing plan and tell the learner
  -> the Learning Coordinator compares recent progress with the current priorities
  -> 4a  the LLM proposes an adapted plan with a rationale for each major change; one retry, then keep the existing plan
  -> 5a  the Coordinator selects resources; an area with no suitable material is shown without a recommendation
  -> the plan passes the Quality Manager (UC9) and is shown to the learner
  -> 6a/7a  the learner requests changes, confirms or rejects (routes in main.py)
  -> 8a  on confirmation the plan is activated and the other agents are notified; a failed delivery is logged and retried

This module holds the parts that do not belong to one agent. It imports ``AgentRuntime`` lazily because
``agents.py`` imports this module for the helpers the Coordinator uses.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend import agent_core
from backend.config import settings
from backend.materials import MaterialLibrary
from backend.models import AgentEvent, AuditLog, Plan, ResultPackage

MIN_ASSESSMENTS = 2        # "the learner has completed multiple assessments" (UC7 precondition)
FOCUS = 2                  # the top priorities that count as the learner's current focus
MINUTES_SHIFT = 0.2        # a weekly-minutes change of at least 20% is a major change
RESOURCES_PER_PLAN = 3
NOTIFY_ATTEMPTS = 3
RECIPIENTS = {"tutor": "AI Tutor", "assessment": "Assessment & Analytics"}
TRIGGERS = ("learner_request", "weekly_review", "major_assessment")

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
GENERATION_FAILED = "GENERATION_FAILED"
NOTICES = {
    INSUFFICIENT_DATA: "There isn't enough verified assessment data yet to justify changing your plan. Complete another practice session or a mock exam; your current plan stays active.",
    GENERATION_FAILED: "Your adapted plan couldn't be generated right now, so your current plan stays active.",
}


# ---------------------------------------------------------------- 4 / 5: what changed and why

def describe_changes(old: dict, new: dict, progress: dict, target: float | None) -> list[dict]:
    """Compare the active plan with the proposed one. A major change is a skill that enters or leaves the top
    priorities or whose weekly minutes move by 20% or more. The facts (ranks, minutes) are computed here;
    the model only supplies the wording of the reason."""
    old_order, new_order = old.get("priorities", []), new.get("priorities", [])
    minutes_before = {a["skill"]: a.get("minutes_per_week", 0) for a in old.get("activities", [])}
    minutes_after = {a["skill"]: a.get("minutes_per_week", 0) for a in new.get("activities", [])}
    scores = progress.get("skill_scores", {})
    changes = []
    for skill in dict.fromkeys(new_order + old_order):
        was = old_order.index(skill) + 1 if skill in old_order else None
        now = new_order.index(skill) + 1 if skill in new_order else None
        before, after = minutes_before.get(skill, 0), minutes_after.get(skill, 0)
        focus_changed = (was is not None and was <= FOCUS) != (now is not None and now <= FOCUS)
        minutes_changed = after != before and (not before or abs(after - before) / before >= MINUTES_SHIFT)
        if not (focus_changed or minutes_changed):
            continue
        direction = "raised" if after > before else "lowered" if after < before else "reordered"
        changes.append({"skill": skill, "change": direction, "from_priority": was, "to_priority": now,
                        "minutes_before": before, "minutes_after": after, "reason": _reason(skill, direction, scores, target)})
    return changes


def _reason(skill: str, direction: str, scores: dict, target: float | None) -> str:
    if skill not in scores:
        return f"You have no verified {skill} results yet, so its time follows your own priorities."
    score = scores[skill]
    if target is not None and score < target:
        evidence = f"Your verified {skill} average is {score:g}, {target - score:g} below your target of {target:g}"
    elif target is not None:
        evidence = f"Your verified {skill} average is {score:g}, at or above your target of {target:g}"
    else:
        evidence = f"Your verified {skill} average is {score:g}"
    return evidence + (", so it gets more of your week." if direction == "raised" else ", so it needs less of your week." if direction == "lowered" else ".")


def merge_reasons(derived: list[dict], proposed: list) -> list[dict]:
    """Keep the computed facts; use the model's wording for a change only when it gave a non-empty reason for that skill."""
    wording = {item.get("skill"): str(item.get("reason", "")).strip() for item in proposed if isinstance(item, dict)}
    return [{**item, "reason": wording.get(item["skill"]) or item["reason"]} for item in derived]


def change_summaries(details: list[dict]) -> list[str]:
    if not details:
        return ["No major change: your priorities still match your recent results."]
    return [f"{item['skill'].title()} {item['change']} ({item['minutes_before']}→{item['minutes_after']} min/week): {item['reason']}" for item in details]


def select_resources(db: Session, user_id: int, exam: str, priorities: list[str], level: str | None = None) -> list[dict]:
    """Step 5: one study resource for each of the top priorities. 5a: when no suitable material exists the area is
    kept, with no inline recommendation, until material becomes available."""
    library = MaterialLibrary(db)
    focus = priorities[:RESOURCES_PER_PLAN]
    found = sorted(library.search(focus, exam, library.dismissed_ids(user_id)), key=lambda item: item.level != level)
    resources = []
    for skill in focus:
        item = next((m for m in found if m.skill == skill), None)
        resources.append({"skill": skill, "material_id": item.id, "title": item.title, "level": item.level} if item
                         else {"skill": skill, "material_id": None, "title": None, "note": "No suitable material is available yet for this area."})
    return resources


# ---------------------------------------------------------------- the use case

def record_outcome(db: Session, user_id: int, trigger: str, outcome: str, **detail):
    db.add(AuditLog(user_id=user_id, action="adaptation_outcome", detail={"trigger": trigger, "outcome": outcome, **detail}))
    db.add(AgentEvent(user_id=user_id, workflow="adaptation", agent="Learning Coordinator", phase="decision",
                      detail={"trigger": trigger, "outcome": outcome, **detail}, mode=settings().ai_mode))


def propose(db: Session, user_id: int, profile: dict, progress: dict, trigger: str) -> dict:
    """Run UC7 up to the point where the learner is shown a plan. The caller commits.
    Returns {"outcome", "plan", "package", "message"}: ``plan`` is None when the existing plan is kept (3a, 4a)."""
    from backend.agents import AgentRuntime  # lazy: agents.py imports this module
    active = db.scalar(select(Plan).where(Plan.user_id == user_id, Plan.status == "ACTIVE").order_by(Plan.id.desc()))
    if active is None:
        raise ValueError("An active plan is required before it can be adapted")
    if progress.get("sample_count", 0) < MIN_ASSESSMENTS:  # 3a
        record_outcome(db, user_id, trigger, INSUFFICIENT_DATA, sample_count=progress.get("sample_count", 0))
        return {"outcome": INSUFFICIENT_DATA, "plan": None, "package": None, "message": NOTICES[INSUFFICIENT_DATA]}
    context = {**progress, "trigger": trigger, "target_score": profile.get("target_score"),
               "current_plan": {"priorities": active.content.get("priorities", []), "activities": active.content.get("activities", [])}}
    state = AgentRuntime(db).plan_graph().invoke({"user_id": user_id, "workflow": "adaptation", "profile": profile, "progress": context})
    if state.get("generation_failed"):  # 4a: the retry also failed
        record_outcome(db, user_id, trigger, GENERATION_FAILED)
        return {"outcome": GENERATION_FAILED, "plan": None, "package": None, "message": NOTICES[GENERATION_FAILED]}
    package = db.get(ResultPackage, state["package_id"])
    version = (db.scalar(select(func.max(Plan.version)).where(Plan.user_id == user_id)) or 0) + 1
    plan = Plan(user_id=user_id, version=version, kind="adaptation", status="PROPOSED" if package.state == "RELEASED" else "HELD", content=package.payload, package_id=package.id)
    db.add(plan)
    db.flush()
    record_outcome(db, user_id, trigger, plan.status, plan_id=plan.id)
    return {"outcome": plan.status, "plan": plan, "package": package, "message": None}


def latest_notice(db: Session, user_id: int) -> dict | None:
    """What the learner should be told about the most recent attempt that kept the existing plan.
    It disappears once a newer adaptation has been proposed."""
    row = db.scalar(select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "adaptation_outcome").order_by(AuditLog.id.desc()))
    if row is None or row.detail.get("outcome") not in NOTICES:
        return None
    return {"outcome": row.detail["outcome"], "message": NOTICES[row.detail["outcome"]], "trigger": row.detail.get("trigger"), "created_at": row.created_at.isoformat() if row.created_at else None}


def reviewed_recently(db: Session, user_id: int, days: int = 7) -> bool:
    """Weekly idempotence: any adaptation proposal, or any weekly attempt that kept the plan, in the last week."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if db.scalar(select(Plan.id).where(Plan.user_id == user_id, Plan.kind == "adaptation", Plan.created_at >= cutoff)):
        return True
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.action == "adaptation_outcome", AuditLog.created_at >= cutoff)).all()
    return any(row.detail.get("trigger") == "weekly_review" for row in rows)


# ---------------------------------------------------------------- step 8: tell the other agents

def notify_agents(db: Session, plan: Plan, previous: dict | None, attempts: int = NOTIFY_ATTEMPTS, only: list[str] | None = None) -> list[str]:
    """Deliver the confirmed priorities to the AI Tutor and Assessment & Analytics (they recall them in later prompts).
    8a: a failed delivery is logged and retried; it never rolls the confirmed plan back. Returns the agents still not notified."""
    content = plan.content or {}
    priorities = content.get("priorities", [])
    before = ((previous or {}).get("priorities") or [])[:4]
    text = f"Study priorities updated (plan v{plan.version}): {', '.join(priorities[:4])}." + (f" Previously: {', '.join(before)}." if before else "")
    failed = []
    for key in (only or list(RECIPIENTS)):
        for attempt in range(1, attempts + 1):
            try:
                agent_core.remember(db, key, plan.user_id, text, "lesson", {"plan_id": plan.id, "priorities": priorities})
                db.add(AuditLog(user_id=plan.user_id, action="agent_notified", detail={"plan_id": plan.id, "agent": key, "attempt": attempt}))
                break
            except Exception as exc:
                db.add(AuditLog(user_id=plan.user_id, action="agent_notification_failed", detail={"plan_id": plan.id, "agent": key, "attempt": attempt, "error": type(exc).__name__}))
        else:
            failed.append(key)
    db.add(AgentEvent(user_id=plan.user_id, workflow="adaptation" if plan.kind == "adaptation" else "plan", agent="Learning Coordinator", phase="handoff",
                      detail={"decision": "notify updated priorities", "plan_id": plan.id, "next_agent": " + ".join(RECIPIENTS[k] for k in (only or RECIPIENTS)), "not_delivered": failed}, mode=settings().ai_mode))
    db.flush()
    return failed


def retry_pending_notifications(db: Session) -> int:
    """Run from the scheduled review: re-deliver to any agent whose notification for an active plan failed. Returns deliveries made."""
    delivered = 0
    for plan in db.scalars(select(Plan).where(Plan.status == "ACTIVE")).all():
        rows = [row for row in db.scalars(select(AuditLog).where(AuditLog.user_id == plan.user_id, AuditLog.action.in_(("agent_notified", "agent_notification_failed")))).all()
                if row.detail.get("plan_id") == plan.id]
        pending = {r.detail["agent"] for r in rows if r.action == "agent_notification_failed"} - {r.detail["agent"] for r in rows if r.action == "agent_notified"}
        if pending:
            failed = notify_agents(db, plan, None, attempts=1, only=sorted(pending))
            delivered += len(pending) - len(failed)
    return delivered
