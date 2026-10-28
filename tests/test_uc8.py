"""UC8 Human Instructor Reviews Escalated Case, against the Stage 1 specification (flow numbers in the test names)."""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["DEMO_MODE"] = "true"
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend import agent_core, escalation
from backend.db import Base, SessionLocal, engine
from backend.main import app
from backend.models import Escalation, ResultPackage, User


def setup_module():
    Base.metadata.drop_all(engine)  # start clean, as test_workflow.py does, so the file can be re-run on its own
    Base.metadata.create_all(engine)


def learner(client, email):
    response = client.post("/api/auth/register", json={"email": email, "name": "UC8 Learner", "password": "Example123!", "exam": "IELTS", "proficiency": "intermediate",
                                                       "target_score": 7, "exam_date": "2026-12-15", "weekly_hours": 8, "priority_skills": ["writing", "speaking"]})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def instructor(client):
    token = client.post("/api/auth/login", json={"email": "instructor@example.com", "password": "ChangeMe123!"}).json()["token"]
    return {"Authorization": "Bearer " + token}


CRITERIA = {"task_response": 6.0, "coherence": 6.0, "lexical_resource": 6.0, "grammar": 6.0}


def feedback(estimate=6.0, confidence=0.9, summary="A clear answer with some grammar slips to fix."):
    return {"summary": summary, "criteria": dict(CRITERIA), "comments": [{"issue": "Article misuse", "suggestion": "Check articles."}],
            "estimated_overall": estimate, "confidence": {key: confidence for key in CRITERIA}}


def uid(email):
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


def add_released(email, kind="writing", estimate=6.0):
    with SessionLocal.begin() as db:
        db.add(ResultPackage(user_id=uid(email), kind=kind, state="RELEASED", payload={"estimated_overall": estimate, "comments": [{"issue": "Article misuse"}]}, confidence={}, source_mode="LOCAL", issues=[]))


def make_case(email, kind="writing", payload=None, issues=("Confidence below configured threshold",)):
    """An escalation exactly as the Quality Manager creates it: a held result plus a routed case."""
    payload = feedback(confidence=0.4) if payload is None else payload
    with SessionLocal.begin() as db:
        package = ResultPackage(user_id=uid(email), kind=kind, state="HELD", payload=payload, confidence=payload.get("confidence", {}), source_mode="LOCAL", issues=list(issues))
        db.add(package)
        db.flush()
        case = Escalation(package_id=package.id, status="PENDING", reason="; ".join(issues))
        db.add(case)
        db.flush()
        escalation.route(db, case)
        return case.id, package.id


def detail(client, ih, case_id):
    response = client.get(f"/api/instructor/cases/{case_id}", headers=ih)
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, ih, case_id, note="Scores match the comments."):
    return client.post(f"/api/instructor/cases/{case_id}/decision", headers=ih, json={"decision": "approve", "note": note})


def memory(email, agent):
    with SessionLocal() as db:
        return agent_core.recall(db, agent, None if agent == "quality" else uid(email), 10)


def test_basic_flow_notifies_shows_context_records_reasoning_and_tells_the_agents():
    email = "uc8-basic@example.com"
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        add_released(email, estimate=6.0)
        first, _ = make_case(email)
        assert approve(client, ih, first, "Earlier case: the confidence was just low.").status_code == 200
        case_id, package_id = make_case(email)
        # step 2: the instructor is notified
        assert case_id in [n["case_id"] for n in client.get("/api/instructor/availability", headers=ih).json()["notifications"]]
        # steps 3 and 4: the learner's results, the previous decision and the highlights
        view = detail(client, ih, case_id)
        assert view["status"] == "PENDING" and view["package"]["id"] == package_id and view["learner"]["exam"] == "IELTS"
        assert view["recent_results"] and view["recent_results"][0]["kind"] == "writing"
        assert any(d["case_id"] == first and d["same_learner"] and d["decision"] == "approve" for d in view["previous_decisions"])
        assert {h["type"] for h in view["highlights"]} >= {"low_confidence"} and any("0.4" in h["detail"] for h in view["highlights"])
        # steps 5a to 8: approve, reasoning recorded, agents told, resolved
        done = approve(client, ih, case_id, "Scores match the comments; the low confidence was a false alarm.")
        assert done.status_code == 200 and done.json()["status"] == "RESOLVED" and done.json()["notifications_pending"] == []
        assert client.get(f"/api/results/{package_id}", headers=learner_headers(client, email)).json()["state"] == "RELEASED"
        after = detail(client, ih, case_id)
        events = [e["event"] for e in after["history"]]
        assert events[0] == "escalated" and "instructor_notified" in events and "decision:approve" in events and "case_resolved" in events
        assert any("false alarm" in e["detail"] for e in after["history"] if e["event"] == "decision:approve")
        assert {d["status"] for d in after["agent_delivery"]} == {"delivered"} and {d["key"] for d in after["agent_delivery"]} == {"quality", "tutor"}
        assert any("approved a held writing result unchanged" in text for text in memory(email, "tutor")) and any("approved a held writing result unchanged" in text for text in memory(email, "quality"))
        assert case_id not in [n["case_id"] for n in client.get("/api/instructor/availability", headers=ih).json()["notifications"]]


