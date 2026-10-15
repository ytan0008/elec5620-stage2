"""Run daily via Task Scheduler or cron to propose weekly adaptations."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from backend.agents import AgentRuntime
from backend.db import SessionLocal
from backend.main import latest_progress, profile_data
from backend.models import Plan, Profile, ResultPackage, AuditLog


def run():
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    proposed = 0
    with SessionLocal() as db:
        for active in db.scalars(select(Plan).where(Plan.status == "ACTIVE")).all():
            existing = db.scalar(select(Plan.id).where(Plan.user_id == active.user_id, Plan.kind == "adaptation", Plan.created_at >= cutoff))
            if existing or active.created_at.replace(tzinfo=timezone.utc) > cutoff:
                continue
            profile = db.scalar(select(Profile).where(Profile.user_id == active.user_id))
            if not profile:
                continue
            runtime = AgentRuntime(db)
            state = runtime.plan_graph().invoke({"user_id": active.user_id, "workflow": "adaptation", "profile": profile_data(profile), "progress": latest_progress(db, active.user_id)})
            package = db.get(ResultPackage, state["package_id"])
            version = (db.scalar(select(func.max(Plan.version)).where(Plan.user_id == active.user_id)) or 0) + 1
            db.add(Plan(user_id=active.user_id, version=version, kind="adaptation", status="PROPOSED" if package.state == "RELEASED" else "HELD", content=package.payload, package_id=package.id))
            db.add(AuditLog(user_id=active.user_id, action="scheduled_adaptation_proposed", detail={"package_id": package.id}))
            db.commit()
            proposed += 1
    print(f"Created {proposed} weekly adaptation proposals")


if __name__ == "__main__":
    run()
