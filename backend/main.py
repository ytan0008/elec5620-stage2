from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import json
import smtplib
import re
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db import get_db
from backend.auth import current_user, learner, instructor, hasher, hash_password, token_for
from backend.models import User, PasswordReset, Profile, OnboardingSession, AgentConversation, LearnerPortrait, QuestionItem, Plan, StudyTask, Practice, Submission, MockExam, ExamResponse, ResultPackage, Escalation, InstructorDecision, Material, MaterialInteraction, PerformanceReport, AgentEvent, AuditLog, QualityCheck, SystemSetting
from backend.schemas import RegisterInput, LoginInput, PasswordResetRequest, PasswordResetConfirm, ProfileInput, SubmitInput, ExamAnswerInput, ReviewInput, ThresholdInput, ChangeRequestInput, OnboardingTurn, QuestionGenerationInput, AgentChatTurn
from backend.recovery import mail_ready, new_reset_token, reset_path, send_reset_email, token_digest
from backend.onboarding import FIELDS, QUESTIONS as ONBOARDING_QUESTIONS, clean_extraction, next_field
from backend.knowledge import build_graph
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
    profile_input = data.model_dump(exclude={"email", "name", "password"}, exclude_none=True, mode="json")
    if profile_input:
        db.add(Profile(user_id=user.id, **profile_input))
    db.add(AuditLog(user_id=user.id, action="registered", detail={"profile_complete": bool(profile_input)}))
    db.commit()
    return {"token": token_for(user), "user": {**dto(user, "id", "email", "name", "role"), "profile_complete": bool(profile_input)}}


@app.post("/api/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not hasher.verify(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    complete = user.role == "instructor" or bool(db.scalar(select(Profile.id).where(Profile.user_id == user.id)))
    return {"token": token_for(user), "user": {**dto(user, "id", "email", "name", "role"), "profile_complete": complete}}


@app.post("/api/auth/password-reset/request")
def request_password_reset(data: PasswordResetRequest, db: Session = Depends(get_db)):
    config = settings()
    if not config.demo_mode and not mail_ready():
        raise HTTPException(503, "Password recovery email is not configured")
    response = {"message": "If this email has an account, a reset link has been issued."}
    token = new_reset_token()
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user:
        now = datetime.now(timezone.utc)
        for previous in db.scalars(select(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))):
            previous.used_at = now
        db.add(PasswordReset(user_id=user.id, token_hash=token_digest(token), expires_at=now + timedelta(minutes=30)))
        db.add(AuditLog(user_id=user.id, action="password_reset_requested", detail={"delivery": "demo" if config.demo_mode else "email"}))
        if not config.demo_mode:
            try:
                send_reset_email(user.email, token)
            except (OSError, smtplib.SMTPException):
                db.rollback()
                raise HTTPException(503, "Recovery email could not be sent; please try again later")
        db.commit()
    if config.demo_mode:
        response["demo_reset_path"] = reset_path(token)
        response["demo_notice"] = "DEMO ONLY: this link is shown on screen because email delivery is not configured."
    return response


@app.post("/api/auth/password-reset/confirm")
def confirm_password_reset(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    record = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_digest(data.token)))
    now = datetime.now(timezone.utc)
    if not record or record.used_at is not None or record.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(400, "Reset link is invalid or expired")
    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(400, "Reset link is invalid or expired")
    user.password_hash = hash_password(data.password)
    user.token_version += 1
    for pending in db.scalars(select(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))):
        pending.used_at = now
    db.add(AuditLog(user_id=user.id, action="password_reset_completed", detail={"revoked_sessions": True}))
    db.commit()
    return {"message": "Password changed. Sign in with your new password."}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return dto(user, "id", "email", "name", "role")


@app.get("/api/onboarding")
def onboarding_state(user: User = Depends(learner), db: Session = Depends(get_db)):
    session = db.scalar(select(OnboardingSession).where(OnboardingSession.user_id == user.id))
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    draft = profile_data(profile) if profile else (session.draft if session else {})
    missing = next_field(draft)
    return {"draft": draft, "messages": session.messages if session else [], "ready": missing is None, "completed": bool(profile), "next_field": missing, "assistant_message": ONBOARDING_QUESTIONS[missing] if missing else "Your profile is ready. Review it and confirm to create your learning portrait.", "mode": "DEMO" if settings().demo_mode else "REAL"}


