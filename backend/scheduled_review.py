"""Run daily via Task Scheduler or cron: the UC7 weekly review, plus retries of failed agent notifications."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend import adaptation, escalation
from backend.db import SessionLocal
from backend.main import latest_progress, profile_data
from backend.models import Plan, Profile


def run():
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    proposed = kept = 0
    with SessionLocal() as db:
        for active in db.scalars(select(Plan).where(Plan.status == "ACTIVE")).all():
            if active.created_at.replace(tzinfo=timezone.utc) > cutoff or adaptation.reviewed_recently(db, active.user_id):
                continue
            profile = db.scalar(select(Profile).where(Profile.user_id == active.user_id))
            if not profile:
                continue
            result = adaptation.propose(db, active.user_id, profile_data(profile), latest_progress(db, active.user_id), "weekly_review")
            db.commit()
            if result["plan"]:
                proposed += 1
            else:
                kept += 1  # not enough evidence, or the model failed twice: the learner keeps the existing plan and is told why
        retried = adaptation.retry_pending_notifications(db)
        cases = escalation.retry_all_pending(db)  # UC8 7a: outcomes of resolved cases that an agent has not received yet
        db.commit()
    print(f"Created {proposed} weekly adaptation proposals; kept {kept} existing plans; delivered {retried} pending plan notifications and {cases} pending case outcomes")


if __name__ == "__main__":
    run()
