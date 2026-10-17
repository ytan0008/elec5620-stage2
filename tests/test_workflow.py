import os
from pathlib import Path
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["DEMO_MODE"] = "true"
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import Base, engine


def setup_module():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def register(client, email="learner@example.com"):
    return client.post("/api/auth/register", json={"email": email, "name": "Test Learner", "password": "Example123!", "exam": "IELTS", "proficiency": "intermediate", "target_score": 7, "exam_date": "2026-12-15", "weekly_hours": 8, "priority_skills": ["writing", "speaking"]})


def auth(client, email="learner@example.com"):
    response = register(client, email)
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def speak_mock(client, headers, mock_id):
    session = client.post("/api/speaking/sessions", headers=headers, json={"mock_id": mock_id})
    assert session.status_code == 200, session.text
    sid = session.json()["id"]
    for _ in range(40):
        stage = client.get(f"/api/speaking/sessions/{sid}", headers=headers).json()["ui"]["stage"]
        if stage == "done":
            break
        body = {"event": "ready"} if stage == "p2_prep" else {"text": "I would say it is important because it helps people grow, for example when I learned to cook with my grandmother.", "seconds": 12}
        assert client.post(f"/api/speaking/sessions/{sid}/turn", headers=headers, json=body).status_code == 200
    finished = client.post(f"/api/speaking/sessions/{sid}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["saved_to_mock"] is True


def active_plan(client, headers):
    response = client.post("/api/plans/generate", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["package"]["state"] == "RELEASED"
    plan_id = response.json()["id"]
    assert client.post(f"/api/plans/{plan_id}/decision?accept=true", headers=headers).status_code == 200
    return plan_id


def test_contextual_agent_chat_persists_and_respects_roles():
    with TestClient(app) as client:
        headers = auth(client, "chat@example.com")
        first = client.post("/api/chat/profile", headers=headers, json={"message": "What is my goal?"})
        assert first.status_code == 200, first.text
        assert first.json()["agent"] == "Learning Coordinator"
        assert "IELTS 7" in first.json()["messages"][-1]["text"]
        follow_up = client.post("/api/chat/speaking", headers=headers, json={"message": "Hello, let's practice."})
        assert follow_up.status_code == 200, follow_up.text
        assert follow_up.json()["agent"] == "AI Tutor"
        assert follow_up.json()["mode"] == "LOCAL"
        assert follow_up.json()["messages"][-1]["text"].endswith("?")
        assert len(client.get("/api/chat/profile", headers=headers).json()["messages"]) == 2
        assert len(client.get("/api/chat/speaking", headers=headers).json()["messages"]) == 2
        other = auth(client, "otherchat@example.com")
        assert client.get("/api/chat/profile", headers=other).json()["messages"] == []
        assert client.get("/api/chat/mock", headers=headers).status_code == 404
        instructor_token = client.post("/api/auth/login", json={"email": "instructor@example.com", "password": "ChangeMe123!"}).json()["token"]
        assert client.get("/api/chat/profile", headers={"Authorization": "Bearer " + instructor_token}).status_code == 403


def test_registration_plan_quality_and_human_review():
    with TestClient(app) as client:
        bad = client.post("/api/auth/register", json={"email": "bad", "name": "X"})
        assert bad.status_code == 422
        headers = auth(client)
        active_plan(client, headers)
        task = client.post("/api/practice/writing", headers=headers).json()
        good = client.post(f"/api/practice/{task['id']}/submit", headers=headers, json={"text": "Remote work has benefits. Workers can save time and use that time to support clients more effectively. Employers should still provide routines for communication."})
        assert good.status_code == 200, good.text
        assert good.json()["result"]["state"] == "RELEASED"
        low = client.post(f"/api/practice/{task['id']}/submit", headers=headers, json={"text": "This second attempt is deliberately uncertain and should stay with the instructor for review.", "scenario": "low_confidence"})
        assert low.status_code == 200, low.text
        assert low.json()["result"]["state"] == "HELD"
        assert "payload" not in low.json()["result"]
        held_id = low.json()["result"]["id"]
        assert client.get("/api/events", headers=headers).status_code == 403
        contradiction = client.post(f"/api/practice/{task['id']}/submit", headers=headers, json={"text": "This third response demonstrates a contradiction in the rubric evaluation.", "scenario": "contradiction"})
        assert contradiction.json()["result"]["state"] == "HELD"
        assert client.get("/api/instructor/cases", headers=headers).status_code == 403
        dev = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": "instructor@example.com", "password": "ChangeMe123!"}).json()["token"]}
        assert all("result" not in event["detail"] for event in client.get("/api/events", headers=dev).json() if event["detail"].get("package_id") == held_id)
        instructor_token = client.post("/api/auth/login", json={"email": "instructor@example.com", "password": "ChangeMe123!"}).json()["token"]
        ih = {"Authorization": "Bearer " + instructor_token}
        cases = client.get("/api/instructor/cases", headers=ih).json()
        assert len(cases) >= 2
        case = next(item for item in cases if item["package"]["id"] == low.json()["result"]["id"])
        approved = client.post(f"/api/instructor/cases/{case['id']}/decision", headers=ih, json={"decision": "approve", "note": "I checked the response manually."})
        assert approved.status_code == 200, approved.text
        assert client.get(f"/api/results/{low.json()['result']['id']}", headers=headers).json()["state"] == "RELEASED"
        other = next(item for item in cases if item["package"]["id"] == contradiction.json()["result"]["id"])
        corrected = client.post(f"/api/instructor/cases/{other['id']}/decision", headers=ih, json={"decision": "correct", "note": "The previous praise was inconsistent.", "correction": {"summary": "The response needs substantial development."}})
        assert corrected.status_code == 200, corrected.text
        assert client.get("/api/instructor/audit", headers=ih).json()
        report = client.post("/api/reports", headers=headers)
        assert report.status_code == 200, report.text
        adaptation = client.post("/api/plans/generate?adapt=true", headers=headers)
        assert adaptation.status_code == 200, adaptation.text
        assert client.post(f"/api/plans/{adaptation.json()['id']}/decision?accept=false", headers=headers).status_code == 200
        assert any(plan["status"] == "ACTIVE" for plan in client.get("/api/plans", headers=headers).json())


def test_speaking_mock_resume_recommendations_ownership():
    with TestClient(app) as client:
        headers = auth(client, "second@example.com")
        active_plan(client, headers)
        speaking = client.post("/api/practice/speaking", headers=headers).json()
        audio = client.post(f"/api/practice/{speaking['id']}/audio", headers=headers, files={"file": ("speech.webm", b"demo-audio-data", "audio/webm")})
        assert audio.status_code == 200, audio.text
        assert audio.json()["transcription_available"] is False
        response = client.post(f"/api/practice/{speaking['id']}/submit", headers=headers, json={"text": "I learned presentation skills through regular practice with my team and applied them in a client meeting."})
        assert response.status_code == 200, response.text
        assert response.json()["result"]["payload"]["pronunciation_available"] is False
        attempt = client.get(f"/api/practice/{speaking['id']}/attempts", headers=headers).json()[0]
        assert attempt["audio_available"] is True
        assert client.get(f"/api/practice/submissions/{attempt['id']}/audio", headers=headers).content == b"demo-audio-data"
        mock = client.post("/api/mock-exams", headers=headers)
        assert mock.status_code == 200, mock.text
        exam_id = mock.json()["id"]
        assert all("answer" not in q for g in mock.json()["sections"]["listening"]["sections"][0]["groups"] for q in g["questions"])
        assert client.post(f"/api/mock-exams/{exam_id}/submit", headers=headers).status_code == 409
        import json
        tasks = {task["task"]: "I think remote work offers meaningful flexibility while teams need clear routines to collaborate effectively." for task in mock.json()["sections"]["writing"]["tasks"]}
        for skill, answer in {"reading": {"1": "TRUE"}, "listening": {"1": "Kowalski"}, "writing": tasks}.items():
            assert client.put(f"/api/mock-exams/{exam_id}/{skill}", headers=headers, json={"answer": json.dumps(answer)}).status_code == 200
        speak_mock(client, headers, exam_id)
        with TestClient(app) as resumed_client:
            assert len(resumed_client.get(f"/api/mock-exams/{exam_id}", headers=headers).json()["answers"]) == 4
        assert len(client.get(f"/api/mock-exams/{exam_id}", headers=headers).json()["answers"]) == 4
        completed = client.post(f"/api/mock-exams/{exam_id}/submit", headers=headers)
        assert completed.status_code == 200, completed.text
        assert completed.json()["result"]["state"] == "RELEASED"
        assert client.post("/api/materials/recommend", headers=headers).json()["state"] == "RELEASED"
        assert client.get("/api/analytics", headers=headers).json()["sample_count"] >= 2
        other = auth(client, "third@example.com")
        assert client.get(f"/api/practice/submissions/{attempt['id']}/audio", headers=other).status_code == 404
        assert client.get(f"/api/mock-exams/{exam_id}", headers=other).status_code == 404
        assert client.get(f"/api/results/{response.json()['result']['id']}", headers=other).status_code == 404


def test_invalid_output_and_adaptation_preserve_release_boundary():
    with TestClient(app) as client:
        headers = auth(client, "fourth@example.com")
        invalid_profile = client.put("/api/profile", headers=headers, json={"exam": "TOEFL", "proficiency": "advanced", "target_score": 8, "exam_date": "2027-01-20", "weekly_hours": 6, "priority_skills": ["reading"]})
        assert invalid_profile.status_code == 422
        assert client.post("/api/mock-exams", headers=headers).status_code == 409
        assert client.post("/api/reports", headers=headers).status_code == 409
        active_plan(client, headers)
        practice = client.post("/api/practice/writing", headers=headers).json()
        malformed = client.post(f"/api/practice/{practice['id']}/submit", headers=headers, json={"text": "This response is deliberately malformed for quality checking.", "scenario": "invalid"})
        assert malformed.status_code == 200, malformed.text
        held_id = malformed.json()["result"]["id"]
        assert "payload" not in client.get(f"/api/results/{held_id}", headers=headers).json()
        instructor_token = client.post("/api/auth/login", json={"email": "instructor@example.com", "password": "ChangeMe123!"}).json()["token"]
        ih = {"Authorization": "Bearer " + instructor_token}
        case = next(case for case in client.get("/api/instructor/cases", headers=ih).json() if case["package"]["id"] == held_id)
        info = client.post(f"/api/instructor/cases/{case['id']}/decision", headers=ih, json={"decision": "request_information", "note": "Need more evidence."})
        assert info.status_code == 200
        assert info.json()["package"]["state"] == "HUMAN_REVIEW"
        assert "payload" not in client.get(f"/api/results/{held_id}", headers=headers).json()
        assert client.post(f"/api/instructor/cases/{case['id']}/decision", headers=ih, json={"decision": "approve", "note": "Cannot approve incomplete output."}).status_code == 422
        approved = client.post(f"/api/instructor/cases/{case['id']}/decision", headers=ih, json={"decision": "correct", "note": "Replaced invalid output.", "correction": {"summary": "Human reviewed this short writing response.", "criteria": {"task_response": 5.0}, "comments": [{"issue": "Short response", "suggestion": "Add more evidence."}], "confidence": {"task_response": 1.0}}})
        assert approved.status_code == 200
        assert client.get(f"/api/results/{held_id}", headers=headers).json()["state"] == "RELEASED"
        proposal = client.post("/api/plans/generate?adapt=true", headers=headers).json()
        assert proposal["package"]["state"] == "RELEASED"
        accepted = client.post(f"/api/plans/{proposal['id']}/decision?accept=true", headers=headers)
        assert accepted.status_code == 200
        plans = client.get("/api/plans", headers=headers).json()
        assert sum(plan["status"] == "ACTIVE" for plan in plans) == 1
        materials = client.get("/api/materials?skill=writing", headers=headers).json()
        assert materials and all(item["skill"] == "writing" for item in materials)
        assert client.post(f"/api/materials/{materials[0]['id']}/interaction?relevant=true", headers=headers).json()["relevant"] is True
        assert client.put("/api/instructor/quality/threshold", headers=headers, json={"value": .9}).status_code == 403
        assert client.put("/api/instructor/quality/threshold", headers=ih, json={"value": .9}).status_code == 200
        high_threshold = client.post(f"/api/practice/{practice['id']}/submit", headers=headers, json={"text": "This otherwise normal answer should be held under the instructor's higher threshold."})
        assert high_threshold.json()["result"]["state"] == "HELD"
        assert client.put("/api/instructor/quality/threshold", headers=ih, json={"value": .7}).status_code == 200


def test_weekly_adaptation_is_idempotent():
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from backend.db import SessionLocal
    from backend.models import Plan
    from backend.scheduled_review import run
    with TestClient(app) as client:
        headers = auth(client, "scheduled@example.com")
        plan_id = active_plan(client, headers)
        with SessionLocal.begin() as db:
            plan = db.get(Plan, plan_id)
            plan.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        run()
        first = client.get("/api/plans", headers=headers).json()
        assert any(item["kind"] == "adaptation" and item["status"] == "PROPOSED" for item in first)
        run()
        second = client.get("/api/plans", headers=headers).json()
        assert len(second) == len(first)


def test_plan_change_request_changes_priority():
    with TestClient(app) as client:
        headers = auth(client, "revision@example.com")
        original = client.post("/api/plans/generate", headers=headers).json()
        revised = client.post(f"/api/plans/{original['id']}/request-changes", headers=headers, json={"note": "more speaking practice"})
        assert revised.status_code == 200, revised.text
        plans = client.get("/api/plans", headers=headers).json()
        new_plan = next(plan for plan in plans if plan["id"] == revised.json()["id"])
        assert new_plan["content"]["priorities"][0] == "speaking"
        assert next(plan for plan in plans if plan["id"] == original["id"])["status"] == "REJECTED"
        assert client.post(f"/api/plans/{new_plan['id']}/decision?accept=true", headers=headers).status_code == 200


def test_without_api_key_the_local_engine_runs_everything():
    from backend.config import settings
    with TestClient(app) as client:
        headers = auth(client, "no-key@example.com")
        config = settings()
        original_mode, original_key = config.demo_mode, config.openai_api_key
        try:
            config.demo_mode = False
            config.openai_api_key = ""
            assert client.get("/api/health").json()["mode"] == "LOCAL"
            practice = client.post("/api/practice/writing", headers=headers)
            assert practice.status_code == 200
            assert practice.json()["prompt"]["mode"] == "ORIGINAL"
            unavailable = client.post("/api/questions/generate", headers=headers, json={"skill": "listening", "topic": "museums"})
            assert unavailable.status_code == 409
            assert "cloud AI" in unavailable.json()["detail"]
            assert client.post("/api/tts", headers=headers, json={"text": "Hello"}).status_code == 404
        finally:
            config.demo_mode, config.openai_api_key = original_mode, original_key


def test_password_recovery_is_one_use_and_revokes_existing_sessions():
    from urllib.parse import parse_qs, urlparse
    from datetime import datetime, timedelta, timezone
    from backend.db import SessionLocal
    from backend.models import PasswordReset
    from backend.recovery import token_digest
    from sqlalchemy import select

    with TestClient(app) as client:
        headers = auth(client, "recover@example.com")
        unknown = client.post("/api/auth/password-reset/request", json={"email": "unknown@example.com"})
        issued = client.post("/api/auth/password-reset/request", json={"email": "recover@example.com"})
        assert issued.status_code == 200
        assert unknown.json()["message"] == issued.json()["message"]
        assert "LOCAL SERVER" in issued.json()["notice"]
        old_token = parse_qs(urlparse(issued.json()["reset_path"]).query)["token"][0]
        assert client.post("/api/auth/password-reset/confirm", json={"token": "x" * 32, "password": "NewPassword123!"}).status_code == 400
        second = client.post("/api/auth/password-reset/request", json={"email": "recover@example.com"}).json()
        token = parse_qs(urlparse(second["reset_path"]).query)["token"][0]
        assert client.post("/api/auth/password-reset/confirm", json={"token": old_token, "password": "NewPassword123!"}).status_code == 400
        assert client.post("/api/auth/password-reset/confirm", json={"token": token, "password": "short"}).status_code == 422
        changed = client.post("/api/auth/password-reset/confirm", json={"token": token, "password": "NewPassword123!"})
        assert changed.status_code == 200, changed.text
        assert client.post("/api/auth/password-reset/confirm", json={"token": token, "password": "AnotherPassword123!"}).status_code == 400
        assert client.post("/api/auth/login", json={"email": "recover@example.com", "password": "Example123!"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "recover@example.com", "password": "NewPassword123!"}).status_code == 200
        assert client.get("/api/me", headers=headers).status_code == 401
        expired = client.post("/api/auth/password-reset/request", json={"email": "recover@example.com"}).json()
        expired_token = parse_qs(urlparse(expired["reset_path"]).query)["token"][0]
        with SessionLocal.begin() as db:
            record = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_digest(expired_token)))
            record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert client.post("/api/auth/password-reset/confirm", json={"token": expired_token, "password": "AnotherPassword123!"}).status_code == 400