@app.post("/api/onboarding/message")
def onboarding_message(data: OnboardingTurn, user: User = Depends(learner), db: Session = Depends(get_db)):
    if db.scalar(select(Profile.id).where(Profile.user_id == user.id)):
        raise HTTPException(409, "Profile already exists; edit it from My profile")
    session = db.scalar(select(OnboardingSession).where(OnboardingSession.user_id == user.id))
    if not session:
        session = OnboardingSession(user_id=user.id, messages=[], draft={})
        db.add(session)
        db.flush()
    runtime = AgentRuntime(db)
    extracted = runtime.provider.extract_onboarding(data.message, session.draft).model_dump(exclude_none=True)
    draft, errors = clean_extraction(extracted, session.draft)
    missing = next_field(draft)
    if missing is None:
        try:
            ProfileInput.model_validate(draft)
        except Exception:
            draft.pop("target_score", None)
            missing = "target_score"
            errors.append("Target score does not match the selected exam")
    reply = ("I couldn't use that detail: " + "; ".join(errors) + ". " if errors else "") + (ONBOARDING_QUESTIONS[missing] if missing else "I have enough to build your starting profile. Review the details and confirm when ready.")
    session.draft = draft
    session.messages = (session.messages or [])[-48:] + [{"role": "learner", "text": data.message}, {"role": "assistant", "text": reply}]
    db.add(AgentEvent(user_id=user.id, workflow="onboarding", agent="Learning Coordinator", phase="decision", detail={"captured_fields": list(extracted), "next_field": missing, "tool": "shared LLM adapter"}, mode=runtime.provider.mode))
    db.commit()
    return {"draft": draft, "messages": session.messages, "ready": missing is None, "completed": False, "next_field": missing, "assistant_message": reply, "mode": runtime.provider.mode}


CHAT_CONTEXTS = {"profile", "plan", "speaking", "writing", "reading", "listening", "dashboard", "questions", "materials", "analytics", "knowledge", "portrait", "workflow", "settings"}


def chat_record(db: Session, user_id: int, context: str) -> AgentConversation | None:
    if context not in CHAT_CONTEXTS:
        raise HTTPException(404, "Unknown conversation context")
    return db.scalar(select(AgentConversation).where(AgentConversation.user_id == user_id, AgentConversation.context == context))


@app.get("/api/chat/{context}")
def chat_history(context: str, user: User = Depends(learner), db: Session = Depends(get_db)):
    record = chat_record(db, user.id, context)
    return {"context": context, "agent": "AI Tutor" if context in ("speaking", "writing", "reading", "listening") else "Learning Coordinator", "messages": record.messages if record else [], "mode": "DEMO" if settings().demo_mode else "REAL"}


@app.post("/api/chat/{context}")
def chat_turn(context: str, data: AgentChatTurn, user: User = Depends(learner), db: Session = Depends(get_db)):
    record = chat_record(db, user.id, context)
    profile = profile_for(db, user)
    plan = db.scalar(select(Plan).where(Plan.user_id == user.id, Plan.status == "ACTIVE").order_by(Plan.id.desc()))
    runtime = AgentRuntime(db)
    started = datetime.now(timezone.utc)
    try:
        # Remove obvious contact details before any external model call; history is redacted too.
        def safe_text(value: str) -> str:
            value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email redacted]", value)
            return re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "[phone redacted]", value)
        safe_history = [{"role": item.get("role"), "text": safe_text(item.get("text", ""))} for item in (record.messages if record else [])]
        reply = runtime.provider.chat(context, safe_text(data.message), profile_data(profile), plan.content if plan else None, safe_history).reply
    except Exception:
        raise HTTPException(503, "Agent reply unavailable; please try again")
    if not record:
        record = AgentConversation(user_id=user.id, context=context, messages=[])
        db.add(record)
    record.messages = (record.messages or [])[-38:] + [{"role": "learner", "text": data.message}, {"role": "assistant", "text": reply}]
    agent = "AI Tutor" if context in ("speaking", "writing", "reading", "listening") else "Learning Coordinator"
    db.add(AgentEvent(user_id=user.id, workflow="chat", agent=agent, phase="action", detail={"context": context, "decision": "respond to learner", "tool": "shared LLM adapter", "note": "Instructional chat; no verified score or plan released"}, mode=runtime.provider.mode, duration_ms=int((datetime.now(timezone.utc)-started).total_seconds()*1000)))
    db.commit()
    return {"context": context, "agent": agent, "messages": record.messages, "mode": runtime.provider.mode}


