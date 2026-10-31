"""UC8 Human Instructor Reviews Escalated Case (Stage 1 report, UC8).

Flow, with the Stage 1 alternate and exception flow numbers:
  1-2  the Quality Manager escalates a case; the instructor is notified
  2a   no instructor is available: the case waits in the queue and the next instructor to become available is notified
  3-4  the instructor opens the case: this learner's earlier results, previous decisions, and the conflicts and
       low-confidence values the system highlights
  3a   not enough context: the Quality Manager gathers more evidence and the case stays open
  5    approve (5a), override with a corrected result (5b) or request more information / coaching (5c, the case stays open)
  6-8  the decision and reasoning go into the case history, the relevant agents are told, the case is resolved and the
       decision becomes available to later quality checks (agents' memory and the instructor-decision tool)
  7a   a failed agent notification is logged and retried; the decision and the resolved case stay in place

Everything is stored in existing tables (audit log, system settings, agent memory), so there is no schema change.
``AgentRuntime`` is imported lazily because agents.py imports this module.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend import agent_core
from backend.config import settings
from backend.models import AgentEvent, AuditLog, Escalation, InstructorDecision, Profile, ResultPackage, SystemSetting, User

QUEUED = "QUEUED"
OPEN = ("PENDING", "MORE_INFO")
NOTIFY_ATTEMPTS = 3
CONFLICT_GAP = 1.0  # an estimate this far from the learner's recent average of the same kind is a conflict
RELEVANT_AGENTS = {"writing": ("quality", "tutor"), "speaking": ("quality", "tutor"), "plan": ("quality", "coordinator"), "adaptation": ("quality", "coordinator"),
                   "recommendations": ("quality", "coordinator"), "mock_exam": ("quality", "assessment")}
OUTCOMES = {"approve": "Instructor approved a held {kind} result unchanged (likely a false alarm)", "correct": "Instructor overrode a held {kind} result with a corrected one",
            "request_information": "Instructor asked for more information on a held {kind} result"}
TIMELINE = {"approve": "Instructor approved the AI result unchanged", "correct": "Instructor overrode the AI result with a corrected one", "request_information": "Instructor asked for more information"}


def log(db: Session, user_id: int | None, action: str, case_id: int, **detail):
    db.add(AuditLog(user_id=user_id, action=action, detail={"case_id": case_id, **detail}))


def case_logs(db: Session, case_id: int, actions: tuple[str, ...]) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action.in_(actions), AuditLog.detail["case_id"].as_integer() == case_id).order_by(AuditLog.id)))


# ---------------------------------------------------------------- steps 1-2 and 2a: notify, or queue

def instructors(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == "instructor").order_by(User.id)))


def is_available(db: Session, instructor_id: int) -> bool:
    row = db.get(SystemSetting, f"instructor_available:{instructor_id}")
    return row is None or row.value != "0"


def notify(db: Session, case: Escalation, instructor: User):
    package = db.get(ResultPackage, case.package_id)
    db.add(AuditLog(user_id=instructor.id, action="instructor_notified", detail={"case_id": case.id, "kind": package.kind, "reason": (case.reason or "")[:200]}))


def route(db: Session, case: Escalation):
    """Called when the Quality Manager escalates. With instructors on the system but none available (2a), the case is queued."""
    people = instructors(db)
    ready = [person for person in people if is_available(db, person.id)]
    if people and not ready:
        case.status = QUEUED
        log(db, None, "case_queued", case.id, reason="no instructor is available")
        return
    for person in ready:
        notify(db, case, person)


def set_available(db: Session, instructor: User, available: bool) -> int:
    """An instructor marks themself available or away. Becoming available releases the queue to them. Returns cases released."""
    key = f"instructor_available:{instructor.id}"
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value="1" if available else "0"))
    else:
        row.value = "1" if available else "0"
    db.flush()
    if not available:
        return 0
    queued = db.scalars(select(Escalation).where(Escalation.status == QUEUED).order_by(Escalation.id)).all()
    for case in queued:
        case.status = "PENDING"
        log(db, instructor.id, "case_released_from_queue", case.id)
        notify(db, case, instructor)
    return len(queued)


def notifications(db: Session, instructor_id: int) -> list[dict]:
    """Cases this instructor was told about that still need a decision, newest first."""
    open_ids = set(db.scalars(select(Escalation.id).where(Escalation.status.in_(OPEN))))
    seen, out = set(), []
    for row in db.scalars(select(AuditLog).where(AuditLog.user_id == instructor_id, AuditLog.action == "instructor_notified").order_by(AuditLog.id.desc()).limit(100)):
        case_id = row.detail["case_id"]
        if case_id in open_ids and case_id not in seen:
            seen.add(case_id)
            out.append({"case_id": case_id, "kind": row.detail.get("kind"), "reason": row.detail.get("reason"), "created_at": row.created_at.isoformat() if row.created_at else None})
    return out


# ---------------------------------------------------------------- steps 3-4: what the instructor sees

def previous_decisions(db: Session, case: Escalation, package: ResultPackage, limit: int = 6) -> list[dict]:
    """Earlier decisions on this learner's cases or on the same kind of result."""
    rows = db.execute(select(InstructorDecision, ResultPackage).join(Escalation, Escalation.id == InstructorDecision.case_id).join(ResultPackage, ResultPackage.id == Escalation.package_id)
                      .where(Escalation.id != case.id, (ResultPackage.user_id == package.user_id) | (ResultPackage.kind == package.kind))
                      .order_by(InstructorDecision.id.desc()).limit(limit)).all()
    return [{"case_id": decision.case_id, "kind": other.kind, "decision": decision.decision, "note": decision.note, "same_learner": other.user_id == package.user_id,
             "created_at": decision.created_at.isoformat() if decision.created_at else None} for decision, other in rows]