def test_password_recovery_requires_mail_delivery_outside_demo():
    from backend.config import settings
    config = settings()
    original_mode, original_host, original_screen = config.demo_mode, config.smtp_host, config.password_reset_link_on_screen
    try:
        config.demo_mode = False
        config.smtp_host = ""
        config.password_reset_link_on_screen = False
        with TestClient(app) as client:
            response = client.post("/api/auth/password-reset/request", json={"email": "someone@example.com"})
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]
    finally:
        config.demo_mode, config.smtp_host, config.password_reset_link_on_screen = original_mode, original_host, original_screen


def test_password_recovery_email_delivery_and_failure(monkeypatch):
    from backend.config import settings
    from backend.db import SessionLocal
    from backend.models import PasswordReset, User
    from sqlalchemy import select, func
    import backend.main as main_module

    config = settings()
    original = (config.demo_mode, config.smtp_host, config.smtp_from_email)
    delivered = []
    try:
        config.demo_mode = False
        config.smtp_host = "smtp.example.com"
        config.smtp_from_email = "noreply@example.com"
        monkeypatch.setattr(main_module, "send_reset_email", lambda address, token: delivered.append((address, token)))
        with TestClient(app) as client:
            register(client, "mail-recover@example.com")
            issued = client.post("/api/auth/password-reset/request", json={"email": "mail-recover@example.com"})
            assert issued.status_code == 200
            assert "reset_path" not in issued.json()
            assert delivered[0][0] == "mail-recover@example.com"
            assert client.post("/api/auth/password-reset/confirm", json={"token": delivered[0][1], "password": "MailedPassword123!"}).status_code == 200
            assert client.post("/api/auth/login", json={"email": "mail-recover@example.com", "password": "MailedPassword123!"}).status_code == 200

            def failed_delivery(address, token):
                raise OSError("mail unavailable")

            monkeypatch.setattr(main_module, "send_reset_email", failed_delivery)
            with SessionLocal() as db:
                user_id = db.scalar(select(User.id).where(User.email == "mail-recover@example.com"))
                before = db.scalar(select(func.count()).select_from(PasswordReset).where(PasswordReset.user_id == user_id))
            failed = client.post("/api/auth/password-reset/request", json={"email": "mail-recover@example.com"})
            assert failed.status_code == 503
            with SessionLocal() as db:
                after = db.scalar(select(func.count()).select_from(PasswordReset).where(PasswordReset.user_id == user_id))
            assert after == before
    finally:
        config.demo_mode, config.smtp_host, config.smtp_from_email = original