@app.post("/api/onboarding/confirm")
def confirm_onboarding(user: User = Depends(learner), db: Session = Depends(get_db)):
    if db.scalar(select(Profile.id).where(Profile.user_id == user.id)):
        raise HTTPException(409, "Profile already exists")
    session = db.scalar(select(OnboardingSession).where(OnboardingSession.user_id == user.id))
    if not session:
        raise HTTPException(409, "Complete the assistant interview first")
    try:
        profile_input = ProfileInput.model_validate(session.draft)
    except Exception:
        raise HTTPException(409, "Profile interview is incomplete or invalid")
    profile = Profile(user_id=user.id, **profile_input.model_dump(mode="json"))
    db.add(profile)
    package = create_portrait(db, user, profile)
    session.completed = True
    db.add(AuditLog(user_id=user.id, action="onboarding_confirmed", detail={"portrait_package_id": package.id}))
    db.commit()
    return {"profile": profile_data(profile), "portrait": package_view(package)}


def create_portrait(db: Session, user: User, profile: Profile) -> ResultPackage:
    runtime = AgentRuntime(db)
    try:
        portrait = runtime.provider.portrait(profile_data(profile)).model_dump()
    except Exception as exc:
        portrait = {"summary": "Portrait generation requires review", "confidence": {}, "error_type": type(exc).__name__}
    package = runtime.verify_output(user.id, "portrait", portrait)
    db.add(LearnerPortrait(user_id=user.id, package_id=package.id, content=portrait))
    db.add(AgentEvent(user_id=user.id, workflow="portrait", agent="Learning Coordinator", phase="handoff", detail={"decision": "submit learner portrait", "next_agent": "Quality Manager", "package_id": package.id}, mode=runtime.provider.mode))
    return package


@app.get("/api/portrait")
def get_portrait(user: User = Depends(learner), db: Session = Depends(get_db)):
    portrait = db.scalar(select(LearnerPortrait).where(LearnerPortrait.user_id == user.id).order_by(LearnerPortrait.id.desc()))
    return package_view(db.get(ResultPackage, portrait.package_id)) if portrait else None