def highlights(db: Session, package: ResultPackage, recent: list[dict]) -> list[dict]:
    """Step 4: low-confidence values and conflicting results, plus the reasons the Quality Manager held the result."""
    from backend.agents import AgentRuntime
    runtime = AgentRuntime(db)
    threshold, payload, items = runtime.threshold(), package.payload or {}, []
    low = {field: value for field, value in (package.confidence or {}).items() if isinstance(value, (int, float)) and value < threshold}
    if low:  # one line for all low values, so a result that is uncertain everywhere does not bury the other highlights
        items.append({"type": "low_confidence", "fields": list(low), "detail": f"Confidence is below the release threshold of {threshold:g} for {len(low)} {'value' if len(low) == 1 else 'values'}: " + ", ".join(f"{field} {value:g}" for field, value in low.items()) + "."})
    for issue in runtime.quality_manager.rule_based_check(payload):
        items.append({"type": "conflict", "detail": issue})
    estimate = payload.get("estimated_overall")
    earlier = [item["estimate"] for item in recent if item["kind"] == package.kind and isinstance(item.get("estimate"), (int, float))]
    if isinstance(estimate, (int, float)) and earlier:
        mean = sum(earlier) / len(earlier)
        if abs(estimate - mean) >= CONFLICT_GAP:
            items.append({"type": "conflict", "detail": f"The estimate of {estimate:g} is {abs(estimate - mean):.1f} away from this learner's recent {package.kind} average of {mean:.1f}."})
    for issue in package.issues or []:
        if not (issue == "Confidence below configured threshold" and any(item["type"] == "low_confidence" for item in items)):
            items.append({"type": "quality_issue", "detail": issue})
    return items


def missing_context(package: ResultPackage, recent: list[dict], evidence_added: bool) -> list[str]:
    """3a: what the instructor would need before a decision can be made."""
    payload, missing = package.payload or {}, []
    if not package.confidence:
        missing.append("The result has no confidence values.")
    if package.kind in ("writing", "speaking") and not (payload.get("criteria") and payload.get("comments")):
        missing.append("The feedback has no criterion scores or comments to check.")
    if not recent and not evidence_added:
        missing.append("There are no earlier verified results for this learner to compare against.")
    return missing