def test_conversational_onboarding_portrait_questions_and_graph():
    with TestClient(app) as client:
        registered = client.post("/api/auth/register", json={"email": "new-onboarding@example.com", "name": "New Learner", "password": "Example123!"})
        assert registered.status_code == 200, registered.text
        assert registered.json()["user"]["profile_complete"] is False
        headers = {"Authorization": "Bearer " + registered.json()["token"]}
        assert client.get("/api/profile", headers=headers).status_code == 409
        assert client.get("/api/onboarding", headers=headers).json()["next_field"] == "exam"
        for answer in ("IELTS", "intermediate", "7.0", "2027-12-15", "8", "writing and speaking"):
            turn = client.post("/api/onboarding/message", headers=headers, json={"message": answer})
            assert turn.status_code == 200, turn.text
        assert turn.json()["ready"] is True
        assert len(turn.json()["messages"]) == 12
        confirmed = client.post("/api/onboarding/confirm", headers=headers)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["portrait"]["state"] == "RELEASED"
        assert confirmed.json()["portrait"]["source_mode"] == "LOCAL"
        assert client.get("/api/portrait", headers=headers).json()["payload"]["focus_areas"] == ["writing", "speaking"]
        assert client.post("/api/onboarding/confirm", headers=headers).status_code == 409
        logged_in = client.post("/api/auth/login", json={"email": "new-onboarding@example.com", "password": "Example123!"})
        assert logged_in.json()["user"]["profile_complete"] is True

        graph = client.get("/api/knowledge-graph", headers=headers)
        assert graph.status_code == 200
        assert len(graph.json()["nodes"]) == 17
        assert len(graph.json()["edges"]) == 16
        assert all(node["score"] is None for node in graph.json()["nodes"])
        assert next(node for node in graph.json()["nodes"] if node["id"] == "writing")["priority"] is True
        questions = client.get("/api/questions?skill=writing", headers=headers).json()
        assert any(item["source_kind"] == "OFFICIAL_LINK" and item["source_url"].startswith("https://ielts.org/") and item["prompt"] is None for item in questions)
        original = next(item for item in questions if item["source_kind"] == "ORIGINAL")
        practice = client.post(f"/api/practice/writing?question_id={original['id']}", headers=headers)
        assert practice.status_code == 200
        assert practice.json()["prompt"]["text"] == original["prompt"]
        generated = client.post("/api/questions/generate", headers=headers, json={"skill": "speaking", "topic": "public libraries"})
        assert generated.status_code == 200, generated.text
        assert generated.json()["source_kind"] == "LOCAL_GENERATED"
        assert generated.json()["verification_state"] == "RELEASED"
        assert client.post(f"/api/practice/speaking?question_id={generated.json()['id']}", headers=headers).status_code == 200

        other = auth(client, "question-other@example.com")
        assert client.post(f"/api/practice/speaking?question_id={generated.json()['id']}", headers=other).status_code == 404
        active_plan(client, headers)
        mock = client.post("/api/mock-exams", headers=headers)
        assert mock.status_code == 200
        assert mock.json()["duration_seconds"] == (16 + 20 + 40 + 14) * 60
        full = client.post("/api/mock-exams", headers=headers, json={"length": "full"})
        assert len(full.json()["sections"]["listening"]["sections"]) == 4
        assert len(full.json()["sections"]["reading"]["sections"]) == 3
        assert [task["task"] for task in full.json()["sections"]["writing"]["tasks"]] == ["task1", "task2"]
        assert mock.json()["created_at"]


