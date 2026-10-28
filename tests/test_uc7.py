"""UC7 Receive Adapted Learning Plan Based on Progress, against the Stage 1 specification (flow numbers in the test names)."""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["DEMO_MODE"] = "true"
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend import adaptation, agent_core
from backend.agents import LLMProviderAdapter
from backend.db import Base, SessionLocal, engine
from backend.main import adapt_after_major_assessment, app
from backend.materials import MaterialLibrary
from backend.models import AgentMemory, AuditLog, Plan, ResultPackage, User


def setup_module():
    Base.metadata.drop_all(engine)  # start clean, as test_workflow.py does, so the file can be re-run on its own
    Base.metadata.create_all(engine)


def learner(client, email):
    response = client.post("/api/auth/register", json={"email": email, "name": "UC7 Learner", "password": "Example123!", "exam": "IELTS", "proficiency": "intermediate",
                                                       "target_score": 7, "exam_date": "2026-12-15", "weekly_hours": 8, "priority_skills": ["writing", "speaking"]})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def with_active_plan(client, email):
    headers = learner(client, email)
    plan = client.post("/api/plans/generate", headers=headers).json()
    assert client.post(f"/api/plans/{plan['id']}/decision?accept=true", headers=headers).status_code == 200
    return headers, plan["id"]


def add_results(email, scores):
    """Verified results with chosen skill scores, so the comparison with the plan is predictable."""
    with SessionLocal.begin() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        for skill, value in scores.items():
            db.add(ResultPackage(user_id=uid, kind=skill, state="RELEASED", payload={"estimated_overall": value, "comments": []}, confidence={}, source_mode="LOCAL", issues=[]))


# reading and listening are the weakest, so they should move to the front of a plan that starts writing, speaking
WEAK_RECEIVING = {"reading": 4.5, "listening": 5.0, "writing": 6.5, "speaking": 7.0}


def plans(client, headers):
    return client.get("/api/plans", headers=headers).json()


def test_basic_flow_proposes_rationale_per_change_and_resources_then_activates_and_notifies():
    with TestClient(app) as client:
        headers, first_id = with_active_plan(client, "uc7-basic@example.com")
        add_results("uc7-basic@example.com", WEAK_RECEIVING)
        proposal = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        assert proposal["outcome"] == "PROPOSED" and proposal["package"]["state"] == "RELEASED"
        content = next(p for p in plans(client, headers) if p["id"] == proposal["id"])["content"]
        assert content["trigger"] == "learner_request"
        assert content["priorities"][:2] == ["reading", "listening"]
        # step 4: a rationale for each major change, grounded in the verified scores
        by_skill = {c["skill"]: c for c in content["change_details"]}
        assert by_skill["reading"]["change"] == "raised" and by_skill["reading"]["to_priority"] == 1 and "4.5" in by_skill["reading"]["reason"]
        assert by_skill["writing"]["change"] == "lowered" and all(c["reason"] for c in content["change_details"])
        assert len(content["changes"]) == len(content["change_details"])
        # step 5: relevant resources for the new focus
        assert [r["skill"] for r in content["resources"]] == content["priorities"][:3]
        assert all(r["material_id"] and r["title"] for r in content["resources"])
        # step 7 and 8: confirming activates the plan and the other agents are told the new priorities
        accepted = client.post(f"/api/plans/{proposal['id']}/decision?accept=true", headers=headers).json()
        assert accepted["status"] == "ACTIVE" and accepted["notifications_pending"] == []
        statuses = {p["id"]: p["status"] for p in plans(client, headers)}
        assert statuses[proposal["id"]] == "ACTIVE" and statuses[first_id] == "SUPERSEDED"
        with SessionLocal() as db:
            uid = db.scalar(select(User.id).where(User.email == "uc7-basic@example.com"))
            for agent in ("tutor", "assessment"):
                assert any("reading, listening" in text for text in agent_core.recall(db, agent, uid, 5)), agent


def test_3a_insufficient_evidence_keeps_the_existing_plan_and_tells_the_learner():
    with TestClient(app) as client:
        headers, plan_id = with_active_plan(client, "uc7-3a@example.com")
        add_results("uc7-3a@example.com", {"writing": 6.0})  # one assessment is not multiple assessments
        result = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        assert result["outcome"] == "INSUFFICIENT_DATA" and result["status"] == "KEPT_EXISTING" and result["id"] is None
        assert "more" in result["message"].lower() or "enough" in result["message"].lower()
        assert [(p["id"], p["status"]) for p in plans(client, headers)] == [(plan_id, "ACTIVE")]
        notice = client.get("/api/plans/adaptation-notice", headers=headers).json()["notice"]
        assert notice["outcome"] == "INSUFFICIENT_DATA"
        # once there is enough evidence the notice goes away because a newer proposal exists
        add_results("uc7-3a@example.com", {"reading": 5.0})
        assert client.post("/api/plans/generate?adapt=true", headers=headers).json()["outcome"] == "PROPOSED"
        assert client.get("/api/plans/adaptation-notice", headers=headers).json()["notice"] is None


