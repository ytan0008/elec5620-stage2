"""Reproducible demo: an active plan, a released result and a pending escalation."""
from fastapi.testclient import TestClient
from backend.main import app


def run():
    with TestClient(app) as client:
        email = "demo.learner@example.com"
        password = "DemoLearner123!"
        login = client.post("/api/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            login = client.post("/api/auth/register", json={"email": email, "password": password, "name": "Mai Chen", "exam": "IELTS", "proficiency": "intermediate", "target_score": 7, "exam_date": "2026-12-15", "weekly_hours": 8, "priority_skills": ["writing", "speaking"]})
            login.raise_for_status()
        headers = {"Authorization": "Bearer " + login.json()["token"]}
        plans = client.get("/api/plans", headers=headers).json()
        if not any(plan["status"] == "ACTIVE" for plan in plans):
            proposal = client.post("/api/plans/generate", headers=headers)
            proposal.raise_for_status()
            client.post(f"/api/plans/{proposal.json()['id']}/decision?accept=true", headers=headers).raise_for_status()
        sessions = client.post("/api/practice/writing", headers=headers)
        sessions.raise_for_status()
        practice_id = sessions.json()["id"]
        essay = "Remote work can improve professional productivity because employees save commuting time. For example, a consultant can use an extra hour to prepare thoughtful client advice. However, employers should set clear communication routines so that teams remain coordinated."
        client.post(f"/api/practice/{practice_id}/submit", headers=headers, json={"text": essay}).raise_for_status()
        client.post(f"/api/practice/{practice_id}/submit", headers=headers, json={"text": essay, "scenario": "contradiction"}).raise_for_status()
        print("Demo learner: demo.learner@example.com / DemoLearner123!")
        print("Instructor credentials: see INSTRUCTOR_EMAIL and INSTRUCTOR_PASSWORD in .env")
        print("Seeded one released writing result and one pending contradiction case.")


if __name__ == "__main__":
    run()
