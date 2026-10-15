"""Developer/teacher console: agent health metrics and anomaly detection.

Anomalies are computed from persisted evidence (agent events, quality checks,
result packages, audit logs and learner reports), so the list is always
reproducible. Acknowledging an anomaly is recorded in the audit log.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import AgentEvent, AuditLog, IssueReport, Plan, QualityCheck, ResultPackage, User

SLOW_MS = 8000
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * .95))]


def overview(db: Session, mode: str, model: str) -> dict:
    now = datetime.now(timezone.utc)
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    events = list(db.scalars(select(AgentEvent).where(AgentEvent.created_at >= week)))
    recent = [e for e in events if _aware(e.created_at) >= day]
    per_agent = defaultdict(list)
    for event in events:
        per_agent[event.agent].append(event.duration_ms or 0)
    agents = [{"agent": agent, "events": len(values), "avg_ms": round(mean(values)) if values else 0, "p95_ms": _p95(values),
               "slow": sum(v > SLOW_MS for v in values)} for agent, values in sorted(per_agent.items(), key=lambda pair: -len(pair[1]))]
    hourly = defaultdict(int)
    for event in recent:
        hourly[_aware(event.created_at).strftime("%H:00")] += 1
    hours = [(now - timedelta(hours=h)).strftime("%H:00") for h in range(23, -1, -1)]
    packages = list(db.scalars(select(ResultPackage).where(ResultPackage.created_at >= week)))
    held = [p for p in packages if p.state in ("HELD", "HUMAN_REVIEW")]
    learners = db.scalars(select(User).where(User.role == "learner")).all()
    active_ids = {e.user_id for e in events}
    return {
        "mode": mode, "model": model,
        "events_24h": len(recent), "events_7d": len(events),
        "results_7d": len(packages), "held_7d": len(held), "hold_rate": round(len(held) / len(packages), 3) if packages else 0,
        "learners": len(learners), "active_learners_7d": len(active_ids & {u.id for u in learners}),
        "open_reports": len(db.scalars(select(IssueReport.id).where(IssueReport.status == "OPEN")).all()),
        "agents": agents, "timeline": [{"hour": h, "events": hourly.get(h, 0)} for h in hours],
        "workflows": sorted(({"workflow": w, "count": c} for w, c in _count(e.workflow for e in events).items()), key=lambda item: -item["count"]),
    }


def _count(items) -> dict:
    counts = defaultdict(int)
    for item in items:
        counts[item] += 1
    return counts


def anomalies(db: Session, days: int = 7) -> list[dict]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    users = {u.id: u for u in db.scalars(select(User))}
    who = lambda uid: {"user_id": uid, "user": users[uid].name if uid in users else "system", "email": users[uid].email if uid in users else ""}
    found: list[dict] = []

    packages = list(db.scalars(select(ResultPackage).where(ResultPackage.created_at >= since).order_by(ResultPackage.id)))
    for package in packages:
        payload = package.payload or {}
        if payload.get("error_type"):
            found.append({"id": f"model-failure:{package.id}", "severity": "high", "category": "Model failure",
                          "title": f"{package.kind} generation failed ({payload['error_type']})",
                          "detail": "The AI provider returned output that failed structured validation; the result was held for human review.",
                          "time": package.created_at, "ref": {"package_id": package.id}, **who(package.user_id)})
        elif package.state in ("HELD", "HUMAN_REVIEW"):
            found.append({"id": f"held:{package.id}", "severity": "medium", "category": "Quality hold",
                          "title": f"{package.kind.replace('_', ' ')} result held by the Quality Manager",
                          "detail": "; ".join(package.issues or []) or "Held for review", "time": package.created_at, "ref": {"package_id": package.id}, **who(package.user_id)})
    if len(packages) >= 5:
        rate = sum(p.state in ("HELD", "HUMAN_REVIEW") for p in packages) / len(packages)
        if rate > .3:
            found.append({"id": f"hold-rate:{now.date()}", "severity": "high", "category": "Quality trend",
                          "title": f"High hold rate: {round(rate * 100)}% of results in {days} days",
                          "detail": "Many outputs fail quality checks. Check the model configuration, prompts or the confidence threshold.", "time": now, "ref": {}, **who(None)})

    held_by_user = _count(p.user_id for p in packages if p.state in ("HELD", "HUMAN_REVIEW"))
    for uid, count in held_by_user.items():
        if count >= 3:
            found.append({"id": f"learner-holds:{uid}:{now.date()}", "severity": "medium", "category": "Learner pattern",
                          "title": f"{count} held results for one learner", "detail": "Repeated holds for the same learner may mean unusual input or a scoring problem for their level.",
                          "time": now, "ref": {}, **who(uid)})

    for check in db.scalars(select(QualityCheck).where(QualityCheck.created_at >= since)):
        if check.method == "FALLBACK_RULES" or any("unavailable" in issue.lower() for issue in check.issues or []):
            package = db.get(ResultPackage, check.package_id)
            found.append({"id": f"provider-outage:{check.id}", "severity": "high", "category": "Provider outage",
                          "title": "Consistency verifier unavailable", "detail": "The LLM consistency check could not run, so rule fallbacks were used.",
                          "time": check.created_at, "ref": {"package_id": check.package_id}, **who(package.user_id if package else None)})

    for event in db.scalars(select(AgentEvent).where(AgentEvent.created_at >= since, AgentEvent.duration_ms > SLOW_MS)):
        found.append({"id": f"slow:{event.id}", "severity": "low", "category": "Latency",
                      "title": f"{event.agent} took {event.duration_ms / 1000:.1f}s", "detail": f"Workflow {event.workflow}, phase {event.phase}. Target is under {SLOW_MS // 1000}s.",
                      "time": event.created_at, "ref": {"event_id": event.id}, **who(event.user_id)})

    for row in db.scalars(select(AuditLog).where(AuditLog.created_at >= since, AuditLog.action.in_(["transcription_failed", "curriculum_gap_detected"]))):
        if row.action == "transcription_failed":
            found.append({"id": f"stt:{row.id}", "severity": "medium", "category": "Speech service", "title": "Audio transcription failed",
                          "detail": f"Error type: {row.detail.get('error_type', 'unknown')}", "time": row.created_at, "ref": row.detail, **who(row.user_id)})
        else:
            found.append({"id": f"gap:{row.id}", "severity": "medium", "category": "Curriculum gap", "title": f"Many learners struggle with: {row.detail.get('issue')}",
                          "detail": f"{row.detail.get('learners')} learners in 7 days. Consider new material.", "time": row.created_at, "ref": row.detail, **who(None)})

    # Sudden verified score drops can indicate inconsistent scoring (inter-rater reliability).
    by_user_skill = defaultdict(list)
    for package in packages:
        if package.state == "RELEASED" and isinstance((package.payload or {}).get("estimated_overall"), (int, float)) and package.kind in ("writing", "speaking", "listening", "reading"):
            by_user_skill[(package.user_id, package.kind)].append(package)
    for (uid, skill), items in by_user_skill.items():
        for previous, current in zip(items, items[1:]):
            drop = previous.payload["estimated_overall"] - current.payload["estimated_overall"]
            if drop >= 2:
                found.append({"id": f"score-drop:{current.id}", "severity": "low", "category": "Score consistency",
                              "title": f"{skill} estimate fell {drop:g} bands between attempts", "detail": f"{previous.payload['estimated_overall']} → {current.payload['estimated_overall']}. Check whether the task or scoring changed.",
                              "time": current.created_at, "ref": {"package_id": current.id}, **who(uid)})

    for report in db.scalars(select(IssueReport).where(IssueReport.status == "OPEN")):
        found.append({"id": f"report:{report.id}", "severity": "medium" if report.category in ("result", "question") else "low", "category": "Learner report",
                      "title": f"Learner report · {report.category}", "detail": report.message[:300], "time": report.created_at, "ref": {"report_id": report.id}, **who(report.user_id)})

    active_plans = {p.user_id for p in db.scalars(select(Plan).where(Plan.status == "ACTIVE"))}
    last_seen = {}
    for event in db.scalars(select(AgentEvent).where(AgentEvent.user_id.in_(active_plans))):
        if event.user_id not in last_seen or _aware(event.created_at) > last_seen[event.user_id]:
            last_seen[event.user_id] = _aware(event.created_at)
    for uid, seen in last_seen.items():
        if (now - seen).days >= 7:
            found.append({"id": f"inactive:{uid}:{seen.date()}", "severity": "low", "category": "Inactivity", "title": f"No practice for {(now - seen).days} days",
                          "detail": "Learner has an active plan but no recent activity.", "time": seen, "ref": {}, **who(uid)})

    acknowledged = {row.detail.get("anomaly_id") for row in db.scalars(select(AuditLog).where(AuditLog.action == "anomaly_acknowledged"))}
    for item in found:
        item["acknowledged"] = item["id"] in acknowledged
        item["time"] = _aware(item["time"]).isoformat()
    # Open items first, then by severity, newest first.
    return sorted(found, key=lambda item: (item["acknowledged"], SEVERITY_ORDER[item["severity"]], -datetime.fromisoformat(item["time"]).timestamp()))[:300]