def gather_evidence(db: Session, case: Escalation, package: ResultPackage, requested_by: int) -> list[dict]:
    """3a and 5c: the Quality Manager collects more evidence for the instructor: a fuller learner history,
    issues that repeat across it, and a fresh consistency check of the held result."""
    from backend.agents import AgentRuntime
    log(db, requested_by, "case_evidence_requested", case.id)
    history = agent_core.score_history(db, package.user_id, None, 15)
    repeated: dict[str, int] = {}
    for item in history:
        for issue in item["issues"]:
            repeated[issue] = repeated.get(issue, 0) + 1
    contradictions = AgentRuntime(db).quality_manager.rule_based_check(package.payload or {})
    items = [{"label": "Learner history", "detail": f"{len(history)} earlier verified results: " + ", ".join(f"{h['kind']} {h['estimate']}" for h in history[:8] if h.get("estimate") is not None)
              if history else "No earlier verified results exist for this learner, so this result has to be judged on its own."},
             {"label": "Repeated issues", "detail": ", ".join(f"{name} (x{count})" for name, count in repeated.items() if count >= 2) or "No issue repeats across the earlier results."},
             {"label": "Fresh consistency check", "detail": "; ".join(contradictions) or "The rule checks found no contradictions."}]
    log(db, None, "case_evidence_added", case.id, items=items)
    db.add(AgentEvent(user_id=package.user_id, workflow=package.kind, agent="Quality Manager", phase="handoff", detail={"decision": "gather more evidence", "case_id": case.id, "next_agent": "Human Instructor"}, mode=package.source_mode))
    return items


# ---------------------------------------------------------------- step 7 and 7a: tell the agents

def notify_agents(db: Session, case: Escalation, package: ResultPackage, decision: str, note: str, attempts: int = NOTIFY_ATTEMPTS, only: list[str] | None = None) -> list[str]:
    """Record the instructor's outcome in the memory of each relevant agent. The Quality Manager keeps it as a lesson for later quality
    checks (8). 7a: a failed delivery is logged and retried and never undoes the decision. Returns the agents still not notified."""
    base = OUTCOMES.get(decision, "Instructor decided '{decision}' on a held {kind} result").format(kind=package.kind, decision=decision)
    failed = []
    for key in (only or RELEVANT_AGENTS.get(package.kind, ("quality",))):
        text = f"{base}; it was held for: {(case.reason or '')[:200]}" + (f". Note: {note[:200]}" if note else ".") if key == "quality" else f"{base} for this learner. Note: {note[:300]}"
        for attempt in range(1, attempts + 1):
            try:
                agent_core.remember(db, key, None if key == "quality" else package.user_id, text, "lesson", {"package_id": package.id, "case_id": case.id, "decision": decision})
                log(db, None, "case_agent_notified", case.id, agent=key, attempt=attempt)
                break
            except Exception as exc:
                log(db, None, "case_agent_notification_failed", case.id, agent=key, attempt=attempt, error=type(exc).__name__)
        else:
            failed.append(key)
    db.add(AgentEvent(user_id=package.user_id, workflow=package.kind, agent="Human Instructor", phase="decision",
                      detail={"decision": decision, "package_id": package.id, "case_id": case.id, "next_agent": ", ".join(agent_core.AGENT_NAMES[k] for k in (only or RELEVANT_AGENTS.get(package.kind, ("quality",)))), "not_delivered": failed}, mode=package.source_mode))
    db.flush()
    return failed


def pending_agents(db: Session, case_id: int) -> list[str]:
    rows = case_logs(db, case_id, ("case_agent_notified", "case_agent_notification_failed"))
    return sorted({r.detail["agent"] for r in rows if r.action == "case_agent_notification_failed"} - {r.detail["agent"] for r in rows if r.action == "case_agent_notified"})