@app.post("/api/portrait/generate")
def generate_portrait(user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    package = create_portrait(db, user, profile)
    db.commit()
    return package_view(package)


@app.get("/api/profile")
def get_profile(user: User = Depends(learner), db: Session = Depends(get_db)):
    return profile_data(profile_for(db, user))


@app.get("/api/knowledge-graph")
def knowledge_graph(user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    counts = {skill: db.scalar(select(func.count()).select_from(Material).where(Material.exam == profile.exam, Material.skill == skill)) for skill in ("listening", "reading", "writing", "speaking")}
    return build_graph(profile_data(profile), latest_progress(db, user.id), counts)


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


def question_view(item: QuestionItem, db: Session) -> dict:
    package = db.get(ResultPackage, item.package_id) if item.package_id else None
    available = not package or package.state == "RELEASED"
    return {"id": item.id, "exam": item.exam, "skill": item.skill, "task_type": item.task_type, "title": item.title,
            "prompt": item.prompt if available else None, "topic": item.topic, "source_kind": item.source_kind,
            "source_url": item.source_url, "available": available, "verification_state": package.state if package else "CURATED"}


@app.get("/api/questions")
def questions(exam: str = "IELTS", skill: str | None = None, user: User = Depends(learner), db: Session = Depends(get_db)):
    if exam != "IELTS":
        raise HTTPException(400, "This catalog currently contains IELTS resources only")
    if skill and skill not in ("writing", "speaking", "reading", "listening"):
        raise HTTPException(400, "Unknown skill")
    query = select(QuestionItem).where(QuestionItem.exam == exam)
    if skill:
        query = query.where(QuestionItem.skill == skill)
    items = db.scalars(query.order_by(QuestionItem.id)).all()
    return [question_view(item, db) for item in items if item.user_id is None or item.user_id == user.id]


@app.post("/api/questions/generate")
def generate_question(data: QuestionGenerationInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    if profile.exam != "IELTS":
        raise HTTPException(409, "IELTS question generation requires an IELTS profile")
    runtime = AgentRuntime(db)
    try:
        output = runtime.provider.generate_question("IELTS", data.skill, data.topic).model_dump()
    except Exception as exc:
        output = {"title": "Question requires review", "confidence": {}, "error_type": type(exc).__name__}
    package = runtime.verify_output(user.id, "question", output)
    item = QuestionItem(user_id=user.id, exam="IELTS", skill=data.skill, task_type=output.get("task_type", "Generated task"), title=output.get("title", "Question under review"), prompt=output.get("prompt"), answer_key=None, topic=data.topic, source_kind="DEMO_GENERATED" if settings().demo_mode else "AI_GENERATED", package_id=package.id)
    db.add(item)
    db.commit()
    return question_view(item, db)


@app.post("/api/practice/{skill}")
def start_practice(skill: str, question_id: int | None = None, user: User = Depends(learner), db: Session = Depends(get_db)):
    if skill not in ("speaking", "writing", "reading", "listening"):
        raise HTTPException(404, "Unknown skill")
    profile = profile_for(db, user)
    runtime = AgentRuntime(db)
    if question_id is not None:
        item = db.get(QuestionItem, question_id)
        if not item or item.exam != profile.exam or item.skill != skill or not item.prompt or item.user_id not in (None, user.id):
            raise HTTPException(404, "Practice question not found")
        if item.package_id and db.get(ResultPackage, item.package_id).state != "RELEASED":
            raise HTTPException(409, "Generated question is awaiting quality review")
        prompt = {"title": item.title, "text": item.prompt, "answer_key": item.answer_key, "mode": item.source_kind,
                  "task_type": item.task_type, "duration_seconds": 120 if skill == "speaking" else 2400 if skill == "writing" else 600}
    else:
        prompt = runtime.provider.prompt(profile.exam, skill, profile.proficiency)
    practice = Practice(user_id=user.id, exam=profile.exam, skill=skill, prompt=prompt)
    db.add(practice)
    db.flush()
    db.add(AgentEvent(user_id=user.id, workflow=skill, agent="AI Tutor", phase="action", detail={"decision": "selected question bank task" if question_id else "generated practice task", "tool": "question bank" if question_id else "LLM adapter", "practice_id": practice.id, "question_id": question_id}, mode=runtime.provider.mode))
    db.commit()
    return {"id": practice.id, "prompt": prompt, "skill": skill}


@app.get("/api/practice/{practice_id}")
def get_practice(practice_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    item = owned(db, Practice, practice_id, user)
    return {"id": item.id, "prompt": item.prompt, "skill": item.skill}


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
    for skill, seconds in {"listening": 300, "reading": 300, "writing": 900, "speaking": 180}.items():
        sections[skill]["duration_seconds"] = seconds
    exam = MockExam(user_id=user.id, exam=profile.exam, sections=sections)
    db.add(exam)
    db.commit()
    return mock_view(exam, db)


def mock_view(exam: MockExam, db: Session):
    answers = {answer.skill: answer.answer for answer in db.scalars(select(ExamResponse).where(ExamResponse.exam_id == exam.id))}
    created_at = exam.created_at if exam.created_at.tzinfo else exam.created_at.replace(tzinfo=timezone.utc)
    return {"id": exam.id, "exam": exam.exam, "status": exam.status, "reduced_length": True, "created_at": created_at,
            "duration_seconds": sum(section["duration_seconds"] for section in exam.sections.values()),
            "sections": exam.sections, "answers": answers, "result": package_view(db.get(ResultPackage, exam.package_id)) if exam.package_id else None}


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