def learner_headers(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": "Example123!"}).json()["token"]
    return {"Authorization": "Bearer " + token}


def test_2a_unavailable_instructor_queues_the_case_and_is_notified_when_available():
    email = "uc8-queue@example.com"
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        try:
            assert client.put("/api/instructor/availability", headers=ih, json={"available": False}).json() == {"available": False, "released": 0}
            case_id, _ = make_case(email)
            assert detail(client, ih, case_id)["status"] == "QUEUED"
            assert case_id not in [n["case_id"] for n in client.get("/api/instructor/availability", headers=ih).json()["notifications"]]
            assert client.get("/api/instructor/availability", headers=ih).json()["queued"] >= 1
            blocked = approve(client, ih, case_id)
            assert blocked.status_code == 409 and "queued" in blocked.json()["detail"]  # it is not silently resolved
            released = client.put("/api/instructor/availability", headers=ih, json={"available": True}).json()
            assert released["available"] is True and released["released"] >= 1
            view = detail(client, ih, case_id)
            assert view["status"] == "PENDING" and "case_queued" in [e["event"] for e in view["history"]] and "case_released_from_queue" in [e["event"] for e in view["history"]]
            assert case_id in [n["case_id"] for n in client.get("/api/instructor/availability", headers=ih).json()["notifications"]]
            assert approve(client, ih, case_id).status_code == 200
        finally:
            client.put("/api/instructor/availability", headers=ih, json={"available": True})


def test_4_conflicting_results_and_low_confidence_are_highlighted():
    email = "uc8-highlights@example.com"
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        for _ in range(3):
            add_released(email, estimate=5.5)
        payload = feedback(estimate=8.0, confidence=0.5, summary="Excellent work with no weaknesses at all.")
        payload["criteria"]["grammar"] = 3.0  # an "excellent" summary next to a very low score
        case_id, _ = make_case(email, payload=payload)
        found = detail(client, ih, case_id)["highlights"]
        kinds = {h["type"] for h in found}
        assert {"low_confidence", "conflict"} <= kinds
        details = " ".join(h["detail"] for h in found)
        assert "recent writing average of 5.5" in details and "contradiction" in details
        low = [h for h in found if h["type"] == "low_confidence"]
        assert len(low) == 1 and len(low[0]["fields"]) == 4  # one highlight naming every criterion below the threshold


def test_3a_insufficient_context_keeps_the_case_open_and_gathers_evidence():
    email = "uc8-context@example.com"
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        payload = {"summary": "Too thin to judge.", "confidence": {}}
        case_id, _ = make_case(email, payload=payload, issues=("Missing or invalid structured output/confidence",))
        before = detail(client, ih, case_id)
        assert len(before["missing_context"]) == 3 and before["additional_evidence"] == []
        gathered = client.post(f"/api/instructor/cases/{case_id}/request-evidence", headers=ih).json()
        assert gathered["status"] == "PENDING"  # still open
        assert [item["label"] for item in gathered["additional_evidence"]] == ["Learner history", "Repeated issues", "Fresh consistency check"]
        assert "No earlier verified results exist" in gathered["additional_evidence"][0]["detail"]
        assert len(gathered["missing_context"]) == 2  # the agent has now confirmed there is no earlier history
        assert {"case_evidence_requested", "case_evidence_added"} <= {e["event"] for e in gathered["history"]}
        refused = approve(client, ih, case_id)
        assert refused.status_code == 422 and detail(client, ih, case_id)["status"] == "PENDING"  # cannot release what has no confidence evidence
        fixed = client.post(f"/api/instructor/cases/{case_id}/decision", headers=ih, json={"decision": "correct", "note": "Replaced the incomplete result.", "correction": feedback()})
        assert fixed.status_code == 200 and fixed.json()["status"] == "RESOLVED"


def test_5c_request_information_keeps_the_case_open_and_returns_it_for_review():
    email = "uc8-info@example.com"
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        add_released(email)
        case_id, package_id = make_case(email)
        asked = client.post(f"/api/instructor/cases/{case_id}/decision", headers=ih, json={"decision": "request_information", "note": "Need the learner's earlier writing before deciding."})
        assert asked.status_code == 200 and asked.json()["status"] == "MORE_INFO" and asked.json()["package"]["state"] == "HUMAN_REVIEW"
        view = detail(client, ih, case_id)
        assert view["status"] == "MORE_INFO" and view["additional_evidence"]  # the information came back with the case
        assert "Learner history" in [item["label"] for item in view["additional_evidence"]]
        assert "payload" not in client.get(f"/api/results/{package_id}", headers=learner_headers(client, email)).json()  # the learner still sees nothing
        assert case_id in [n["case_id"] for n in client.get("/api/instructor/availability", headers=ih).json()["notifications"]]
        assert approve(client, ih, case_id, "Having seen the history, the result is consistent.").json()["status"] == "RESOLVED"


def test_5b_override_replaces_the_result_and_tells_the_agents():
    email = "uc8-override@example.com"
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        case_id, package_id = make_case(email)
        corrected = {**feedback(estimate=5.0, confidence=0.9), "summary": "Instructor-corrected feedback for this response."}
        corrected["criteria"] = {key: 5.0 for key in CRITERIA}
        done = client.post(f"/api/instructor/cases/{case_id}/decision", headers=ih, json={"decision": "correct", "note": "Scores were too generous.", "correction": corrected})
        assert done.status_code == 200 and done.json()["status"] == "RESOLVED"
        shown = client.get(f"/api/results/{package_id}", headers=learner_headers(client, email)).json()
        assert shown["state"] == "RELEASED" and shown["payload"]["summary"] == "Instructor-corrected feedback for this response."
        assert any("overrode" in text for text in memory(email, "tutor"))
        assert any(e["event"] == "decision:correct" and "too generous" in e["detail"] for e in detail(client, ih, case_id)["history"])
        timeline = [e["detail"] for e in detail(client, ih, case_id)["history"] if e["event"] == "decision:correct"]
        assert timeline == ["Instructor overrode the AI result with a corrected one. Reasoning: Scores were too generous."]  # reads as one sentence
        assert any("Instructor overrode a held writing result with a corrected one" in text for text in memory(email, "tutor"))


def test_7a_failed_notification_keeps_the_case_resolved_and_is_retried(monkeypatch):
    email = "uc8-notify@example.com"
    real = agent_core.remember

    def tutor_unreachable(db, agent, *args, **kwargs):
        if agent == "tutor":
            raise ConnectionError("tutor unavailable")
        return real(db, agent, *args, **kwargs)
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        first, _ = make_case(email)
        second, _ = make_case(email)
        monkeypatch.setattr(agent_core, "remember", tutor_unreachable)
        done = approve(client, ih, first)
        assert done.status_code == 200 and done.json()["status"] == "RESOLVED" and done.json()["notifications_pending"] == ["tutor"]
        view = detail(client, ih, first)
        assert view["status"] == "RESOLVED" and {d["key"]: d["status"] for d in view["agent_delivery"]} == {"quality": "delivered", "tutor": "pending"}
        assert any("failed" in e["detail"] for e in view["history"] if e["event"] == "case_agent_notification_failed")
        assert not any("approved a held writing result unchanged" in text for text in memory(email, "tutor"))
        monkeypatch.setattr(agent_core, "remember", real)  # the tutor is reachable again
        retried = client.post(f"/api/instructor/cases/{first}/retry-notifications", headers=ih).json()
        assert retried == {"delivered": 1, "notifications_pending": []}
        assert any("approved a held writing result unchanged" in text for text in memory(email, "tutor"))
        # the scheduled job does the same for cases nobody retried by hand
        monkeypatch.setattr(agent_core, "remember", tutor_unreachable)
        assert approve(client, ih, second).json()["notifications_pending"] == ["tutor"]
        monkeypatch.setattr(agent_core, "remember", real)
        with SessionLocal.begin() as db:
            assert escalation.retry_all_pending(db) == 1
        with SessionLocal.begin() as db:
            assert escalation.retry_all_pending(db) == 0
        assert client.post(f"/api/instructor/cases/{second}/retry-notifications", headers=ih).json()["delivered"] == 0
        assert client.post(f"/api/instructor/cases/{make_case(email)[0]}/retry-notifications", headers=ih).status_code == 409  # an open case has no outcome yet


def test_instructor_endpoints_are_instructor_only_and_unknown_cases_404():
    with TestClient(app) as client:
        headers = learner(client, "uc8-access@example.com")
        ih = instructor(client)
        for method, path in (("get", "/api/instructor/cases/1"), ("get", "/api/instructor/availability"), ("post", "/api/instructor/cases/1/request-evidence"), ("post", "/api/instructor/cases/1/retry-notifications")):
            assert getattr(client, method)(path, headers=headers).status_code == 403, path
        assert client.put("/api/instructor/availability", headers=headers, json={"available": False}).status_code == 403
        assert client.get("/api/instructor/cases/999999", headers=ih).status_code == 404


def test_a_result_held_by_the_quality_manager_reaches_the_instructor():
    """UC9 hands over to UC8: a malformed generated result is held, escalated, notified and can be resolved."""
    email = "uc8-handover@example.com"
    with TestClient(app) as client:
        headers = learner(client, email)
        plan = client.post("/api/plans/generate", headers=headers).json()
        assert client.post(f"/api/plans/{plan['id']}/decision?accept=true", headers=headers).status_code == 200
        practice = client.post("/api/practice/writing", headers=headers).json()
        held = client.post(f"/api/practice/{practice['id']}/submit", headers=headers, json={"text": "This response is deliberately malformed for quality checking.", "scenario": "invalid"}).json()["result"]
        assert held["state"] == "HELD"
        ih = instructor(client)
        case = next(c for c in client.get("/api/instructor/cases", headers=ih).json() if c["package"]["id"] == held["id"])
        assert case["status"] == "PENDING" and case["id"] in [n["case_id"] for n in client.get("/api/instructor/availability", headers=ih).json()["notifications"]]
        view = detail(client, ih, case["id"])
        assert view["highlights"] and view["history"][0]["event"] == "escalated" and "instructor_notified" in [e["event"] for e in view["history"]]


def test_a_cases_history_and_pending_deliveries_survive_a_busy_audit_log():
    """The case records are found by case id, not by scanning the newest audit rows, so an old case on a busy system is not forgotten."""
    from backend.models import AuditLog
    email = "uc8-busy@example.com"
    with TestClient(app) as client:
        learner(client, email)
        ih = instructor(client)
        case_id, _ = make_case(email)
        with SessionLocal.begin() as db:
            escalation.log(db, None, "case_agent_notification_failed", case_id, agent="tutor", attempt=1, error="ConnectionError")
            db.flush()
            db.add_all(AuditLog(user_id=None, action=action, detail={"case_id": 900000 + n, "agent": "tutor", "attempt": 1}) for n in range(900) for action in ("case_agent_notified", "case_agent_notification_failed"))
        with SessionLocal() as db:
            assert escalation.pending_agents(db, case_id) == ["tutor"]  # the failed delivery is still known, so it will still be retried
        events = [e["event"] for e in detail(client, ih, case_id)["history"]]
        assert events[0] == "escalated" and "instructor_notified" in events and "case_agent_notification_failed" in events
