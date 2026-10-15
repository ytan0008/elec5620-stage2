from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db import get_db
from backend.auth import current_user, learner, instructor, hasher, hash_password, token_for
from backend.models import User, Profile, Plan, StudyTask, Practice, Submission, MockExam, ExamResponse, ResultPackage, Escalation, InstructorDecision, Material, MaterialInteraction, PerformanceReport, AgentEvent, AuditLog, QualityCheck, SystemSetting
from backend.schemas import RegisterInput, LoginInput, ProfileInput, SubmitInput, ExamAnswerInput, ReviewInput, ThresholdInput, ChangeRequestInput
from backend.agents import AgentRuntime
from backend.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed()
    yield


app = FastAPI(title="ELEC5620 CertifyAI", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    if "REAL AI MODE requires OPENAI_API_KEY" in str(exc):
        return JSONResponse(status_code=503, content={"detail": "AI provider is not configured; set credentials or use DEMO MODE"})
    return JSONResponse(status_code=500, content={"detail": "Workflow execution failed"})


def dto(obj, *fields):
    return {field: getattr(obj, field) for field in fields}


def profile_for(db: Session, user: User) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if not profile:
        raise HTTPException(409, "Complete learner profile first")
    return profile


def profile_data(profile: Profile) -> dict:
    return dto(profile, "exam", "proficiency", "target_score", "exam_date", "weekly_hours", "priority_skills")


def owned(db: Session, model, object_id: int, user: User):
    obj = db.get(model, object_id)
    if not obj or obj.user_id != user.id:
        raise HTTPException(404, "Record not found")
    return obj


def package_view(package: ResultPackage | None, include_held: bool = False):
    if not package:
        return None
    result = dto(package, "id", "kind", "state", "source_mode", "issues", "created_at")
    if package.state == "RELEASED" or include_held:
        result["payload"] = package.payload
        result["confidence"] = package.confidence
    else:
        result["message"] = "Your result is being double-checked" if package.state == "HELD" else "Verification pending"
    return result


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
    weaknesses = [skill for skill, _ in sorted(averages.items(), key=lambda item: item[1])[:2]]
    return {"skill_scores": averages, "history": history, "weaknesses": weaknesses, "strengths": [skill for skill, _ in sorted(averages.items(), key=lambda item: -item[1])[:2]], "repeated_errors": [{"issue": issue, "count": count} for issue,count in error_counts.items() if count >= 2], "sample_count": len(packages), "readiness": "Insufficient data" if len(packages) < 2 else "Developing"}


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "DEMO" if settings().demo_mode else "REAL"}


@app.post("/api/auth/register")
def register(data: RegisterInput, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == data.email.lower())):
        raise HTTPException(409, "Email already registered")
    user = User(email=data.email.lower(), name=data.name, password_hash=hash_password(data.password), role="learner")
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, **data.model_dump(exclude={"email", "name", "password"}, mode="json")))
    db.add(AuditLog(user_id=user.id, action="registered", detail={"exam": data.exam}))
    db.commit()
    return {"token": token_for(user), "user": dto(user, "id", "email", "name", "role")}


