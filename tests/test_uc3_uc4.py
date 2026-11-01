"""UC3 Speaking practice and UC4 Writing practice alternative flows 5a and 6a, against the Stage 1 specification."""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["DEMO_MODE"] = "true"
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.agents import LLMProviderAdapter
from backend.db import Base, SessionLocal, engine
from backend.main import app
from backend.models import AgentEvent, Practice, ResultPackage, SpeakingSession, Submission

ESSAY = ("Some people believe that technology has made our lives more complicated, but I think it has mostly made them easier. "
         "For example, online banking saves time and allows people to manage money from home. ") * 12
ANSWER = "Well, I really enjoy it because it gives me a chance to relax, and for example last weekend I spent the afternoon there with my friends."


def setup_module():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def learner(client, email):
    response = client.post("/api/auth/register", json={"email": email, "name": "UC3 UC4 Learner", "password": "Example123!", "exam": "IELTS", "proficiency": "intermediate",
                                                       "target_score": 7, "exam_date": "2026-12-15", "weekly_hours": 8, "priority_skills": ["writing", "speaking"]})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def feedback_fails(monkeypatch, times: int):
    """The Tutor's feedback call fails the given number of times, then works again."""
    real, calls = LLMProviderAdapter.feedback, {"n": 0}

    def flaky(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= times:
            raise TimeoutError("model did not respond")
        return real(self, *args, **kwargs)
    monkeypatch.setattr(LLMProviderAdapter, "feedback", flaky)
    return calls


def speak_to_the_end(client, headers):
    sid = client.post("/api/speaking/sessions", headers=headers, json={"persona": "boy"}).json()["id"]
    for _ in range(60):
        stage = client.get(f"/api/speaking/sessions/{sid}", headers=headers).json()["ui"]["stage"]
        if stage == "done":
            break
        body = {"event": "ready"} if stage == "p2_prep" else {"text": ANSWER, "seconds": 9}
        assert client.post(f"/api/speaking/sessions/{sid}/turn", headers=headers, json=body).status_code == 200
    return sid


def test_uc4_6a_writing_feedback_retried_once(monkeypatch):
    """One failure is absorbed by the retry: the learner still gets feedback."""
    with TestClient(app) as client:
        headers = learner(client, "uc4.6a.retry@example.com")
        task = client.post("/api/practice/writing", headers=headers).json()
        calls = feedback_fails(monkeypatch, 1)
        submitted = client.post(f"/api/practice/{task['id']}/submit", headers=headers, json={"text": ESSAY})
        assert submitted.status_code == 200, submitted.text
        assert calls["n"] == 2 and submitted.json()["result"] is not None and not submitted.json().get("feedback_unavailable")


def test_uc4_6a_writing_kept_and_feedback_unavailable_then_try_again(monkeypatch):
    with TestClient(app) as client:
        headers = learner(client, "uc4.6a@example.com")
        task = client.post("/api/practice/writing", headers=headers).json()
        calls = feedback_fails(monkeypatch, 4)  # the submission and the first Try again both fail
        submitted = client.post(f"/api/practice/{task['id']}/submit", headers=headers, json={"text": ESSAY})
        assert submitted.status_code == 200, submitted.text
        body = submitted.json()
        assert calls["n"] == 2  # first try plus exactly one retry
        assert body["feedback_unavailable"] is True and body["result"] is None and "temporarily unavailable" in body["message"]
        with SessionLocal() as db:
            sub = db.get(Submission, body["submission_id"])
            assert sub.text == ESSAY and sub.package_id is None  # the essay is kept
            practice = db.get(Practice, task["id"])
            assert db.scalar(select(ResultPackage.id).where(ResultPackage.user_id == practice.user_id)) is None  # nothing was sent to scoring or the quality gate
        attempts = client.get(f"/api/practice/{task['id']}/attempts", headers=headers).json()
        assert attempts[-1]["result"] is None and attempts[-1]["text"] == ESSAY
        # Still failing: the learner is told again and the essay stays kept.
        still = client.post(f"/api/submissions/{body['submission_id']}/feedback", headers=headers)
        assert still.status_code == 503 and "temporarily unavailable" in still.json()["detail"]
        monkeypatch.undo()
        # The model is back: Try again gives feedback for the same essay, without a new attempt.
        again = client.post(f"/api/submissions/{body['submission_id']}/feedback", headers=headers)
        assert again.status_code == 200, again.text
        assert again.json()["result"]["state"] in ("RELEASED", "HELD") and again.json()["attempt"] == body["attempt"]
        assert client.post(f"/api/submissions/{body['submission_id']}/feedback", headers=headers).status_code == 409
        assert len(client.get(f"/api/practice/{task['id']}/attempts", headers=headers).json()) == 1


def test_uc3_6a_speaking_kept_and_feedback_unavailable_then_try_again(monkeypatch):
    with TestClient(app) as client:
        headers = learner(client, "uc3.6a@example.com")
        sid = speak_to_the_end(client, headers)
        feedback_fails(monkeypatch, 2)
        finished = client.post(f"/api/speaking/sessions/{sid}/finish", headers=headers)
        assert finished.status_code == 200, finished.text
        body = finished.json()
        assert body["feedback_unavailable"] is True and body["result"] is None and body["status"] == "COMPLETED"
        with SessionLocal() as db:
            assert ANSWER in db.get(Submission, body["submission_id"]).text  # the transcript is kept
        monkeypatch.undo()
        again = client.post(f"/api/submissions/{body['submission_id']}/feedback", headers=headers)
        assert again.status_code == 200, again.text
        assert set(again.json()["result"]["payload"]["criteria"]) == {"fluency", "lexical_resource", "grammar"}


def test_uc3_5a_leaving_a_speaking_test_records_it_as_incomplete():
    with TestClient(app) as client:
        headers = learner(client, "uc3.5a@example.com")
        session = client.post("/api/speaking/sessions", headers=headers, json={"persona": "boy"}).json()
        assert client.post(f"/api/speaking/sessions/{session['id']}/turn", headers=headers, json={"text": ANSWER, "seconds": 9}).status_code == 200
        left = client.post(f"/api/speaking/sessions/{session['id']}/leave", headers=headers)
        assert left.status_code == 200 and left.json()["status"] == "INCOMPLETE"
        assert any(item["role"] == "learner" and item["text"] == ANSWER for item in left.json()["log"])  # progress is kept
        assert client.post(f"/api/speaking/sessions/{session['id']}/turn", headers=headers, json={"text": ANSWER}).status_code == 409
        assert client.post(f"/api/speaking/sessions/{session['id']}/leave", headers=headers).json()["status"] == "INCOMPLETE"  # leaving twice is harmless
        with SessionLocal() as db:
            assert db.get(Practice, session["practice_id"]).status == "INCOMPLETE"
            assert db.scalar(select(AgentEvent.id).where(AgentEvent.workflow == "speaking", AgentEvent.detail["session_id"].as_integer() == session["id"]))


def test_uc3_5a_a_test_left_without_leaving_is_recorded_when_the_next_one_starts():
    """The tab was closed or the connection lost, so no leave request arrived."""
    with TestClient(app) as client:
        headers = learner(client, "uc3.5a.closed@example.com")
        first = client.post("/api/speaking/sessions", headers=headers, json={"persona": "boy"}).json()
        second = client.post("/api/speaking/sessions", headers=headers, json={"persona": "boy"}).json()
        with SessionLocal() as db:
            assert db.get(SpeakingSession, first["id"]).status == "INCOMPLETE"
            assert db.get(Practice, first["practice_id"]).status == "INCOMPLETE"
            assert db.get(SpeakingSession, second["id"]).status == "ACTIVE"