def test_generated_question_is_held_when_quality_fails(monkeypatch):
    from backend.agents import ProviderAdapter
    from backend.schemas import QuestionOutput

    with TestClient(app) as client:
        headers = auth(client, "question-hold@example.com")
        def uncertain(self, exam, skill, topic, task="auto"):
            return {"title": "A practice discussion task", "prompt": "Discuss whether libraries should be free and explain your answer with examples.", "task_type": "Academic Task 2", "confidence": {"task": .2}}
        monkeypatch.setattr(ProviderAdapter, "generate_question", uncertain)
        result = client.post("/api/questions/generate", headers=headers, json={"skill": "writing", "topic": "libraries"})
        assert result.status_code == 200
        assert result.json()["verification_state"] == "HELD"
        assert result.json()["prompt"] is None
        assert client.post(f"/api/practice/writing?question_id={result.json()['id']}", headers=headers).status_code in (404, 409)


def test_existing_learner_can_create_a_quality_checked_portrait():
    with TestClient(app) as client:
        headers = auth(client, "portrait-existing@example.com")
        assert client.get("/api/portrait", headers=headers).json() is None
        created = client.post("/api/portrait/generate", headers=headers)
        assert created.status_code == 200
        assert created.json()["state"] == "RELEASED"
        assert client.get("/api/portrait", headers=headers).json()["id"] == created.json()["id"]


