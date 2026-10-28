"""Assessment & Analytics tools (UC5 steps 6-7, UC6 steps 2-6).

Pure analysis of verified (RELEASED) results: per-skill estimates, strengths and
weaknesses against the target, trends, readiness, recommendations and mock
comparisons. AssessmentAgent in backend/agents.py calls these and records what it
did; nothing here talks to the language model.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import MockExam, Profile, ResultPackage


def latest_progress(db: Session, user_id: int):
    packages = db.scalars(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.state == "RELEASED", ResultPackage.kind.in_(["writing", "speaking", "reading", "listening", "mock_exam"])).order_by(ResultPackage.id.desc()).limit(20)).all()
    scores = {}
    history = []
    error_counts = {}
    for pkg in reversed(packages):
        if pkg.kind == "mock_exam":
            for skill, score in pkg.payload.get("section_scores", {}).items():
                scores.setdefault(skill, []).append(score)
                history.append({"skill": skill, "score": score, "date": pkg.created_at.date().isoformat()})
        else:
            value = pkg.payload.get("estimated_overall")
            if value is not None:
                scores.setdefault(pkg.kind, []).append(value)
                history.append({"skill": pkg.kind, "score": value, "date": pkg.created_at.date().isoformat()})
            for comment in pkg.payload.get("comments", []):
                issue = comment.get("issue")
                if issue:
                    error_counts[issue] = error_counts.get(issue, 0) + 1
    averages = {skill: round(sum(values) / len(values), 2) for skill, values in scores.items()}
    target = db.scalar(select(Profile.target_score).where(Profile.user_id == user_id))
    # Strengths are at or above the target, weaknesses below it, so a skill is never both (UC6 step 4).
    strong, weak = split_skills(averages, target) if averages else ([], [])
    trends, trend_note = skill_trends(history)
    readiness, readiness_note = progress_readiness(averages, target, len(packages))
    return {"skill_scores": averages, "history": history, "weaknesses": [w["skill"] for w in weak], "strengths": [s["skill"] for s in strong],
            "weakness_notes": weak, "strength_notes": strong, "trends": trends, "trend_note": trend_note,
            "repeated_errors": [{"issue": issue, "count": count} for issue, count in error_counts.items() if count >= 2], "sample_count": len(packages),
            "readiness": readiness, "readiness_note": readiness_note}


TREND_STEP = .25  # Smaller changes than a quarter band are treated as steady.


def skill_trends(history: list[dict]) -> tuple[dict, str]:
    """Per-skill trend: the latest verified result against the average of the earlier ones (UC6 step 5)."""
    by_skill: dict[str, list[float]] = {}
    for item in history:
        by_skill.setdefault(item["skill"], []).append(item["score"])
    trends = {}
    for skill, values in by_skill.items():
        if len(values) < 2:
            trends[skill] = {"results": 1, "latest": values[-1], "direction": "not enough data"}
            continue
        change = round(values[-1] - sum(values[:-1]) / len(values[:-1]), 2)
        trends[skill] = {"results": len(values), "first": values[0], "latest": values[-1], "change": change,
                         "direction": "improving" if change >= TREND_STEP else "declining" if change <= -TREND_STEP else "steady"}
    thin = sorted(skill for skill, t in trends.items() if t["direction"] == "not enough data")
    if not trends or len(thin) == len(trends):
        note = "Not enough results to show a trend yet: complete at least two verified results in a skill."
    elif thin:
        note = f"Not enough data for a trend in {', '.join(thin)} yet: one more verified result in each is needed."
    else:
        note = ""
    return trends, note


def progress_readiness(averages: dict[str, float], target: float | None, samples: int) -> tuple[str, str]:
    """One readiness rule for the Performance page and saved reports."""
    if samples < 2 or not averages or target is None:
        return "Insufficient data", "Complete at least two verified results before readiness is estimated."
    mean = round(sum(averages.values()) / len(averages), 2)
    gap = round(target - mean, 2)
    level = "On track" if gap <= 0 else "Close to target" if gap <= .5 else "Needs further practice"
    return level, f"Your average verified estimate is {mean} against a target of {target}" + (f" ({gap} to go)." if gap > 0 else ".")


def issue_history(db: Session, user_id: int) -> dict[str, int]:
    """How often each feedback issue appeared in the learner's earlier verified writing, speaking and mock results."""
    counts: dict[str, int] = {}
    for package in db.scalars(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.state == "RELEASED",
                                                          ResultPackage.kind.in_(["writing", "speaking", "mock_exam"]))):
        payload = package.payload or {}
        comments = payload.get("comments", []) if package.kind != "mock_exam" else \
            [c for fb in (payload.get("details", {}).get("writing") or {}).values() for c in fb.get("comments", [])] + (payload.get("details", {}).get("speaking") or {}).get("comments", [])
        for comment in comments:
            if comment.get("issue"):
                counts[comment["issue"]] = counts.get(comment["issue"], 0) + 1
    return counts