def test_adaptation_requires_an_initial_plan():
    with TestClient(app) as client:
        headers = learner(client, "uc7-noplan@example.com")
        assert client.post("/api/plans/generate?adapt=true", headers=headers).status_code == 409


def test_4a_model_failure_is_retried_once_then_the_existing_plan_is_kept(monkeypatch):
    calls = []

    def unavailable(self, *args, **kwargs):
        calls.append(1)
        raise TimeoutError("model did not respond")
    with TestClient(app) as client:
        headers, plan_id = with_active_plan(client, "uc7-4a@example.com")
        add_results("uc7-4a@example.com", WEAK_RECEIVING)
        monkeypatch.setattr(LLMProviderAdapter, "plan", unavailable)
        result = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        assert len(calls) == 2  # the first attempt and exactly one retry
        assert result["outcome"] == "GENERATION_FAILED" and result["status"] == "KEPT_EXISTING" and result["package"] is None
        assert [(p["id"], p["status"]) for p in plans(client, headers)] == [(plan_id, "ACTIVE")]
        assert client.get("/api/plans/adaptation-notice", headers=headers).json()["notice"]["outcome"] == "GENERATION_FAILED"


def test_4a_a_successful_retry_still_produces_the_plan(monkeypatch):
    real, calls = LLMProviderAdapter.plan, []

    def flaky(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("first call failed")
        return real(self, *args, **kwargs)
    with TestClient(app) as client:
        headers, _ = with_active_plan(client, "uc7-4a-retry@example.com")
        add_results("uc7-4a-retry@example.com", WEAK_RECEIVING)
        monkeypatch.setattr(LLMProviderAdapter, "plan", flaky)
        assert client.post("/api/plans/generate?adapt=true", headers=headers).json()["outcome"] == "PROPOSED"
        assert len(calls) == 2


def test_model_wording_is_used_but_the_changes_themselves_are_computed(monkeypatch):
    real = LLMProviderAdapter.plan

    def worded(self, *args, **kwargs):
        output = real(self, *args, **kwargs)
        output.change_details = [{"skill": "reading", "reason": "Reading needs the most work right now."}, {"skill": "speaking", "reason": ""}, {"skill": "history", "reason": "invented"}]
        return output
    with TestClient(app) as client:
        headers, _ = with_active_plan(client, "uc7-wording@example.com")
        add_results("uc7-wording@example.com", WEAK_RECEIVING)
        monkeypatch.setattr(LLMProviderAdapter, "plan", worded)
        proposal = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        content = next(p for p in plans(client, headers) if p["id"] == proposal["id"])["content"]
        by_skill = {c["skill"]: c for c in content["change_details"]}
        assert by_skill["reading"]["reason"] == "Reading needs the most work right now."
        assert by_skill["speaking"]["reason"]  # an empty model reason falls back to the computed one
        assert "history" not in by_skill  # a change the model invented is ignored


def test_5a_an_area_with_no_suitable_material_is_kept_without_a_recommendation(monkeypatch):
    with TestClient(app) as client:
        headers, _ = with_active_plan(client, "uc7-5a@example.com")
        add_results("uc7-5a@example.com", WEAK_RECEIVING)
        monkeypatch.setattr(MaterialLibrary, "search", lambda self, *args, **kwargs: [])
        proposal = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        assert proposal["outcome"] == "PROPOSED"
        content = next(p for p in plans(client, headers) if p["id"] == proposal["id"])["content"]
        assert content["priorities"][:2] == ["reading", "listening"]  # the new priorities are kept
        assert all(r["material_id"] is None and r["title"] is None and r["note"] for r in content["resources"])


def test_7a_rejecting_keeps_the_existing_plan_and_records_the_rejection():
    with TestClient(app) as client:
        headers, plan_id = with_active_plan(client, "uc7-7a@example.com")
        add_results("uc7-7a@example.com", WEAK_RECEIVING)
        proposal = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        rejected = client.post(f"/api/plans/{proposal['id']}/decision?accept=false", headers=headers).json()
        assert rejected["status"] == "REJECTED"
        statuses = {p["id"]: p["status"] for p in plans(client, headers)}
        assert statuses[plan_id] == "ACTIVE" and statuses[proposal["id"]] == "REJECTED"
        with SessionLocal() as db:
            uid = db.scalar(select(User.id).where(User.email == "uc7-7a@example.com"))
            assert any("rejected" in m.text for m in db.scalars(select(AgentMemory).where(AgentMemory.agent == "coordinator", AgentMemory.user_id == uid)))
            assert db.scalar(select(AuditLog.id).where(AuditLog.user_id == uid, AuditLog.action == "plan_rejected"))
            told = [r.detail["plan_id"] for r in db.scalars(select(AuditLog).where(AuditLog.user_id == uid, AuditLog.action == "agent_notified"))]
            assert proposal["id"] not in told and plan_id in told  # only the plan that became active was announced


def test_8a_a_failed_notification_keeps_the_plan_active_is_logged_and_retried(monkeypatch):
    real = agent_core.remember

    def tutor_unreachable(db, agent, *args, **kwargs):
        if agent == "tutor":
            raise ConnectionError("tutor unavailable")
        return real(db, agent, *args, **kwargs)
    email = "uc7-8a@example.com"
    with TestClient(app) as client:
        headers, _ = with_active_plan(client, email)
        add_results(email, WEAK_RECEIVING)
        proposal = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        monkeypatch.setattr(agent_core, "remember", tutor_unreachable)
        accepted = client.post(f"/api/plans/{proposal['id']}/decision?accept=true", headers=headers)
        assert accepted.status_code == 200 and accepted.json()["status"] == "ACTIVE"  # the confirmed plan is not rolled back
        assert accepted.json()["notifications_pending"] == ["tutor"]
        with SessionLocal() as db:
            uid = db.scalar(select(User.id).where(User.email == email))
            rows = [r for r in db.scalars(select(AuditLog).where(AuditLog.user_id == uid, AuditLog.action.in_(("agent_notified", "agent_notification_failed")))) if r.detail["plan_id"] == proposal["id"]]
            assert [r.detail["agent"] for r in rows if r.action == "agent_notification_failed"] == ["tutor"] * adaptation.NOTIFY_ATTEMPTS
            assert [r.detail["agent"] for r in rows if r.action == "agent_notified"] == ["assessment"]
        monkeypatch.setattr(agent_core, "remember", real)  # the tutor is reachable again
        with SessionLocal.begin() as db:
            assert adaptation.retry_pending_notifications(db) == 1
        with SessionLocal.begin() as db:
            assert adaptation.retry_pending_notifications(db) == 0  # nothing left pending
            assert any("reading, listening" in text for text in agent_core.recall(db, "tutor", uid, 5))


def test_trigger_major_assessment_proposes_once_and_only_for_learners_with_a_plan():
    email = "uc7-major@example.com"
    with TestClient(app) as client:
        headers, _ = with_active_plan(client, email)
        add_results(email, WEAK_RECEIVING)
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            first = adapt_after_major_assessment(db, user)
            assert first["outcome"] == "PROPOSED" and first["plan_id"]
            assert adapt_after_major_assessment(db, user) is None  # a proposal is already waiting for the learner
        content = next(p for p in plans(client, headers) if p["id"] == first["plan_id"])["content"]
        assert content["trigger"] == "major_assessment"
        newcomer = learner(client, "uc7-major-noplan@example.com")
        with SessionLocal() as db:
            assert adapt_after_major_assessment(db, db.scalar(select(User).where(User.email == "uc7-major-noplan@example.com"))) is None
        assert newcomer


def test_trigger_weekly_review_keeps_plans_without_evidence_and_does_not_repeat_itself():
    from backend.scheduled_review import run
    email = "uc7-weekly@example.com"
    with TestClient(app) as client:
        headers, plan_id = with_active_plan(client, email)
        with SessionLocal.begin() as db:
            db.get(Plan, plan_id).created_at = datetime.now(timezone.utc) - timedelta(days=8)

        def weekly_attempts():
            with SessionLocal() as db:
                uid = db.scalar(select(User.id).where(User.email == email))
                return len(db.scalars(select(AuditLog).where(AuditLog.user_id == uid, AuditLog.action == "adaptation_outcome")).all())
        run()
        assert weekly_attempts() == 1 and len(plans(client, headers)) == 1
        assert client.get("/api/plans/adaptation-notice", headers=headers).json()["notice"]["trigger"] == "weekly_review"
        run()
        assert weekly_attempts() == 1  # the daily job does not repeat the weekly attempt