@app.post("/api/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not hasher.verify(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"token": token_for(user), "user": dto(user, "id", "email", "name", "role")}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return dto(user, "id", "email", "name", "role")


@app.get("/api/profile")
def get_profile(user: User = Depends(learner), db: Session = Depends(get_db)):
    return profile_data(profile_for(db, user))


@app.put("/api/profile")
def update_profile(data: ProfileInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    for key, value in data.model_dump(mode="json").items():
        setattr(profile, key, value)
    profile.confirmed = True
    db.add(AuditLog(user_id=user.id, action="profile_updated", detail={"exam": data.exam}))
    db.commit()
    return profile_data(profile)


@app.get("/api/plans")
def plans(user: User = Depends(learner), db: Session = Depends(get_db)):
    items = db.scalars(select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc())).all()
    return [{**dto(item, "id", "version", "kind", "status", "created_at"), "content": item.content if item.status in ("PROPOSED", "ACTIVE", "REJECTED") else None} for item in items]


@app.post("/api/plans/generate")
def generate_plan(adapt: bool = False, user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    if adapt and not db.scalar(select(Plan.id).where(Plan.user_id == user.id, Plan.status == "ACTIVE")):
        raise HTTPException(409, "Accept an initial plan first")
    runtime = AgentRuntime(db)
    state = runtime.plan_graph().invoke({"user_id": user.id, "workflow": "adaptation" if adapt else "plan", "profile": profile_data(profile), "progress": latest_progress(db, user.id)})
    package = db.get(ResultPackage, state["package_id"])
    version = (db.scalar(select(func.max(Plan.version)).where(Plan.user_id == user.id)) or 0) + 1
    plan = Plan(user_id=user.id, version=version, kind="adaptation" if adapt else "initial", status="PROPOSED" if package.state == "RELEASED" else "HELD", content=package.payload, package_id=package.id)
    db.add(plan)
    db.commit()
    return {"id": plan.id, "status": plan.status, "package": package_view(package)}


@app.post("/api/plans/{plan_id}/decision")
def plan_decision(plan_id: int, accept: bool, user: User = Depends(learner), db: Session = Depends(get_db)):
    plan = owned(db, Plan, plan_id, user)
    if plan.status != "PROPOSED" or db.get(ResultPackage, plan.package_id).state != "RELEASED":
        raise HTTPException(409, "Only verified proposed plans can be decided")
    if accept:
        for old in db.scalars(select(Plan).where(Plan.user_id == user.id, Plan.status == "ACTIVE")):
            old.status = "SUPERSEDED"
        plan.status = "ACTIVE"
        for item in plan.content["activities"]:
            db.add(StudyTask(user_id=user.id, plan_id=plan.id, skill=item["skill"], title=item["title"]))
        db.add(AgentEvent(user_id=user.id, workflow="adaptation" if plan.kind == "adaptation" else "plan", agent="Learning Coordinator", phase="handoff", detail={"decision": "activated", "next_agent": "AI Tutor + Assessment & Analytics", "plan_id": plan.id}, mode="DEMO" if settings().demo_mode else "REAL"))
    else:
        plan.status = "REJECTED"
    db.add(AuditLog(user_id=user.id, action="plan_accepted" if accept else "plan_rejected", detail={"plan_id": plan.id}))
    db.commit()
    return {"id": plan.id, "status": plan.status}


@app.post("/api/plans/{plan_id}/request-changes")
def request_plan_changes(plan_id: int, data: ChangeRequestInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    previous = owned(db, Plan, plan_id, user)
    if previous.status != "PROPOSED":
        raise HTTPException(409, "Only a proposed plan can be revised")
    profile = profile_for(db, user)
    progress = latest_progress(db, user.id)
    progress["change_request"] = data.note
    runtime = AgentRuntime(db)
    state = runtime.plan_graph().invoke({"user_id": user.id, "workflow": "plan", "profile": profile_data(profile), "progress": progress})
    package = db.get(ResultPackage, state["package_id"])
    version = (db.scalar(select(func.max(Plan.version)).where(Plan.user_id == user.id)) or 0) + 1
    revised = Plan(user_id=user.id, version=version, kind="revision", status="PROPOSED" if package.state == "RELEASED" else "HELD", content=package.payload, package_id=package.id)
    previous.status = "REJECTED"
    db.add(revised)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="plan_changes_requested", detail={"previous_plan_id": plan_id, "new_plan_id": revised.id, "request": data.note}))
    db.commit()
    return {"id": revised.id, "status": revised.status, "package": package_view(package)}


@app.get("/api/tasks")
def tasks(user: User = Depends(learner), db: Session = Depends(get_db)):
    return [dto(item, "id", "skill", "title", "complete") for item in db.scalars(select(StudyTask).where(StudyTask.user_id == user.id).order_by(StudyTask.id.desc()))]


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    task = owned(db, StudyTask, task_id, user)
    task.complete = True
    db.commit()
    return {"complete": True}


@app.post("/api/practice/{skill}")
def start_practice(skill: str, user: User = Depends(learner), db: Session = Depends(get_db)):
    if skill not in ("speaking", "writing", "reading", "listening"):
        raise HTTPException(404, "Unknown skill")
    profile = profile_for(db, user)
    runtime = AgentRuntime(db)
    prompt = runtime.provider.prompt(profile.exam, skill, profile.proficiency)
    practice = Practice(user_id=user.id, exam=profile.exam, skill=skill, prompt=prompt)
    db.add(practice)
    db.flush()
    db.add(AgentEvent(user_id=user.id, workflow=skill, agent="AI Tutor", phase="action", detail={"decision": "generated practice task", "tool": "LLM adapter", "practice_id": practice.id}, mode=runtime.provider.mode))
    db.commit()
    return {"id": practice.id, "prompt": prompt, "skill": skill}


@app.get("/api/practice/{practice_id}/attempts")
def attempts(practice_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    practice = owned(db, Practice, practice_id, user)
    submissions = db.scalars(select(Submission).where(Submission.practice_id == practice.id).order_by(Submission.attempt)).all()
    return [{"id": sub.id, "text": sub.text, "attempt": sub.attempt, "audio_available": bool(sub.audio_path), "result": package_view(db.get(ResultPackage, sub.package_id))} for sub in submissions]


@app.get("/api/practice/submissions/{submission_id}/audio")
def get_submission_audio(submission_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    sub = owned(db, Submission, submission_id, user)
    if not sub.audio_path or not Path(sub.audio_path).is_file():
        raise HTTPException(404, "Audio not found")
    return FileResponse(sub.audio_path, media_type="audio/webm")


@app.post("/api/practice/{practice_id}/audio")
async def upload_audio(practice_id: int, file: UploadFile = File(...), user: User = Depends(learner), db: Session = Depends(get_db)):
    practice = owned(db, Practice, practice_id, user)
    if practice.skill != "speaking":
        raise HTTPException(400, "Audio is only for speaking practice")
    if file.content_type not in ("audio/webm", "audio/ogg", "audio/mp4", "audio/wav"):
        raise HTTPException(415, "Unsupported audio type")
    data = await file.read(5_000_001)
    if len(data) > 5_000_000:
        raise HTTPException(413, "Audio exceeds 5 MB")
    folder = Path("uploads") / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"practice-{practice.id}-{uuid4().hex}.webm"
    path.write_bytes(data)
    db.add(AuditLog(user_id=user.id, action="audio_uploaded", detail={"practice_id": practice.id, "bytes": len(data)}))
    db.commit()
    if not settings().demo_mode and settings().transcription_model and settings().openai_api_key:
        try:
            from openai import OpenAI
            with path.open("rb") as stream:
                transcript = OpenAI(api_key=settings().openai_api_key, timeout=30).audio.transcriptions.create(model=settings().transcription_model, file=stream)
            return {"stored": True, "transcription_available": True, "transcript": transcript.text, "message": "Audio transcribed. Review the transcript before submitting."}
        except Exception as exc:
            db.add(AuditLog(user_id=user.id, action="transcription_failed", detail={"practice_id": practice.id, "error_type": type(exc).__name__}))
            db.commit()
            return {"stored": True, "transcription_available": False, "message": "Transcription failed; enter a transcript manually. Audio pronunciation assessment is unavailable."}
    return {"stored": True, "transcription_available": False, "message": "Audio saved. Configure a transcription service for real transcription; enter a transcript manually for text-based demo feedback."}


@app.post("/api/practice/{practice_id}/submit")
def submit_practice(practice_id: int, data: SubmitInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    practice = owned(db, Practice, practice_id, user)
    profile = profile_for(db, user)
    runtime = AgentRuntime(db)
    if practice.skill in ("writing", "speaking"):
        if data.scenario == "invalid" and settings().demo_mode:
            package = runtime.verify_output(user.id, practice.skill, {"summary": "Malformed demo output", "criteria": {}, "confidence": {}})
        else:
            state = runtime.practice_graph().invoke({"user_id": user.id, "workflow": practice.skill, "profile": profile_data(profile), "skill": practice.skill, "text": data.text, "scenario": data.scenario})
            package = db.get(ResultPackage, state["package_id"])
    else:
        key = practice.prompt["answer_key"]
        correct = key in data.text.lower()
        score = 6.5 if profile.exam == "IELTS" else 4.5
        if not correct:
            score = 4.5 if profile.exam == "IELTS" else 3.0
        package = runtime.verify_output(user.id, practice.skill, {"summary": "Correct answer supported by passage" if correct else f"Review the evidence and try identifying: {key}", "criteria": {practice.skill: score}, "estimated_overall": score, "official": False, "confidence": {practice.skill: .90}, "comments": [{"issue": "Check source evidence", "suggestion": key}]})
    attempt = (db.scalar(select(func.max(Submission.attempt)).where(Submission.practice_id == practice.id)) or 0) + 1
    audio_path = None
    if practice.skill == "speaking":
        used = {item for item in db.scalars(select(Submission.audio_path).where(Submission.practice_id == practice.id)) if item}
        files = sorted((Path("uploads") / str(user.id)).glob(f"practice-{practice.id}-*.webm"), key=lambda item: item.stat().st_mtime, reverse=True) if (Path("uploads") / str(user.id)).exists() else []
        audio_path = next((str(item) for item in files if str(item) not in used), None)
    sub = Submission(practice_id=practice.id, user_id=user.id, text=data.text, audio_path=audio_path, attempt=attempt, package_id=package.id)
    db.add(sub)
    practice.status = "SUBMITTED"
    db.commit()
    return {"submission_id": sub.id, "attempt": attempt, "result": package_view(package)}


@app.get("/api/results/{package_id}")
def result(package_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    return package_view(owned(db, ResultPackage, package_id, user))


@app.post("/api/mock-exams")
def create_mock(user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    if not db.scalar(select(Plan.id).where(Plan.user_id == user.id, Plan.status == "ACTIVE")):
        raise HTTPException(409, "Accept a learning plan before the mock exam")
    runtime = AgentRuntime(db)
    sections = {skill: runtime.provider.prompt(profile.exam, skill) for skill in ("listening", "reading", "writing", "speaking")}
    exam = MockExam(user_id=user.id, exam=profile.exam, sections=sections)
    db.add(exam)
    db.commit()
    return mock_view(exam, db)


def mock_view(exam: MockExam, db: Session):
    answers = {answer.skill: answer.answer for answer in db.scalars(select(ExamResponse).where(ExamResponse.exam_id == exam.id))}
    return {"id": exam.id, "exam": exam.exam, "status": exam.status, "reduced_length": True, "sections": exam.sections, "answers": answers, "result": package_view(db.get(ResultPackage, exam.package_id)) if exam.package_id else None}


@app.get("/api/mock-exams")
def list_mocks(user: User = Depends(learner), db: Session = Depends(get_db)):
    return [mock_view(exam, db) for exam in db.scalars(select(MockExam).where(MockExam.user_id == user.id).order_by(MockExam.id.desc()))]


@app.get("/api/mock-exams/{exam_id}")
def get_mock(exam_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    return mock_view(owned(db, MockExam, exam_id, user), db)


@app.put("/api/mock-exams/{exam_id}/{skill}")
def save_exam_answer(exam_id: int, skill: str, data: ExamAnswerInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    exam = owned(db, MockExam, exam_id, user)
    if exam.status != "IN_PROGRESS" or skill not in exam.sections:
        raise HTTPException(409, "Section cannot be edited")
    response = db.scalar(select(ExamResponse).where(ExamResponse.exam_id == exam.id, ExamResponse.skill == skill))
    if response:
        response.answer = data.answer
    else:
        db.add(ExamResponse(exam_id=exam.id, skill=skill, answer=data.answer))
    db.commit()
    return {"saved": True}


@app.post("/api/mock-exams/{exam_id}/submit")
def submit_mock(exam_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    exam = owned(db, MockExam, exam_id, user)
    if exam.status != "IN_PROGRESS":
        raise HTTPException(409, "Exam already submitted")
    answers = {item.skill: item.answer for item in db.scalars(select(ExamResponse).where(ExamResponse.exam_id == exam.id))}
    if set(answers) != set(exam.sections) or any(not answer.strip() for answer in answers.values()):
        raise HTTPException(409, "Complete all four sections")
    runtime = AgentRuntime(db)
    scores = {}
    for skill in ("listening", "reading"):
        correct = exam.sections[skill]["answer_key"] in answers[skill].lower()
        scores[skill] = (6.5 if correct else 4.5) if exam.exam == "IELTS" else (4.5 if correct else 3.0)
    for skill in ("writing", "speaking"):
        feedback = runtime.provider.feedback(exam.exam, skill, answers[skill], "normal")
        scores[skill] = round(sum(feedback.criteria.values()) / len(feedback.criteria) * 2) / 2
    overall = round(sum(scores.values()) / 4 * 2) / 2
    output = {"summary": "Reduced-length prototype exam estimate; not an official score or full-length exam. Speaking audio delivery/pronunciation was not assessed from text.", "section_scores": scores, "estimated_overall": overall, "readiness": "On track" if overall >= (6.5 if exam.exam == "IELTS" else 4.5) else "Needs further practice", "score_scale": "IELTS 0-9 bands" if exam.exam == "IELTS" else "TOEFL 2026 1-6 sections", "official": False, "confidence": {skill: .82 for skill in scores}}
    package = runtime.verify_output(user.id, "mock_exam", output)
    exam.package_id = package.id
    exam.status = "SUBMITTED"
    db.commit()
    return mock_view(exam, db)


@app.get("/api/analytics")
def analytics(user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    progress = latest_progress(db, user.id)
    progress["target_score"] = profile.target_score
    progress["exam"] = profile.exam
    if progress["sample_count"] >= 2 and progress["skill_scores"]:
        mean = sum(progress["skill_scores"].values()) / len(progress["skill_scores"])
        progress["readiness"] = "Estimated on track" if mean >= profile.target_score else "Estimated needs practice"
    progress["recommendations"] = [f"Practise {skill} twice this week" for skill in progress["weaknesses"]] if progress["sample_count"] else ["Complete a practice session to unlock personalised insights"]
    return progress


@app.post("/api/reports")
def create_report(user: User = Depends(learner), db: Session = Depends(get_db)):
    data = latest_progress(db, user.id)
    if data["sample_count"] == 0:
        raise HTTPException(409, "Complete practice before generating a report")
    runtime = AgentRuntime(db)
    try:
        narrative = runtime.provider.report(data).model_dump()
        data.update(narrative)
    except Exception as exc:
        data.update({"summary": "Report generation failed", "confidence": {}, "error_type": type(exc).__name__})
    package = runtime.verify_output(user.id, "report", data)
    report = PerformanceReport(user_id=user.id, package_id=package.id)
    db.add(report)
    db.commit()
    return {"id": report.id, "result": package_view(package)}


@app.get("/api/reports")
def reports(user: User = Depends(learner), db: Session = Depends(get_db)):
    return [{"id": report.id, "result": package_view(db.get(ResultPackage, report.package_id))} for report in db.scalars(select(PerformanceReport).where(PerformanceReport.user_id == user.id).order_by(PerformanceReport.id.desc()))]


@app.get("/api/materials")
def materials(exam: str | None = None, skill: str | None = None, level: str | None = None, user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    query = select(Material).where(Material.exam == (exam or profile.exam))
    if skill:
        query = query.where(Material.skill == skill)
    if level:
        query = query.where(Material.level == level)
    return [dto(item, "id", "title", "exam", "skill", "level", "description", "content") for item in db.scalars(query)]


@app.post("/api/materials/recommend")
def recommend_materials(user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    progress = latest_progress(db, user.id)
    priorities = progress["weaknesses"] or profile.priority_skills
    catalog = db.scalars(select(Material).where(Material.exam == profile.exam)).all()
    runtime = AgentRuntime(db)
    try:
        output = runtime.provider.recommendations([dto(item, "id", "title", "skill", "level", "description") for item in catalog], priorities).model_dump()
        valid_ids = {item.id for item in catalog}
        if any(item.get("id") not in valid_ids for item in output["items"]):
            output["confidence"] = {}
            output["error_type"] = "Unknown catalog ID"
    except Exception as exc:
        output = {"items": [], "summary": "Recommendation generation failed", "confidence": {}, "error_type": type(exc).__name__}
    package = runtime.verify_output(user.id, "recommendations", output)
    db.commit()
    return package_view(package)


@app.post("/api/materials/{material_id}/interaction")
def material_interaction(material_id: int, relevant: bool | None = None, user: User = Depends(learner), db: Session = Depends(get_db)):
    if not db.get(Material, material_id):
        raise HTTPException(404, "Material not found")
    item = db.scalar(select(MaterialInteraction).where(MaterialInteraction.user_id == user.id, MaterialInteraction.material_id == material_id))
    if not item:
        item = MaterialInteraction(user_id=user.id, material_id=material_id)
        db.add(item)
    item.viewed = True
    if relevant is not None:
        item.relevant = relevant
    db.commit()
    return {"viewed": item.viewed, "relevant": item.relevant}


@app.get("/api/events")
def events(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(AgentEvent).order_by(AgentEvent.id.desc()).limit(100)
    if user.role == "learner":
        query = query.where(AgentEvent.user_id == user.id)
    return [dto(event, "id", "workflow", "agent", "phase", "detail", "mode", "duration_ms", "created_at") for event in db.scalars(query)]


@app.get("/api/instructor/cases")
def cases(user: User = Depends(instructor), db: Session = Depends(get_db)):
    rows = db.scalars(select(Escalation).order_by(Escalation.id.desc())).all()
    return [{**dto(case, "id", "status", "reason", "created_at"), "package": package_view(db.get(ResultPackage, case.package_id), True), "decisions": [dto(dec, "decision", "note", "correction", "created_at") for dec in db.scalars(select(InstructorDecision).where(InstructorDecision.case_id == case.id))]} for case in rows]


@app.post("/api/instructor/cases/{case_id}/decision")
def decide_case(case_id: int, data: ReviewInput, user: User = Depends(instructor), db: Session = Depends(get_db)):
    case = db.get(Escalation, case_id)
    if not case or case.status not in ("PENDING", "MORE_INFO"):
        raise HTTPException(409, "Case is not pending")
    package = db.get(ResultPackage, case.package_id)
    if data.decision == "correct" and not data.correction:
        raise HTTPException(422, "Correction payload is required")
    corrected = {**package.payload, **data.correction} if data.decision == "correct" else package.payload
    if data.decision in ("approve", "correct"):
        if not corrected.get("confidence"):
            raise HTTPException(422, "Release requires confidence evidence")
        if any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in corrected["confidence"].values()):
            raise HTTPException(422, "Confidence values must be within 0 and 1")
        if package.kind in ("writing", "speaking"):
            if not corrected.get("summary") or not corrected.get("criteria") or not corrected.get("comments") or set(corrected["criteria"]) != set(corrected["confidence"]):
                raise HTTPException(422, "Feedback is incomplete; supply a complete correction")
            learner_profile = db.scalar(select(Profile).where(Profile.user_id == package.user_id))
            maximum = 9 if learner_profile and learner_profile.exam == "IELTS" else 6
            if any(not isinstance(v, (int, float)) or not 0 <= v <= maximum for v in corrected["criteria"].values()):
                raise HTTPException(422, "Corrected scores are outside the exam scale")
            if package.kind == "speaking" and (corrected.get("pronunciation_available") is not False or not corrected.get("pronunciation_note")):
                raise HTTPException(422, "Speaking correction must disclose unavailable audio assessment")
        if package.kind in ("plan", "adaptation") and (not corrected.get("activities") or not corrected.get("priorities")):
            raise HTTPException(422, "Plan is incomplete; supply a complete correction")
        if package.kind == "recommendations" and not corrected.get("items"):
            raise HTTPException(422, "Recommendations are incomplete")
        if data.decision == "correct":
            package.payload = corrected
            package.confidence = corrected["confidence"]
    db.add(InstructorDecision(case_id=case.id, instructor_id=user.id, decision=data.decision, note=data.note, correction=data.correction))
    db.add(AuditLog(user_id=user.id, action="instructor_decision", detail={"case_id": case.id, "decision": data.decision}))
    db.add(AgentEvent(user_id=package.user_id, workflow=package.kind, agent="Human Instructor", phase="decision", detail={"decision": data.decision, "package_id": package.id, "next_agent": "Quality Manager"}, mode=package.source_mode))
    if data.decision == "request_information":
        case.status = "MORE_INFO"
        package.state = "HUMAN_REVIEW"
        db.add(AgentEvent(user_id=package.user_id, workflow=package.kind, agent="Quality Manager", phase="state", detail={"package_id": package.id, "state": "HUMAN_REVIEW"}, mode=package.source_mode))
    else:
        package.state = "APPROVED" if data.decision == "approve" else "CORRECTED"
        db.add(AgentEvent(user_id=package.user_id, workflow=package.kind, agent="Quality Manager", phase="state", detail={"package_id": package.id, "state": package.state}, mode=package.source_mode))
        db.add(QualityCheck(package_id=package.id, verdict="HUMAN_APPROVED", issues=[], threshold=AgentRuntime(db).threshold(), method="HUMAN"))
        AgentRuntime(db).release_after_human(package)
        case.status = "RESOLVED"
        for plan in db.scalars(select(Plan).where(Plan.package_id == package.id)):
            plan.content = package.payload
            plan.status = "PROPOSED"
    db.commit()
    return {"status": case.status, "package": package_view(package, True)}


@app.get("/api/instructor/quality")
def quality_dashboard(user: User = Depends(instructor), db: Session = Depends(get_db)):
    checks = db.scalars(select(QualityCheck).order_by(QualityCheck.id.desc()).limit(100)).all()
    return {"threshold": AgentRuntime(db).threshold(), "checks": [dto(check, "id", "package_id", "verdict", "issues", "method", "created_at") for check in checks], "pending": db.scalar(select(func.count()).select_from(Escalation).where(Escalation.status != "RESOLVED"))}


@app.put("/api/instructor/quality/threshold")
def update_threshold(data: ThresholdInput, user: User = Depends(instructor), db: Session = Depends(get_db)):
    row = db.get(SystemSetting, "quality_threshold")
    if not row:
        row = SystemSetting(key="quality_threshold", value=str(data.value))
        db.add(row)
    else:
        row.value = str(data.value)
    db.add(AuditLog(user_id=user.id, action="quality_threshold_updated", detail={"value": data.value}))
    db.commit()
    return {"threshold": data.value}


@app.get("/api/instructor/audit")
def audit(user: User = Depends(instructor), db: Session = Depends(get_db)):
    return [dto(row, "id", "user_id", "action", "detail", "created_at") for row in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100))]