def split_skills(scores: dict[str, float], target: float | None) -> tuple[list[dict], list[dict]]:
    """Strengths and weaknesses never overlap: below target is a weakness, at or above is a strength.
    When every skill sits on one side, the clearest outlier (at least half a band away) is named relative to the others."""
    ordered = sorted(scores, key=scores.get)
    if target is None:
        target = sum(scores.values()) / len(scores)
    weak = [{"skill": s, "score": scores[s], "note": f"{round(target - scores[s], 1)} below target"} for s in ordered if scores[s] < target]
    strong = [{"skill": s, "score": scores[s], "note": "at or above target"} for s in reversed(ordered) if scores[s] >= target]
    spread = scores[ordered[-1]] - scores[ordered[0]] if ordered else 0
    if not weak and spread >= .5:
        weak = [{"skill": ordered[0], "score": scores[ordered[0]], "note": "lowest of your skills (still at target)"}]
        strong = [item for item in strong if item["skill"] != ordered[0]]
    if not strong and spread >= .5:
        strong = [{"skill": ordered[-1], "score": scores[ordered[-1]], "note": "highest of your skills (still below target)"}]
        weak = [item for item in weak if item["skill"] != ordered[-1]]
    return strong, weak


def mock_insights(db: Session, user_id: int, scores: dict[str, float], overall: float, target: float | None, current_issues: list[str]) -> dict:
    """Compare with earlier assessments, name strengths and weaknesses, and estimate readiness from the trend (UC5 steps 6-7)."""
    previous = db.scalar(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.kind == "mock_exam", ResultPackage.state == "RELEASED")
                         .order_by(ResultPackage.id.desc()))
    if previous:
        prev_exam = db.scalar(select(MockExam.id).where(MockExam.package_id == previous.id))
        before = previous.payload.get("section_scores", {})
        against = f"Mock #{prev_exam} ({previous.created_at.date().isoformat()})" if prev_exam else f"your previous mock ({previous.created_at.date().isoformat()})"
        overall_change = round(overall - previous.payload.get("estimated_overall", overall), 1)
    else:
        before = latest_progress(db, user_id)["skill_scores"]
        against = "your practice average" if before else None
        overall_change = None
    comparison = {"against": against, "overall_change": overall_change,
                  "skills": {skill: {"before": before[skill], "now": scores[skill], "change": round(scores[skill] - before[skill], 1)} for skill in scores if skill in before}} if against else None
    strengths, weaknesses = split_skills(scores, target)
    history = issue_history(db, user_id)
    persistent = sorted({issue for issue in current_issues if history.get(issue)}, key=lambda issue: -history[issue])[:5]
    gap = round(target - overall, 1) if target is not None else None
    level = "Not enough data" if gap is None else "On track" if gap <= 0 else "Close to target" if gap <= .5 else "Needs further practice"
    if overall_change is None:
        trend = "This is your first mock, so there is no trend yet: take another mock in two to three weeks to see your progress."
    else:
        trend = (f"Up {overall_change} since {against}." if overall_change > 0 else f"Down {abs(overall_change)} since {against}." if overall_change < 0 else f"No change since {against}.")
    explanation = (f"Estimated {overall} against your target {target}" + (f" ({gap} to go). " if gap and gap > 0 else ". ") if target is not None else "") + trend
    if weaknesses:
        explanation += f" Focus next on {', '.join(item['skill'] for item in weaknesses[:2])}."
    return {"comparison": comparison, "strengths": strengths, "weaknesses": weaknesses, "persistent_issues": persistent,
            "readiness_detail": {"level": level, "gap": gap, "target": target, "trend": trend, "explanation": explanation}}


def progress_recommendations(progress: dict) -> list[str]:
    """Recommendations from the main skill gaps, declining trends and repeated problems (UC6 step 6)."""
    tips = [f"{item['skill'].title()} is {item['note']}: do two timed {item['skill']} tasks this week and review every comment." for item in progress["weakness_notes"][:2]]
    tips += [f"{skill.title()} is declining ({t['change']:+}): revisit your last {skill} feedback before practising again." for skill, t in progress["trends"].items()
             if t["direction"] == "declining" and skill not in progress["weaknesses"][:2]]
    tips += [f"'{item['issue']}' came up {item['count']} times in your feedback: make it your focus in the next task." for item in progress["repeated_errors"][:2]]
    return tips or ["Keep practising all four skills to maintain your level."]