def test_listening_and_reading_are_marked_against_hidden_keys():
    from backend import content
    with TestClient(app) as client:
        headers = auth(client, "objective@example.com")
        bank = client.get("/api/questions?skill=listening", headers=headers).json()
        part = next(item for item in bank if item["title"] == "Evening course enrolment")
        practice = client.post(f"/api/practice/listening?question_id={part['id']}", headers=headers)
        assert practice.status_code == 200, practice.text
        test = practice.json()["prompt"]["test"]
        assert test["sections"][0]["script"], "script is needed for text-to-speech"
        assert all("answer" not in q and "accepts" not in q for g in test["sections"][0]["groups"] for q in g["questions"])
        answers = {"1": "kowalski", "2": "Elmfield", "3": "07946 381 552", "4": "the newspaper", "5": "£95", "6": "apron", "7": "three", "8": "7:15", "9": "Library", "10": "wrong"}
        submitted = client.post(f"/api/practice/{practice.json()['id']}/submit", headers=headers, json={"answers": answers})
        assert submitted.status_code == 200, submitted.text
        result = submitted.json()["result"]
        assert result["state"] == "RELEASED"
        assert result["payload"]["raw_score"] == 9
        assert result["payload"]["estimated_overall"] == 8.0
        assert result["payload"]["transcript"][0]["script"]
        assert not next(item for item in result["payload"]["review"] if item["n"] == 10)["correct"]
        reading = client.post("/api/practice/reading", headers=headers).json()
        assert reading["prompt"]["test"]["sections"][0]["passage"]
        empty = client.post(f"/api/practice/{reading['id']}/submit", headers=headers, json={"answers": {}})
        assert empty.json()["result"]["payload"]["raw_score"] == 0


