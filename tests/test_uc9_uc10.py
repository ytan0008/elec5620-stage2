"""UC9 Check Agent Output Quality and UC10 Access Recommended Materials, against the Stage 1 specs."""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["DEMO_MODE"] = "true"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.main import app
from backend.db import Base, SessionLocal, engine
from backend.models import AgentEvent, Escalation, Material, QualityCheck, ResultPackage, User
from backend.agents import Agent, AgentRuntime, LLMProviderAdapter, OpsQualityManager
from backend.llm_service import LLMService, ResultStatus

PROFILE = {"exam": "IELTS", "proficiency": "intermediate", "priority_skills": ["writing", "speaking"]}


def setup_module():
    Base.metadata.create_all(engine)


def auth(client, email):
    response = client.post("/api/auth/register", json={"email": email, "name": "UC Learner", "password": "Example123!", "exam": "IELTS", "proficiency": "intermediate",
                                                       "target_score": 7, "exam_date": "2026-12-15", "weekly_hours": 8, "priority_skills": ["writing", "speaking"]})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def user_id(db, email):
    return db.scalar(select(User.id).where(User.email == email))


def states(db, package_id):
    return [e.detail["state"] for e in db.scalars(select(AgentEvent).where(AgentEvent.phase == "state").order_by(AgentEvent.id)) if e.detail.get("package_id") == package_id]


def test_agents_follow_the_class_diagram():
    with SessionLocal() as db:
        runtime = AgentRuntime(db)
        agents = [runtime.coordinator, runtime.tutor, runtime.assessment, runtime.quality_manager]
        assert all(isinstance(agent, Agent) for agent in agents)
        assert isinstance(runtime.quality_manager, OpsQualityManager)
        assert isinstance(runtime.provider, LLMService) and isinstance(runtime.provider, LLMProviderAdapter)
        assert {"SUBMITTED", "QUEUED", "VALIDATING", "REGENERATING", "CHECKING", "HELD", "VERIFIED", "RELEASED"} <= {s.value for s in ResultStatus}


def test_uc9_incomplete_result_is_regenerated_once_then_released():
    with TestClient(app) as client:
        headers = auth(client, "uc9-regen@example.com")
        practice = client.post("/api/practice/writing", headers=headers).json()
        response = client.post(f"/api/practice/{practice['id']}/submit", headers=headers,
                               json={"text": "Remote work gives employees flexibility, but teams need clear routines to collaborate well.", "scenario": "incomplete_once"})
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["state"] == "RELEASED"
    with SessionLocal() as db:
        assert states(db, result["id"]) == ["SUBMITTED", "VALIDATING", "REGENERATING", "VALIDATING", "CHECKING", "VERIFIED"]


def test_uc9_still_incomplete_after_regeneration_is_held_and_escalated():
    with TestClient(app) as client:
        auth(client, "uc9-hold@example.com")
    with SessionLocal() as db:
        uid = user_id(db, "uc9-hold@example.com")
        calls = []
        package = AgentRuntime(db).verify_output(uid, "recommendations", {"summary": "Empty list", "items": [], "confidence": {}},
                                                 regenerate=lambda: calls.append(1) or {"summary": "Still empty", "items": [], "confidence": {}})
        db.commit()
        assert len(calls) == 1  # Regenerated exactly once.
        assert package.state == "HELD" and "Recommendation list is incomplete" in package.issues
        assert db.scalar(select(Escalation).where(Escalation.package_id == package.id)) is not None
        assert states(db, package.id).count("REGENERATING") == 1


def test_uc9_llm_failure_is_retried_once_then_rule_checks_decide(monkeypatch):
    with TestClient(app) as client:
        auth(client, "uc9-retry@example.com")
    calls = []

    def unavailable(self, *args, **kwargs):
        calls.append(1)
        raise TimeoutError("LLM service did not respond")
    monkeypatch.setattr(LLMProviderAdapter, "check_consistency", unavailable)
    with SessionLocal() as db:
        uid = user_id(db, "uc9-retry@example.com")
        package = AgentRuntime(db).verify_output(uid, "portrait", {"summary": "Clear goals", "focus_areas": ["writing"], "next_steps": ["Practise Task 2"], "confidence": {"overall": .9}})
        db.commit()
        assert len(calls) == 2  # The first try and one retry.
        assert db.scalar(select(QualityCheck).where(QualityCheck.package_id == package.id)).method == "FALLBACK_RULES"
        assert package.state == "RELEASED"  # LOCAL mode: the rule checks found nothing to hold.