def retry_notifications(db: Session, case: Escalation) -> int:
    """Re-deliver the outcome to any agent still missing it. Returns deliveries made."""
    pending = pending_agents(db, case.id)
    decision = db.scalar(select(InstructorDecision).where(InstructorDecision.case_id == case.id).order_by(InstructorDecision.id.desc()))
    if not pending or decision is None:
        return 0
    failed = notify_agents(db, case, db.get(ResultPackage, case.package_id), decision.decision, decision.note, attempts=1, only=pending)
    return len(pending) - len(failed)


def retry_all_pending(db: Session) -> int:
    """Run from the scheduled job: retry every resolved case whose agent notification failed."""
    return sum(retry_notifications(db, case) for case in db.scalars(select(Escalation).where(Escalation.status == "RESOLVED")).all())


# ---------------------------------------------------------------- the case as the instructor sees it

EVENT_TEXT = {
    "instructor_notified": lambda d: "Instructor notified that the case needs review",
    "case_queued": lambda d: "No instructor was available, so the case was queued",
    "case_released_from_queue": lambda d: "An instructor became available and the case was released from the queue",
    "case_evidence_requested": lambda d: "More evidence requested from the Quality Manager",
    "case_evidence_added": lambda d: "Evidence added: " + ", ".join(item["label"].lower() for item in d.get("items", [])),
    "case_agent_notified": lambda d: f"{agent_core.AGENT_NAMES.get(d.get('agent'), d.get('agent'))} notified of the outcome",
    "case_agent_notification_failed": lambda d: f"Notifying {agent_core.AGENT_NAMES.get(d.get('agent'), d.get('agent'))} failed (attempt {d.get('attempt')}); it will be retried",
    "case_resolved": lambda d: "Case resolved",
}


def history(db: Session, case: Escalation) -> list[dict]:
    """Step 6: one timeline of the escalation, system events and every decision with its reasoning."""
    events = [(case.created_at, {"event": "escalated", "detail": f"Escalated by the Quality Manager: {case.reason}"})]
    for row in case_logs(db, case.id, tuple(EVENT_TEXT)):
        events.append((row.created_at, {"event": row.action, "detail": EVENT_TEXT[row.action](row.detail)}))
    for decision in db.scalars(select(InstructorDecision).where(InstructorDecision.case_id == case.id).order_by(InstructorDecision.id)):
        events.append((decision.created_at, {"event": f"decision:{decision.decision}", "detail": f"{TIMELINE.get(decision.decision, decision.decision)}. Reasoning: {decision.note}"}))
    return [{"at": at.isoformat() if at else None, **event} for at, event in sorted(events, key=lambda pair: (pair[0] is None, pair[0]))]


def delivery(db: Session, case_id: int) -> list[dict]:
    rows = case_logs(db, case_id, ("case_agent_notified", "case_agent_notification_failed"))
    agents = list(dict.fromkeys(r.detail["agent"] for r in rows))
    delivered = {r.detail["agent"] for r in rows if r.action == "case_agent_notified"}
    return [{"agent": agent_core.AGENT_NAMES.get(a, a), "key": a, "status": "delivered" if a in delivered else "pending"} for a in agents]


def case_detail(db: Session, case: Escalation) -> dict:
    """Everything the instructor needs next to the held result (the caller adds the package itself)."""
    package = db.get(ResultPackage, case.package_id)
    profile = db.scalar(select(Profile).where(Profile.user_id == package.user_id))
    recent = agent_core.score_history(db, package.user_id, None, 8)
    evidence = [item for row in case_logs(db, case.id, ("case_evidence_added",)) for item in row.detail.get("items", [])]
    return {"learner": {"learner_id": package.user_id, **({"exam": profile.exam, "proficiency": profile.proficiency, "target_score": profile.target_score} if profile else {})},
            "recent_results": recent, "previous_decisions": previous_decisions(db, case, package), "highlights": highlights(db, package, recent),
            "missing_context": missing_context(package, recent, bool(evidence)), "additional_evidence": evidence,
            "history": history(db, case), "agent_delivery": delivery(db, case.id)}