def test_live_ielts_speaking_examiner_runs_all_three_parts():
    with TestClient(app) as client:
        headers = auth(client, "examiner@example.com")
        session = client.post("/api/speaking/sessions", headers=headers, json={"persona": "boy"})
        assert session.status_code == 200, session.text
        sid = session.json()["id"]
        assert "Kai" in session.json()["log"][0]["text"]
        parts = []
        for _ in range(40):
            view = client.get(f"/api/speaking/sessions/{sid}", headers=headers).json()
            parts.append(view["ui"]["part"])
            if view["ui"]["stage"] == "done":
                break
            if view["ui"]["stage"] == "p2_prep":
                assert client.post(f"/api/speaking/sessions/{sid}/turn", headers=headers, json={"text": "too early"}).status_code == 409
                body = {"event": "ready"}
            else:
                body = {"text": "Well, I really enjoy it because it gives me a chance to relax, and for example last weekend I spent the afternoon there with my friends.", "seconds": 9}
            turn = client.post(f"/api/speaking/sessions/{sid}/turn", headers=headers, json=body)
            assert turn.status_code == 200, turn.text
        assert {"Part 1", "Part 2", "Part 3", "Complete"} <= set(parts)
        finished = client.post(f"/api/speaking/sessions/{sid}/finish", headers=headers)
        assert finished.status_code == 200, finished.text
        payload = finished.json()["result"]["payload"]
        assert set(payload["criteria"]) == {"fluency", "lexical_resource", "grammar"}
        assert payload["pronunciation_available"] is False
        assert finished.json()["metrics"]["words_per_minute"] > 100
        assert client.post(f"/api/speaking/sessions/{sid}/finish", headers=headers).status_code == 409
        assert client.put("/api/me/avatar", headers=headers, json={"avatar": "boy"}).json()["avatar"] == "boy"


def test_local_writing_analysis_flags_real_errors():
    from backend.scoring import analyse_response
    weak = analyse_response("IELTS", "writing", "i think peoples is more better when they works at home. the informations is easy.", "", "task2")
    issues = " ".join(c["issue"] for c in weak["comments"])
    assert "people" in issues and "comparative" in issues and "uncountable" in issues
    assert max(weak["criteria"].values()) <= 4.5
    toefl = analyse_response("TOEFL", "writing", "Dear Ms Lin, I am writing because the meetings clash with my class. " * 6, "", "email")
    assert set(toefl["criteria"]) == {"task_fulfillment", "organisation", "language_use"}
    assert all(1 <= value <= 6 for value in toefl["criteria"].values())