def test_uc9_adapter_makes_one_call_per_attempt():
    calls = []

    class Unreachable:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            calls.append(1)
            raise TimeoutError("LLM service did not respond")
    provider = LLMProviderAdapter()
    provider.mode, provider.verifier = "REAL", Unreachable()
    with pytest.raises(TimeoutError):
        provider.check_consistency({"summary": "Clear essay", "criteria": {"grammar": 6}})
    assert len(calls) == 1  # No hidden retry inside the adapter.


def test_uc10_new_learner_gets_general_starter_list():
    with TestClient(app) as client:
        headers = auth(client, "uc10-new@example.com")
        result = client.post("/api/materials/recommend", headers=headers).json()
        assert result["state"] == "RELEASED"
        items = result["payload"]["items"]
        assert 0 < len(items) <= 5 and all(item["label"] == "General" for item in items)
        assert items[0]["level"] == "intermediate"


def test_uc10_dismissed_items_are_left_out_and_ai_exercise_fills_the_gap():
    with TestClient(app) as client:
        headers = auth(client, "uc10-gap@example.com")
        writing = client.get("/api/materials?skill=writing", headers=headers).json()
        for item in writing:  # 8a: "Not relevant" on every writing item.
            assert client.post(f"/api/materials/{item['id']}/interaction?relevant=false", headers=headers).json()["relevant"] is False
    with SessionLocal() as db:
        uid = user_id(db, "uc10-gap@example.com")
        package = AgentRuntime(db).coordinator.request_recommendations(uid, PROFILE, {"weaknesses": ["writing", "speaking"], "sample_count": 2})
        db.commit()
        items = package.payload["items"]
        assert package.state == "RELEASED", package.issues
        assert not {item["id"] for item in writing} & {item["id"] for item in items}
        generated = [item for item in items if item.get("label") == "AI-generated"]
        assert [item["skill"] for item in generated] == ["writing"] and generated[0]["content"]
        assert {item["skill"] for item in items} <= {"writing", "speaking"}
        assert any(e.detail.get("material_id") == writing[0]["id"] for e in db.scalars(select(AgentEvent).where(AgentEvent.agent == "Learning Coordinator", AgentEvent.user_id == uid)))


def test_uc10_ranking_unavailable_falls_back_to_weakness_tags(monkeypatch):
    def unavailable(self, *args, **kwargs):
        raise TimeoutError("LLM service did not respond")
    monkeypatch.setattr(LLMProviderAdapter, "rank_and_explain", unavailable)
    with TestClient(app) as client:
        auth(client, "uc10-tags@example.com")
    with SessionLocal() as db:
        uid = user_id(db, "uc10-tags@example.com")
        package = AgentRuntime(db).coordinator.request_recommendations(uid, PROFILE, {"weaknesses": ["reading", "listening"], "sample_count": 2})
        db.commit()
        assert package.state == "RELEASED", package.issues
        assert package.payload["basis"] == "tags" and package.payload["error_type"] == "TimeoutError"
        items = package.payload["items"]
        assert items and all(item["reason"] == "" for item in items)
        assert [item["skill"] for item in items] == sorted((item["skill"] for item in items), key=["reading", "listening"].index)


def test_uc10_held_list_shows_last_verified_list(monkeypatch):
    with TestClient(app) as client:
        headers = auth(client, "uc10-held@example.com")
        first = client.post("/api/materials/recommend", headers=headers).json()
        assert first["state"] == "RELEASED"
        with SessionLocal() as db:  # Give the learner verified results so the personalised path runs.
            uid = user_id(db, "uc10-held@example.com")
            db.add(ResultPackage(user_id=uid, kind="writing", state="RELEASED", payload={"estimated_overall": 5.0, "comments": []}, confidence={}, source_mode="LOCAL", issues=[]))
            db.commit()
        original = LLMProviderAdapter.rank_and_explain

        def unsure(self, *args, **kwargs):
            output = original(self, *args, **kwargs)
            output.confidence = {key: .3 for key in output.confidence}
            return output
        monkeypatch.setattr(LLMProviderAdapter, "rank_and_explain", unsure)
        held = client.post("/api/materials/recommend", headers=headers).json()
        assert held["state"] == "HELD" and "payload" not in held
        assert held["last_verified"] == first["payload"]