def test_notebooks_memory_and_coaching(monkeypatch):
    from backend import notebook as nb
    monkeypatch.setattr(nb, "dictionary_lookup", lambda word: {"phonetic": "/test/", "meanings": [{"pos": "adjective", "definition": f"definition of {word}", "example": ""}], "synonyms": []})
    with TestClient(app) as client:
        headers = auth(client, "notebook@example.com")
        # Wrong listening answers go to the mistake book, grouped by question type.
        bank = client.get("/api/questions?skill=listening", headers=headers).json()
        part = next(item for item in bank if item["title"] == "Evening course enrolment")
        practice = client.post(f"/api/practice/listening?question_id={part['id']}", headers=headers).json()
        client.post(f"/api/practice/{practice['id']}/submit", headers=headers, json={"answers": {"1": "kowalski"}})
        mistakes = client.get("/api/notebook?kind=mistake", headers=headers).json()
        assert len(mistakes) == 9 and all(m["category"] == "Completion / gap fill" for m in mistakes)
        stats = client.get("/api/notebook/stats", headers=headers).json()
        assert stats["mistakes_by_type"][0] == {"name": "Completion / gap fill", "count": 9}
        assert stats["mistakes_by_skill"][0]["name"] == "listening"
        apron = next(m for m in mistakes if "apron" in m["detail"]["answer"])
        assert client.post(f"/api/notebook/{apron['id']}/retry", headers=headers, json={"answer": "wrong"}).json()["correct"] is False
        assert client.post(f"/api/notebook/{apron['id']}/retry", headers=headers, json={"answer": "Apron"}).json()["correct"] is True
        assert client.post(f"/api/notebook/{apron['id']}/retry", headers=headers, json={"answer": "apron"}).json()["entry"]["mastered"] is True
        # Repeating the same test merges repeated mistakes instead of duplicating them.
        again = client.post(f"/api/practice/listening?question_id={part['id']}", headers=headers).json()
        client.post(f"/api/practice/{again['id']}/submit", headers=headers, json={"answers": {}})
        assert len(client.get("/api/notebook?kind=mistake", headers=headers).json()) == 10
        # Writing errors become grammar entries; corrections become model sentences.
        writing = client.post("/api/practice/writing", headers=headers).json()
        client.post(f"/api/practice/{writing['id']}/submit", headers=headers, json={"text": "I think peoples is more better when they work at home. The informations about this topic is easy to find for everyone."})
        grammar = client.get("/api/notebook?kind=grammar", headers=headers).json()
        assert any("people" in g["category"].lower() for g in grammar)
        assert client.get("/api/notebook?kind=sentence", headers=headers).json()
        # Words: from the tutor chat in English and Chinese, and from a selection.
        chat = client.post("/api/chat/tutor", headers=headers, json={"message": "I don't know the word ubiquitous"}).json()
        assert any(e["type"] == "word" and e["word"] == "ubiquitous" for e in chat["events"])
        assert "definition of ubiquitous" in chat["messages"][-1]["text"]
        client.post("/api/chat/reading", headers=headers, json={"message": "serendipity是什么意思"})
        selected = client.post("/api/notebook", headers=headers, json={"kind": "word", "text": "Brittle,", "context": "paper turns yellow and brittle", "skill": "reading", "source": "Paper passage"}).json()
        assert selected["text"] == "brittle" and selected["detail"]["contexts"] == ["paper turns yellow and brittle"]
        words = {w["text"] for w in client.get("/api/notebook?kind=word", headers=headers).json()}
        assert {"ubiquitous", "serendipity", "brittle"} <= words
        sentence = client.post("/api/notebook", headers=headers, json={"kind": "sentence", "text": "Although cities are crowded, they offer opportunities which villages cannot match."}).json()
        assert "Concession" in sentence["category"] and "Relative clause" in sentence["category"]
        # Quiz uses a saved word and updates its review schedule.
        quiz = client.post("/api/chat/tutor", headers=headers, json={"message": "quiz me"}).json()
        word = quiz["messages"][-1]["quiz"]
        answer = client.post("/api/chat/tutor", headers=headers, json={"message": f"The {word} thing appeared in my essay today."}).json()
        assert any(e["type"] == "quiz" and e["remembered"] for e in answer["events"])
        # Memory persists across pages and can be edited.
        client.post("/api/chat/dashboard", headers=headers, json={"message": "My name is Mai and I struggle with listening for numbers."})
        memory = [m["text"] for m in client.get("/api/tutor/memory", headers=headers).json()]
        assert "Name: Mai" in memory and any(m.startswith("Struggles with listening") for m in memory)
        assert any(m.startswith("Latest verified listening estimate") for m in memory)
        recalled = client.post("/api/chat/speaking", headers=headers, json={"message": "What do you remember about me?"}).json()
        assert "Struggles with listening" in recalled["messages"][-1]["text"]
        coach = client.post("/api/tutor/coach", headers=headers).json()
        assert "Completion / gap fill" in coach["message"] and coach["messages"][-1]["coach"] is True
        # Other learners cannot touch these entries.
        other = auth(client, "notebook-other@example.com")
        assert client.delete(f"/api/notebook/{selected['id']}", headers=other).status_code == 404
        assert client.get("/api/notebook", headers=other).json() == []
        assert client.delete(f"/api/notebook/{selected['id']}", headers=headers).json()["deleted"] is True


def test_developer_console_reports_dictionary_and_exam_lock():
    with TestClient(app) as client:
        headers = auth(client, "devconsole@example.com")
        dev = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": "instructor@example.com", "password": "ChangeMe123!"}).json()["token"]}
        practice = client.post("/api/practice/writing", headers=headers).json()
        client.post(f"/api/practice/{practice['id']}/submit", headers=headers, json={"text": "A deliberately uncertain answer that must be held for review.", "scenario": "low_confidence"})
        # Learners cannot see the developer console.
        for path in ("/api/events", "/api/instructor/overview", "/api/instructor/anomalies", "/api/instructor/feedback"):
            assert client.get(path, headers=headers).status_code == 403
        events = client.get("/api/events?agent=Quality%20Manager", headers=dev).json()
        assert events and all(e["agent"] == "Quality Manager" for e in events) and any(e["user"] == "Test Learner" for e in events)
        overview = client.get("/api/instructor/overview", headers=dev).json()
        assert overview["held_7d"] >= 1 and len(overview["timeline"]) == 24 and overview["agents"]
        anomalies = client.get("/api/instructor/anomalies", headers=dev).json()
        held = next(a for a in anomalies if a["category"] == "Quality hold" and a["email"] == "devconsole@example.com")
        assert client.post("/api/instructor/anomalies/ack", headers=dev, json={"anomaly_id": held["id"]}).status_code == 200
        assert next(a for a in client.get("/api/instructor/anomalies", headers=dev).json() if a["id"] == held["id"])["acknowledged"] is True
        # Learner feedback reaches the console and the reply comes back.
        report = client.post("/api/feedback", headers=headers, json={"category": "result", "message": "My writing score looks too low.", "context": {"package_id": 1}}).json()
        assert any(a["category"] == "Learner report" for a in client.get("/api/instructor/anomalies", headers=dev).json())
        resolved = client.post(f"/api/instructor/feedback/{report['id']}/resolve", headers=dev, json={"response": "Checked and re-scored."}).json()
        assert resolved["status"] == "RESOLVED"
        assert client.get("/api/feedback", headers=headers).json()[0]["response"] == "Checked and re-scored."
        # Dictionary shows meanings outside exams.
        looked = client.get("/api/dictionary?word=Mitigate,", headers=headers).json()
        assert looked["word"] == "mitigate" and looked["translation"] and looked["saved"] is False
        # During a running mock: meanings and the tutor are locked, but words can still be saved.
        active_plan(client, headers)
        assert client.post("/api/mock-exams", headers=headers).status_code == 200
        assert client.get("/api/dictionary?word=brittle", headers=headers).status_code == 423
        assert client.post("/api/chat/dashboard", headers=headers, json={"message": "What does brittle mean?"}).status_code == 423
        saved = client.post("/api/notebook", headers=headers, json={"kind": "word", "text": "brittle", "context": "paper became brittle"}).json()
        assert saved["hidden"] is True and "translation" not in saved["detail"] and "meanings" not in saved["detail"]
        listed = client.get("/api/notebook?kind=word", headers=headers).json()
        assert listed[0]["hidden"] is True and "translation" not in listed[0]["detail"]
        from backend.db import SessionLocal
        from backend.models import NotebookEntry
        with SessionLocal() as db:
            assert db.get(NotebookEntry, saved["id"]).detail.get("translation")  # stored, revealed after the exam


def test_each_agent_has_memory_tools_and_progress_comparison():
    with TestClient(app) as client:
        headers = auth(client, "memory.agents@example.com")
        active_plan(client, headers)
        task = client.post("/api/practice/writing", headers=headers).json()
        essay = "i think peoples is more better when they works at home. the informations is easy. Companies should allow it because workers save time."
        first = client.post(f"/api/practice/{task['id']}/submit", headers=headers, json={"text": essay})
        assert first.status_code == 200, first.text
        second = client.post(f"/api/practice/{task['id']}/submit", headers=headers, json={"text": essay.replace("peoples is", "people are")}).json()["result"]
        assert second["state"] == "RELEASED"
        # The Tutor compares with its previous feedback; Assessment reports the trend from its score-history tool.
        assert {"fixed", "remaining", "criteria_change"} <= set(second["payload"]["since_last"])
        assert "change" in second["payload"]["trend"]
        instructor = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": "instructor@example.com", "password": "ChangeMe123!"}).json()["token"]}
        assert client.get("/api/instructor/agent-memory", headers=headers).status_code == 403
        memory = client.get("/api/instructor/agent-memory", headers=instructor).json()
        assert {"coordinator", "tutor", "assessment"} <= {row["agent"] for row in memory}
        tools = client.get("/api/events?limit=300", headers=instructor).json()
        assert {"get_previous_feedback", "get_score_history"} <= {e["detail"].get("tool") for e in tools if e["phase"] == "tool"}


def test_cloud_agent_loop_calls_tools_then_submits_structured_result():
    from langchain_core.messages import AIMessage
    from backend.agents import ProviderAdapter
    from backend.agent_core import Toolkit, remember
    from backend.db import SessionLocal
    from backend.schemas import VerdictOutput

    class FakeLLM:
        def __init__(self):
            self.seen = []

        def bind_tools(self, tools, tool_choice=None):
            names = [t["function"]["name"] if isinstance(t, dict) else t.name for t in tools]
            outer = self

            class Bound:
                def invoke(self, messages):
                    outer.seen.append((names, tool_choice, list(messages)))
                    if len(outer.seen) == 1:
                        return AIMessage(content="", tool_calls=[{"name": "get_quality_threshold", "args": {}, "id": "c1"}, {"name": "recall_memory", "args": {"query": "writing"}, "id": "c2"}])
                    return AIMessage(content="", tool_calls=[{"name": "submit_result", "args": {"consistent": True, "reason": "Scores match comments", "confidence": 0.9}, "id": "c3"}])
            return Bound()

    db = SessionLocal()
    try:
        remember(db, "quality", None, "Instructor approved unchanged a held writing result (likely a false alarm).", "lesson")
        adapter = ProviderAdapter()
        adapter.mode, adapter.llm = "REAL", FakeLLM()
        adapter.scorer = adapter.llm
        kit = Toolkit(db, "quality", None)
        verdict = adapter.check_consistency({"summary": "Good", "criteria": {"grammar": 6}, "comments": []}, kit)
        assert isinstance(verdict, VerdictOutput) and verdict.consistent
        names, choice, messages = adapter.llm.seen[0]
        assert choice == "required" and "get_instructor_decisions" in names and "submit_result" in names
        assert "false alarm" in messages[1].content  # The agent's own memory is in the prompt.
        assert [c["tool"] for c in kit.calls] == ["get_quality_threshold", "recall_memory"]
        assert any(m.type == "tool" for m in adapter.llm.seen[1][2])  # Tool results were returned to the model.
    finally:
        db.rollback()
        db.close()


def test_sign_in_lasts_seven_days():
    import jwt
    from datetime import datetime, timezone
    from backend.config import settings
    with TestClient(app) as client:
        token = auth(client, "session.days@example.com")["Authorization"].split()[1]
        days = (datetime.fromtimestamp(jwt.decode(token, settings().jwt_secret, algorithms=["HS256"])["exp"], timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 86400
        assert 6.9 < days <= 7
        assert client.get("/api/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
