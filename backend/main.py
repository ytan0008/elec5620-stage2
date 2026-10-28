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
from backend.models import User, PasswordReset, Profile, OnboardingSession, AgentConversation, LearnerPortrait, QuestionItem, Plan, StudyTask, Practice, Submission, MockExam, ExamResponse, ResultPackage, Escalation, InstructorDecision, Material, MaterialInteraction, PerformanceReport, AgentEvent, AuditLog, QualityCheck, SystemSetting, SpeakingSession, NotebookEntry, LearnerMemory, IssueReport, AgentMemory
from backend.schemas import AvailabilityInput, RegisterInput, LoginInput, PasswordResetRequest, PasswordResetConfirm, ProfileInput, SubmitInput, ExamAnswerInput, ReviewInput, ThresholdInput, ChangeRequestInput, OnboardingTurn, QuestionGenerationInput, AgentChatTurn, AvatarInput, SpeakingStartInput, SpeakingTurnInput, TTSInput, MockCreateInput, NotebookAddInput, NotebookUpdateInput, NotebookReviewInput, NotebookRetryInput, MemoryInput, IssueReportInput, IssueResolveInput, AnomalyAckInput
from backend.recovery import mail_ready, new_reset_token, reset_path, send_reset_email, token_digest
from backend.onboarding import FIELDS, QUESTIONS as ONBOARDING_QUESTIONS, clean_extraction, next_field
from backend.knowledge import build_graph
from backend.agents import AgentRuntime, LocalGenerationUnavailable, practice_prompt
from backend import adaptation
from backend import escalation
from backend import agent_core
from backend.agent_core import Toolkit
from backend.scoring import grade_objective, strip_answers, overall_band, find_errors
from backend import notebook
from backend import monitoring
from backend.speech import server_speech_available, synthesise, transcribe
from backend import content as bank
from backend import examiner
from backend.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed()
    yield


app = FastAPI(title="ELEC5620 CertifyAI", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    return JSONResponse(status_code=500, content={"detail": "Workflow execution failed"})


@app.exception_handler(LocalGenerationUnavailable)
async def local_generation_handler(request: Request, exc: LocalGenerationUnavailable):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


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
    config = settings()
    return {"status": "ok", "mode": config.ai_mode, "model": config.llm_model if config.ai_mode == "REAL" else "built-in engine",
            "server_tts": server_speech_available(), "server_stt": server_speech_available()}


def user_view(user: User, profile_complete: bool | None = None) -> dict:
    result = {**dto(user, "id", "email", "name", "role"), "avatar": user.avatar or "witch"}
    if profile_complete is not None:
        result["profile_complete"] = profile_complete
    return result


@app.post("/api/auth/register")
def register(data: RegisterInput, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == data.email.lower())):
        raise HTTPException(409, "Email already registered")
    user = User(email=data.email.lower(), name=data.name, password_hash=hash_password(data.password), role="learner", avatar="witch")
    db.add(user)
    db.flush()
    profile_input = data.model_dump(exclude={"email", "name", "password"}, exclude_none=True, mode="json")
    if profile_input:
        db.add(Profile(user_id=user.id, **profile_input))
    db.add(AuditLog(user_id=user.id, action="registered", detail={"profile_complete": bool(profile_input)}))
    db.commit()
    return {"token": token_for(user), "user": user_view(user, bool(profile_input))}


@app.post("/api/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not hasher.verify(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    complete = user.role == "instructor" or bool(db.scalar(select(Profile.id).where(Profile.user_id == user.id)))
    return {"token": token_for(user), "user": user_view(user, complete)}


@app.post("/api/auth/password-reset/request")
def request_password_reset(data: PasswordResetRequest, db: Session = Depends(get_db)):
    config = settings()
    on_screen = not mail_ready() and (config.password_reset_link_on_screen or config.demo_mode)
    if not mail_ready() and not on_screen:
        raise HTTPException(503, "Password recovery email is not configured")
    response = {"message": "If this email has an account, a reset link has been issued."}
    token = new_reset_token()
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user:
        now = datetime.now(timezone.utc)
        for previous in db.scalars(select(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))):
            previous.used_at = now
        db.add(PasswordReset(user_id=user.id, token_hash=token_digest(token), expires_at=now + timedelta(minutes=30)))
        db.add(AuditLog(user_id=user.id, action="password_reset_requested", detail={"delivery": "screen" if on_screen else "email"}))
        if not on_screen:
            try:
                send_reset_email(user.email, token)
            except (OSError, smtplib.SMTPException):
                db.rollback()
                raise HTTPException(503, "Recovery email could not be sent; please try again later")
        db.commit()
    if on_screen:
        response["reset_path"] = reset_path(token)
        response["notice"] = "LOCAL SERVER: email delivery is not configured, so the one-time reset link is shown here."
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
    return user_view(user)


@app.put("/api/me/avatar")
def set_avatar(data: AvatarInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.avatar = data.avatar
    db.commit()
    return user_view(user)


@app.get("/api/onboarding")
def onboarding_state(user: User = Depends(learner), db: Session = Depends(get_db)):
    session = db.scalar(select(OnboardingSession).where(OnboardingSession.user_id == user.id))
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    draft = profile_data(profile) if profile else (session.draft if session else {})
    missing = next_field(draft)
    return {"draft": draft, "messages": session.messages if session else [], "ready": missing is None, "completed": bool(profile), "next_field": missing, "assistant_message": ONBOARDING_QUESTIONS[missing] if missing else "Your profile is ready. Review it and confirm to create your learning portrait.", "mode": settings().ai_mode}


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


CHAT_CONTEXTS = {"profile", "plan", "speaking", "writing", "reading", "listening", "dashboard", "questions", "materials", "analytics", "knowledge", "portrait", "workflow", "settings", "tutor", "notebook"}
TUTOR_CONTEXTS = ("speaking", "writing", "reading", "listening", "tutor", "notebook")


def agent_for(context: str) -> str:
    return "AI Tutor" if context in TUTOR_CONTEXTS else "Learning Coordinator"


def chat_record(db: Session, user_id: int, context: str) -> AgentConversation | None:
    if context not in CHAT_CONTEXTS:
        raise HTTPException(404, "Unknown conversation context")
    return db.scalar(select(AgentConversation).where(AgentConversation.user_id == user_id, AgentConversation.context == context))


@app.get("/api/chat/{context}")
def chat_history(context: str, user: User = Depends(learner), db: Session = Depends(get_db)):
    record = chat_record(db, user.id, context)
    return {"context": context, "agent": agent_for(context), "messages": record.messages if record else [], "mode": settings().ai_mode}


def safe_text(value: str) -> str:
    """Remove obvious contact details before any external model call."""
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email redacted]", value)
    return re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "[phone redacted]", value)


def save_word(db: Session, runtime: AgentRuntime, user: User, word: str, context: str = "", skill: str = "", source: str = "", language: str = "Chinese (Simplified)") -> tuple[NotebookEntry, bool]:
    existing = db.scalar(select(NotebookEntry).where(NotebookEntry.user_id == user.id, NotebookEntry.kind == "word", NotebookEntry.key == notebook.norm(word)))
    detail = {"contexts": [context] if context else []}
    if not existing or not (existing.detail or {}).get("meanings"):
        dictionary = notebook.dictionary_lookup(word) if " " not in word.strip() or len(word) < 30 else {}
        try:
            detail.update(runtime.provider.word_info(word, context, language, dictionary))
        except Exception:
            detail.update(dictionary)
    return notebook.add_entry(db, user.id, "word", word.strip().lower(), skill=skill, source=source, detail=detail)


def due_word(db: Session, user_id: int) -> NotebookEntry | None:
    return db.scalar(select(NotebookEntry).where(NotebookEntry.user_id == user_id, NotebookEntry.kind == "word", NotebookEntry.mastered.is_(False))
                     .order_by(NotebookEntry.next_review, NotebookEntry.count.desc()))


@app.post("/api/chat/{context}")
def chat_turn(context: str, data: AgentChatTurn, user: User = Depends(learner), db: Session = Depends(get_db)):
    record = chat_record(db, user.id, context)
    if active_mock(db, user.id):
        raise HTTPException(423, "The tutor is unavailable while a mock exam is in progress")
    profile = profile_for(db, user)
    plan = db.scalar(select(Plan).where(Plan.user_id == user.id, Plan.status == "ACTIVE").order_by(Plan.id.desc()))
    runtime = AgentRuntime(db)
    started = datetime.now(timezone.utc)
    history = record.messages if record else []
    actions, events, quiz = [], [], None
    # Quiz answer: the previous tutor turn asked the learner to use a saved word.
    last = history[-1] if history else {}
    if last.get("quiz"):
        entry = db.scalar(select(NotebookEntry).where(NotebookEntry.user_id == user.id, NotebookEntry.kind == "word", NotebookEntry.key == notebook.norm(last["quiz"])))
        used = re.search(rf"\b{re.escape(last['quiz'][:max(3, len(last['quiz']) - 2)])}", data.message, flags=re.I)
        errors = find_errors(data.message, spoken=True)
        if entry:
            notebook.review(entry, bool(used) and not errors)
        verdict = (f"Nice — you used “{last['quiz']}” correctly. " if used and not errors else
                   f"You didn't use “{last['quiz']}” — try again later. " if not used else f"Good use of “{last['quiz']}”, but check this: {errors[0]['suggestion']} ")
        actions.append(verdict + (notebook.word_summary(entry) if entry and not used else "") + " Say “quiz me” for another word.")
        events.append({"type": "quiz", "word": last["quiz"], "remembered": bool(used) and not errors})
    elif notebook.is_quiz_request(data.message):
        entry = due_word(db, user.id)
        if entry:
            quiz = entry.text
            hint = ((entry.detail or {}).get("meanings") or [{}])[0].get("definition", "")
            actions.append(f"Quiz time! Make your own sentence using “{entry.text}”." + (f" Hint: {hint}" if hint else ""))
        else:
            actions.append("Your word book is empty or fully mastered. Select any unfamiliar word on a page, or tell me “I don't know the word …”, and I'll save it for quizzes.")
    for word in notebook.requested_words(data.message):
        quoted = re.search(r"sentence[^\"“]*[\"“]([^\"”]{8,600})[\"”]", data.message)
        entry, created = save_word(db, runtime, user, word, context=quoted.group(1) if quoted else "", skill=context if context in ("speaking", "writing", "reading", "listening") else "", source=f"Chat · {context}")
        actions.append(f"📒 {'Saved' if created else 'Already in your word book (count +1)'}: {notebook.word_summary(entry)}")
        events.append({"type": "word", "id": entry.id, "word": entry.text, "created": created})
    for kind, text in notebook.extract_memories(data.message):
        notebook.remember(db, user.id, kind, text)
        events.append({"type": "memory", "text": text})
    memory_texts = [item.text for item in notebook.memories(db, user.id)]
    summary = notebook.stats(db, user.id)
    kit = Toolkit(db, "tutor" if agent_for(context) == "AI Tutor" else "coordinator", user.id, profile.exam)
    try:
        safe_history = [{"role": item.get("role"), "text": safe_text(item.get("text", ""))} for item in history]
        result = runtime.provider.chat(context, safe_text(data.message), profile_data(profile), plan.content if plan else None, safe_history, data.persona,
                                       memory_texts, {k: summary[k] for k in ("mistakes_by_type", "grammar_issues", "due_words", "counts")}, actions, kit)
    except Exception:
        raise HTTPException(503, "Agent reply unavailable; please try again")
    kit.log("chat", runtime.provider.mode)
    for text in result.remember[:3]:
        if 4 <= len(text) <= 300:
            notebook.remember(db, user.id, "note", text, source="tutor")
            events.append({"type": "memory", "text": text})
    if not record:
        record = AgentConversation(user_id=user.id, context=context, messages=[])
        db.add(record)
    reply = {"role": "assistant", "text": result.reply, **({"quiz": quiz} if quiz else {})}
    record.messages = (record.messages or [])[-58:] + [{"role": "learner", "text": data.message}, reply]
    db.add(AgentEvent(user_id=user.id, workflow="chat", agent=agent_for(context), phase="action", detail={"context": context, "decision": "respond to learner with memory", "memories_used": len(memory_texts), "notebook_actions": [e["type"] for e in events], "tool": "shared LLM adapter"},
                      mode=runtime.provider.mode, duration_ms=int((datetime.now(timezone.utc) - started).total_seconds() * 1000)))
    db.commit()
    return {"context": context, "agent": agent_for(context), "messages": record.messages, "mode": runtime.provider.mode, "events": events}


# ---------------------------------------------------------------- exam lock and dictionary

def active_mock(db: Session, user_id: int) -> MockExam | None:
    """A mock exam that is still running locks dictionary meanings and the tutor chat."""
    now_ = datetime.now(timezone.utc)
    for exam in db.scalars(select(MockExam).where(MockExam.user_id == user_id, MockExam.status == "IN_PROGRESS")):
        created = exam.created_at if exam.created_at.tzinfo else exam.created_at.replace(tzinfo=timezone.utc)
        duration = sum(exam.sections.get(skill, {}).get("duration_seconds", 0) for skill in ("listening", "reading", "writing", "speaking"))
        if created + timedelta(seconds=duration) > now_:
            return exam
    return None


@app.get("/api/dictionary")
def dictionary(word: str, user: User = Depends(learner), db: Session = Depends(get_db)):
    word = word.strip().strip(".,;:!?\"'()“”‘’").lower()
    if not word or len(word) > 60 or len(word.split()) > 5:
        raise HTTPException(422, "Select a single word or short phrase")
    if active_mock(db, user.id):
        raise HTTPException(423, "Meanings are hidden while a mock exam is in progress")
    saved = db.scalar(select(NotebookEntry).where(NotebookEntry.user_id == user.id, NotebookEntry.kind == "word", NotebookEntry.key == notebook.norm(word)))
    return {"word": word, **notebook.offline_lookup(word), "saved": bool(saved)}


# ---------------------------------------------------------------- notebooks

def notebook_owned(db: Session, entry_id: int, user: User) -> NotebookEntry:
    entry = db.get(NotebookEntry, entry_id)
    if not entry or entry.user_id != user.id:
        raise HTTPException(404, "Notebook entry not found")
    return entry


@app.get("/api/notebook")
def list_notebook(kind: str | None = None, skill: str | None = None, include_mastered: bool = True, user: User = Depends(learner), db: Session = Depends(get_db)):
    query = select(NotebookEntry).where(NotebookEntry.user_id == user.id)
    if kind:
        if kind not in notebook.KINDS:
            raise HTTPException(400, "Unknown notebook")
        query = query.where(NotebookEntry.kind == kind)
    if skill:
        query = query.where(NotebookEntry.skill == skill)
    if not include_mastered:
        query = query.where(NotebookEntry.mastered.is_(False))
    items = [notebook.view(entry) for entry in db.scalars(query.order_by(NotebookEntry.updated_at.desc()).limit(500))]
    if active_mock(db, user.id):
        for item in items:
            if item["kind"] == "word":
                item["detail"], item["hidden"] = {"contexts": item["detail"].get("contexts", [])}, True
    return items


@app.get("/api/notebook/stats")
def notebook_stats(user: User = Depends(learner), db: Session = Depends(get_db)):
    return notebook.stats(db, user.id)


@app.post("/api/notebook")
def add_notebook(data: NotebookAddInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    runtime = AgentRuntime(db)
    locked = data.exam or active_mock(db, user.id) is not None
    text = re.sub(r"\s+", " ", data.text).strip()
    if data.kind == "word":
        if len(text) > 60 or len(text.split()) > 5:
            raise HTTPException(422, "Select a single word or short phrase for the word book")
        entry, created = save_word(db, runtime, user, text.strip(".,;:!?\"'()“”‘’"), data.context or "", data.skill, data.source, data.language)
    elif data.kind == "sentence":
        patterns = notebook.sentence_patterns(text)
        entry, created = notebook.add_entry(db, user.id, "sentence", text, category=data.category or ", ".join(patterns[:3]) or "Useful sentence", skill=data.skill, source=data.source,
                                            detail={"origin": "saved", "patterns": patterns, **({"note": data.note} if data.note else {})})
    elif data.kind == "grammar":
        found = find_errors(text, spoken=False)
        issue = data.category or (found[0]["issue"] if found else "Grammar note")
        entry, created = notebook.add_entry(db, user.id, "grammar", text, key=f"{notebook.norm(issue)}|{notebook.norm(text)}", category=issue, skill=data.skill, source=data.source or "Added manually",
                                            detail={"issue": issue, "suggestion": data.note or (found[0]["suggestion"] if found else ""), "correction": data.correction or (found[0].get("correction", "") if found else "")})
    else:
        entry, created = notebook.add_entry(db, user.id, "mistake", text, category=data.category or "Other", skill=data.skill, source=data.source or "Added manually",
                                            detail={"type": "completion", "answer": data.correction or "", "note": data.note or ""})
    db.commit()
    result = {**notebook.view(entry), "created": created}
    if locked and entry.kind == "word":
        # During a test the word is saved, but its meaning stays hidden until the learner finishes.
        result["detail"] = {"contexts": (entry.detail or {}).get("contexts", [])}
        result["hidden"] = True
    return result


@app.patch("/api/notebook/{entry_id}")
def update_notebook(entry_id: int, data: NotebookUpdateInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    entry = notebook_owned(db, entry_id, user)
    if data.mastered is not None:
        entry.mastered = data.mastered
    detail = dict(entry.detail or {})
    if data.note is not None:
        detail["note"] = data.note
    if data.translation is not None:
        detail["translation"] = data.translation
    entry.detail = detail
    db.commit()
    return notebook.view(entry)


@app.delete("/api/notebook/{entry_id}")
def delete_notebook(entry_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    db.delete(notebook_owned(db, entry_id, user))
    db.commit()
    return {"deleted": True}


@app.post("/api/notebook/{entry_id}/review")
def review_notebook(entry_id: int, data: NotebookReviewInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    entry = notebook.review(notebook_owned(db, entry_id, user), data.remembered)
    db.commit()
    return notebook.view(entry)


@app.post("/api/notebook/{entry_id}/retry")
def retry_notebook(entry_id: int, data: NotebookRetryInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    entry = notebook_owned(db, entry_id, user)
    if entry.kind != "mistake" or not (entry.detail or {}).get("answer"):
        raise HTTPException(409, "Only recorded test questions can be retried")
    correct = notebook.retry_mistake(entry, data.answer)
    db.commit()
    return {"correct": correct, "entry": notebook.view(entry)}


# ---------------------------------------------------------------- tutor memory and coaching

@app.get("/api/tutor/memory")
def tutor_memory(user: User = Depends(learner), db: Session = Depends(get_db)):
    return [dto(item, "id", "kind", "text", "source", "updated_at") for item in notebook.memories(db, user.id, 100)]


@app.post("/api/tutor/memory")
def add_memory(data: MemoryInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    item = notebook.remember(db, user.id, data.kind, data.text, source="learner")
    db.commit()
    return dto(item, "id", "kind", "text", "source", "updated_at")


@app.delete("/api/tutor/memory/{memory_id}")
def forget_memory(memory_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    item = db.get(LearnerMemory, memory_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Memory not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@app.post("/api/tutor/coach")
def tutor_coach(persona: str = "witch", user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_data(profile_for(db, user))
    memory_texts = [item.text for item in notebook.memories(db, user.id)]
    summary = notebook.stats(db, user.id)
    progress = latest_progress(db, user.id)
    points = notebook.coaching_points(summary, profile, memory_texts)
    if progress["weaknesses"]:
        points.append(f"Your weakest verified skill right now is {progress['weaknesses'][0]} ({progress['skill_scores'].get(progress['weaknesses'][0])}). Do one timed {progress['weaknesses'][0]} task today.")
    runtime = AgentRuntime(db)
    try:
        kit = Toolkit(db, "tutor", user.id, profile.get("exam", "IELTS"))
        message = runtime.provider.coach(points, profile, memory_texts, {**{k: summary[k] for k in ("mistakes_by_type", "grammar_issues", "due_words", "due_mistakes")}, "skill_scores": progress["skill_scores"]}, persona, kit)
        kit.log("coaching", runtime.provider.mode)
    except Exception:
        message = "Here's your coaching plan for today:\n" + "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))
    record = chat_record(db, user.id, "tutor")
    if not record:
        record = AgentConversation(user_id=user.id, context="tutor", messages=[])
        db.add(record)
    record.messages = (record.messages or [])[-58:] + [{"role": "assistant", "text": message, "coach": True}]
    db.add(AgentEvent(user_id=user.id, workflow="coaching", agent="AI Tutor", phase="decision", detail={"decision": "personalised coaching from notebooks and memory", "points": len(points)}, mode=runtime.provider.mode))
    db.commit()
    return {"message": message, "messages": record.messages, "stats": summary}


def record_release(db: Session, user_id: int, package: ResultPackage, skill: str, source: str, test: dict | None = None) -> None:
    """Feed released results into the notebooks and the tutor's memory."""
    if package.state != "RELEASED":
        return
    payload = package.payload or {}
    if skill in ("listening", "reading") and test and payload.get("review"):
        notebook.record_objective_mistakes(db, user_id, test, payload["review"], skill, source)
    if skill in ("writing", "speaking"):
        notebook.record_feedback(db, user_id, payload, skill, source)
    notebook.update_progress_memory(db, user_id, skill, payload)


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
        kit = Toolkit(db, "coordinator", user.id, profile.exam)
        portrait = runtime.provider.portrait(profile_data(profile), kit).model_dump()
        kit.log("portrait", runtime.provider.mode)
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
    if adapt:  # UC7, triggered by the learner
        result = adaptation.propose(db, user.id, profile_data(profile), latest_progress(db, user.id), "learner_request")
        db.commit()
        if result["plan"] is None:  # 3a / 4a: the existing plan stays active
            return {"id": None, "status": "KEPT_EXISTING", "outcome": result["outcome"], "message": result["message"], "package": None}
        return {"id": result["plan"].id, "status": result["plan"].status, "outcome": result["outcome"], "package": package_view(result["package"])}
    runtime = AgentRuntime(db)
    state = runtime.plan_graph().invoke({"user_id": user.id, "workflow": "plan", "profile": profile_data(profile), "progress": latest_progress(db, user.id)})
    package = db.get(ResultPackage, state["package_id"])
    version = (db.scalar(select(func.max(Plan.version)).where(Plan.user_id == user.id)) or 0) + 1
    plan = Plan(user_id=user.id, version=version, kind="initial", status="PROPOSED" if package.state == "RELEASED" else "HELD", content=package.payload, package_id=package.id)
    db.add(plan)
    db.commit()
    return {"id": plan.id, "status": plan.status, "package": package_view(package)}


@app.get("/api/plans/adaptation-notice")
def adaptation_notice(user: User = Depends(learner), db: Session = Depends(get_db)):
    """UC7 3a / 4a: why the learner's existing plan was kept the last time an adaptation was attempted."""
    return {"notice": adaptation.latest_notice(db, user.id)}


@app.post("/api/plans/{plan_id}/decision")
def plan_decision(plan_id: int, accept: bool, user: User = Depends(learner), db: Session = Depends(get_db)):
    plan = owned(db, Plan, plan_id, user)
    if plan.status != "PROPOSED" or db.get(ResultPackage, plan.package_id).state != "RELEASED":
        raise HTTPException(409, "Only verified proposed plans can be decided")
    undelivered: list[str] = []
    if accept:
        previous = None
        for old in db.scalars(select(Plan).where(Plan.user_id == user.id, Plan.status == "ACTIVE")):
            previous = previous or old.content
            old.status = "SUPERSEDED"
        plan.status = "ACTIVE"
        for item in plan.content["activities"]:
            db.add(StudyTask(user_id=user.id, plan_id=plan.id, skill=item["skill"], title=item["title"]))
        undelivered = adaptation.notify_agents(db, plan, previous)  # 8a: the plan stays active even if a delivery fails
    else:
        plan.status = "REJECTED"
    priorities = ", ".join((plan.content or {}).get("priorities", [])[:4])
    agent_core.remember(db, "coordinator", user.id, f"Learner {'accepted' if accept else 'rejected'} plan v{plan.version} (priorities {priorities}).",
                        "episode" if accept else "lesson", {"plan_id": plan.id, "accepted": accept})
    db.add(AuditLog(user_id=user.id, action="plan_accepted" if accept else "plan_rejected", detail={"plan_id": plan.id}))
    db.commit()
    return {"id": plan.id, "status": plan.status, "notifications_pending": undelivered}


@app.post("/api/plans/{plan_id}/request-changes")
def request_plan_changes(plan_id: int, data: ChangeRequestInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    previous = owned(db, Plan, plan_id, user)
    if previous.status != "PROPOSED":
        raise HTTPException(409, "Only a proposed plan can be revised")
    profile = profile_for(db, user)
    progress = latest_progress(db, user.id)
    progress["change_request"] = data.note
    agent_core.remember(db, "coordinator", user.id, f"Learner asked to change plan v{previous.version}: {data.note[:300]}", "lesson", {"plan_id": plan_id})
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
            "source_url": item.source_url, "available": available, "verification_state": package.state if package else "CURATED",
            "structured": bool(item.content), "chart": (item.content or {}).get("chart") if available else None}


@app.get("/api/questions")
def questions(exam: str | None = None, skill: str | None = None, user: User = Depends(learner), db: Session = Depends(get_db)):
    exam = exam or profile_for(db, user).exam
    if exam not in ("IELTS", "TOEFL"):
        raise HTTPException(400, "Unknown exam")
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
    runtime = AgentRuntime(db)
    try:
        output = runtime.provider.generate_question(profile.exam, data.skill, data.topic, data.task)
        output = output.model_dump() if hasattr(output, "model_dump") else output
    except LocalGenerationUnavailable:
        raise
    except Exception as exc:
        output = {"title": "Question requires review", "confidence": {}, "error_type": type(exc).__name__}
    package = runtime.verify_output(user.id, "question", output)
    item = QuestionItem(user_id=user.id, exam=profile.exam, skill=data.skill, task_type=output.get("task_type", "Generated task"), title=output.get("title", "Question under review")[:200], prompt=output.get("prompt"), answer_key=None, topic=data.topic[:80],
                        source_kind="LOCAL_GENERATED" if runtime.provider.local else "AI_GENERATED", content=output.get("content"), package_id=package.id)
    db.add(item)
    db.commit()
    return question_view(item, db)


def seen_content(db: Session, user_id: int, skill: str) -> set[str]:
    return {practice.prompt.get("content_id") for practice in db.scalars(select(Practice).where(Practice.user_id == user_id, Practice.skill == skill)) if practice.prompt.get("content_id")}


def public_prompt(prompt: dict) -> dict:
    """Practice prompt as sent to the learner: objective answer keys stay on the server."""
    if isinstance(prompt.get("test"), dict) and prompt["test"].get("kind") in ("listening", "reading"):
        return {**prompt, "test": strip_answers(prompt["test"])}
    return {key: value for key, value in prompt.items() if key != "answer_key"}


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
        if item.content:
            prompt = practice_prompt(item.content, item.source_kind)
        else:
            prompt = {"title": item.title, "text": item.prompt, "answer_key": item.answer_key, "mode": item.source_kind,
                      "task_type": item.task_type, "duration_seconds": 900 if skill == "speaking" else 2400 if skill == "writing" else 600}
    else:
        prompt = runtime.provider.prompt(profile.exam, skill, seen_content(db, user.id, skill))
    practice = Practice(user_id=user.id, exam=profile.exam, skill=skill, prompt=prompt)
    db.add(practice)
    db.flush()
    db.add(AgentEvent(user_id=user.id, workflow=skill, agent="AI Tutor", phase="action", detail={"decision": "selected question bank task", "tool": "question bank", "practice_id": practice.id, "question_id": question_id, "content_id": prompt.get("content_id")}, mode=runtime.provider.mode))
    db.commit()
    return {"id": practice.id, "prompt": public_prompt(prompt), "skill": skill}


@app.get("/api/practice/{practice_id}")
def get_practice(practice_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    item = owned(db, Practice, practice_id, user)
    return {"id": item.id, "prompt": public_prompt(item.prompt), "skill": item.skill}


@app.get("/api/practice/{practice_id}/attempts")
def attempts(practice_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    practice = owned(db, Practice, practice_id, user)
    submissions = db.scalars(select(Submission).where(Submission.practice_id == practice.id).order_by(Submission.attempt)).all()
    return [{"id": sub.id, "text": sub.text, "attempt": sub.attempt, "audio_available": bool(sub.audio_path), "created_at": sub.created_at, "result": package_view(db.get(ResultPackage, sub.package_id))} for sub in submissions]


@app.get("/api/practice/submissions/{submission_id}/audio")
def get_submission_audio(submission_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    sub = owned(db, Submission, submission_id, user)
    if not sub.audio_path or not Path(sub.audio_path).is_file():
        raise HTTPException(404, "Audio not found")
    return FileResponse(sub.audio_path, media_type="audio/webm")


AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/mpeg", "audio/x-wav")


async def read_audio(file: UploadFile) -> bytes:
    if not (file.content_type or "").split(";")[0] in AUDIO_TYPES:
        raise HTTPException(415, "Unsupported audio type")
    data = await file.read(25_000_001)
    if len(data) > 25_000_000:
        raise HTTPException(413, "Audio exceeds 25 MB")
    return data


@app.post("/api/practice/{practice_id}/audio")
async def upload_audio(practice_id: int, file: UploadFile = File(...), user: User = Depends(learner), db: Session = Depends(get_db)):
    practice = owned(db, Practice, practice_id, user)
    if practice.skill != "speaking":
        raise HTTPException(400, "Audio is only for speaking practice")
    data = await read_audio(file)
    folder = Path("uploads") / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"practice-{practice.id}-{uuid4().hex}.webm"
    path.write_bytes(data)
    db.add(AuditLog(user_id=user.id, action="audio_uploaded", detail={"practice_id": practice.id, "bytes": len(data)}))
    db.commit()
    if server_speech_available():
        try:
            return {"stored": True, "transcription_available": True, "transcript": transcribe(path), "message": "Recording saved and transcribed. Review the transcript before submitting."}
        except Exception as exc:
            db.add(AuditLog(user_id=user.id, action="transcription_failed", detail={"practice_id": practice.id, "error_type": type(exc).__name__}))
            db.commit()
            return {"stored": True, "transcription_available": False, "message": "Recording saved, but cloud transcription failed. Live browser recognition or typing still works."}
    return {"stored": True, "transcription_available": False, "message": "Recording saved for replay. Your words are captured by live speech recognition in the browser."}


def latest_unused_audio(db: Session, user_id: int, practice_id: int) -> str | None:
    used = {item for item in db.scalars(select(Submission.audio_path).where(Submission.practice_id == practice_id)) if item}
    folder = Path("uploads") / str(user_id)
    files = sorted(folder.glob(f"practice-{practice_id}-*.webm"), key=lambda item: item.stat().st_mtime, reverse=True) if folder.exists() else []
    return next((str(item) for item in files if str(item) not in used), None)


def objective_output(prompt: dict, answers: dict, skill: str, exam: str) -> dict:
    test = prompt["test"]
    graded = grade_objective(test, answers, skill, exam)
    wrong = [item for item in graded["items"] if not item["correct"]]
    comments = [{"issue": f"Question {item['n']}", "suggestion": f"Correct answer: {item['answer']}" + (f" — {item['evidence']}" if item["evidence"] else ""), "sentence": f"Your answer: {item['given'] or '(blank)'}"} for item in wrong[:12]]
    if not comments:
        comments = [{"issue": "All answers correct", "suggestion": "Try a harder part or a full test under timed conditions."}]
    types = {}
    for item in graded["items"]:
        bucket = types.setdefault(item["type"], [0, 0])
        bucket[0] += item["correct"]
        bucket[1] += 1
    weakest = min(types.items(), key=lambda pair: pair[1][0] / pair[1][1])[0] if types else None
    names = {"completion": "completion", "mcq": "multiple choice", "matching": "matching", "tfng": "True/False/Not Given", "ynng": "Yes/No/Not Given", "cwords": "Complete the Words"}
    summary = (f"You answered {graded['raw']} of {graded['total']} correctly"
               + (f" (equivalent to about {graded['scaled_40']}/40)" if graded["scaled_40"] is not None else "")
               + f". Estimated {graded['score_scale'].split(' ')[0]} {skill} score: {graded['band']}."
               + (f" Your weakest question type was {names.get(weakest, weakest)}." if weakest and len(types) > 1 else ""))
    output = {"summary": summary, "criteria": {skill: graded["band"]}, "estimated_overall": graded["band"], "score_scale": graded["score_scale"], "official": False,
              "raw_score": graded["raw"], "total": graded["total"], "review": graded["items"], "confidence": {skill: .92}, "comments": comments,
              "question_types": {names.get(k, k): f"{v[0]}/{v[1]}" for k, v in types.items()}}
    if skill == "listening":
        output["transcript"] = [{"title": section.get("title"), "script": section.get("script", []),
                                 "clips": [q.get("clip") for g in section.get("groups", []) for q in g.get("questions", []) if q.get("clip")]} for section in test["sections"]]
    return output


@app.post("/api/practice/{practice_id}/submit")
def submit_practice(practice_id: int, data: SubmitInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    practice = owned(db, Practice, practice_id, user)
    profile = profile_for(db, user)
    runtime = AgentRuntime(db)
    prompt = practice.prompt
    text = data.text
    if practice.skill in ("writing", "speaking"):
        if data.scenario == "invalid" and runtime.provider.local:
            package = runtime.verify_output(user.id, practice.skill, {"summary": "Malformed output", "criteria": {}, "confidence": {}})
        else:
            state = runtime.practice_graph().invoke({"user_id": user.id, "workflow": practice.skill, "profile": profile_data(profile), "skill": practice.skill, "text": text,
                                                     "prompt": prompt.get("text", ""), "task": data.task or prompt.get("task") or ("speaking" if practice.skill == "speaking" else "task2"),
                                                     "metrics": data.metrics, "scenario": data.scenario})
            package = db.get(ResultPackage, state["package_id"])
    elif isinstance(prompt.get("test"), dict):
        answers = {str(k): str(v)[:200] for k, v in (data.answers or {}).items()}
        output = objective_output(prompt, answers, practice.skill, profile.exam)
        text = json.dumps(answers)
        package = runtime.verify_output(user.id, practice.skill, output)
    else:
        key = prompt.get("answer_key") or ""
        correct = bool(key) and key in text.lower()
        score = (6.5 if correct else 4.5) if profile.exam == "IELTS" else (4.5 if correct else 3.0)
        package = runtime.verify_output(user.id, practice.skill, {"summary": "Correct answer supported by the text" if correct else f"Review the evidence and try identifying: {key}", "criteria": {practice.skill: score}, "estimated_overall": score, "official": False, "confidence": {practice.skill: .90}, "comments": [{"issue": "Check source evidence", "suggestion": key}]})
    attempt = (db.scalar(select(func.max(Submission.attempt)).where(Submission.practice_id == practice.id)) or 0) + 1
    audio_path = latest_unused_audio(db, user.id, practice.id) if practice.skill == "speaking" else None
    sub = Submission(practice_id=practice.id, user_id=user.id, text=text or "(no answers)", audio_path=audio_path, attempt=attempt, package_id=package.id)
    db.add(sub)
    practice.status = "SUBMITTED"
    record_release(db, user.id, package, practice.skill, prompt.get("title", practice.skill), prompt.get("test"))
    db.commit()
    return {"submission_id": sub.id, "attempt": attempt, "result": package_view(package)}


@app.get("/api/results/{package_id}")
def result(package_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    return package_view(owned(db, ResultPackage, package_id, user))


# ---------------------------------------------------------------- live speaking examiner

def speaking_view(session: SpeakingSession) -> dict:
    return {"id": session.id, "exam": session.exam, "status": session.status, "practice_id": session.practice_id, "mock_id": session.mock_id, "persona": session.persona,
            "log": [{k: v for k, v in item.items() if k != "repeat_target" or session.status == "COMPLETED"} for item in session.log],
            "ui": examiner.ui(session.test, session.state), "test_title": session.test.get("title")}


@app.post("/api/speaking/sessions")
def start_speaking(data: SpeakingStartInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    runtime = AgentRuntime(db)
    practice_id = None
    if data.mock_id is not None:
        exam = owned(db, MockExam, data.mock_id, user)
        if exam.status != "IN_PROGRESS" or "test" not in exam.sections.get("speaking", {}):
            raise HTTPException(409, "This mock exam has no open speaking section")
        test = exam.sections["speaking"]["test"]
    else:
        practice = start_practice("speaking", data.question_id, user, db)
        practice_id = practice["id"]
        test = db.get(Practice, practice_id).prompt.get("test")
        if not test:
            raise HTTPException(409, "This speaking task does not support the live examiner")
    state, text, _ = examiner.start(test, data.persona)
    session = SpeakingSession(user_id=user.id, practice_id=practice_id, mock_id=data.mock_id, exam=test["exam"], persona=data.persona, test=test, state=state,
                              log=[{"role": "examiner", "text": text, "stage": state["stage"], "part": examiner.ui(test, state)["part"]}])
    db.add(session)
    db.add(AgentEvent(user_id=user.id, workflow="speaking", agent="AI Tutor", phase="action", detail={"decision": "start live speaking examiner", "exam": test["exam"], "mock_id": data.mock_id}, mode=runtime.provider.mode))
    db.commit()
    return speaking_view(session)


@app.get("/api/speaking/sessions/{session_id}")
def get_speaking(session_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    return speaking_view(owned(db, SpeakingSession, session_id, user))


@app.post("/api/speaking/sessions/{session_id}/turn")
def speaking_turn(session_id: int, data: SpeakingTurnInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    session = owned(db, SpeakingSession, session_id, user)
    if session.status != "ACTIVE":
        raise HTTPException(409, "This speaking test has finished")
    stage = session.state["stage"]
    if stage == "p2_prep" and data.event != "ready":
        raise HTTPException(409, "Finish preparing, then start your long turn")
    if stage != "p2_prep" and not data.text.strip():
        raise HTTPException(422, "No speech was captured; please answer again")
    runtime = AgentRuntime(db)
    part = examiner.ui(session.test, session.state)["part"]
    rephrase = (lambda st, scripted, said, follow: runtime.provider.examiner_rephrase(st, scripted, said, follow, session.persona)) if not runtime.provider.local else None
    state, reply, ui, done, meta = examiner.advance(session.test, session.state, data.text, data.event, rephrase)
    log = list(session.log)
    if data.event == "answer":
        log.append({"role": "learner", "text": data.text.strip(), "seconds": round(data.seconds, 1), "stage": stage, "part": part,
                    **{k: v for k, v in meta.items() if k in ("repeat_accuracy", "repeat_target")}})
    log.append({"role": "examiner", "text": reply, "stage": state["stage"], "part": ui["part"], **({"follow_up": True} if meta.get("follow_up") else {})})
    session.state, session.log = state, log
    if done:
        session.status = "FINISHED"
    db.commit()
    return {**speaking_view(session), "reply": reply, "done": done}


@app.post("/api/speaking/sessions/{session_id}/finish")
def finish_speaking(session_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    session = owned(db, SpeakingSession, session_id, user)
    if session.status == "COMPLETED":
        raise HTTPException(409, "Feedback was already requested for this test")
    text, metrics = examiner.transcript_for_assessment(session.test, session.log)
    if len(text.split()) < 5:
        raise HTTPException(409, "Answer at least one examiner question before requesting feedback")
    session.status = "COMPLETED"
    if session.mock_id is not None:
        exam = owned(db, MockExam, session.mock_id, user)
        if exam.status != "IN_PROGRESS":
            raise HTTPException(409, "Mock exam already submitted")
        payload = json.dumps({"session_id": session.id, "transcript": text, "metrics": metrics})
        response = db.scalar(select(ExamResponse).where(ExamResponse.exam_id == exam.id, ExamResponse.skill == "speaking"))
        if response:
            response.answer = payload
        else:
            db.add(ExamResponse(exam_id=exam.id, skill="speaking", answer=payload))
        db.commit()
        return {**speaking_view(session), "saved_to_mock": True, "metrics": metrics}
    practice = owned(db, Practice, session.practice_id, user)
    profile = profile_for(db, user)
    runtime = AgentRuntime(db)
    test = session.test
    question = (test.get("part2", {}).get("cue") or "") + " " + " ".join(test.get("part3", {}).get("questions", []) or test.get("interview", {}).get("questions", []))
    state = runtime.practice_graph().invoke({"user_id": user.id, "workflow": "speaking", "profile": profile_data(profile), "skill": "speaking", "text": text,
                                             "prompt": question, "task": "speaking", "metrics": metrics})
    package = db.get(ResultPackage, state["package_id"])
    attempt = (db.scalar(select(func.max(Submission.attempt)).where(Submission.practice_id == practice.id)) or 0) + 1
    sub = Submission(practice_id=practice.id, user_id=user.id, text=text, audio_path=latest_unused_audio(db, user.id, practice.id), attempt=attempt, package_id=package.id)
    db.add(sub)
    practice.status = "SUBMITTED"
    record_release(db, user.id, package, "speaking", f"Speaking test · {test.get('title', '')}")
    db.commit()
    return {**speaking_view(session), "submission_id": sub.id, "attempt": attempt, "metrics": metrics, "result": package_view(package)}


# ---------------------------------------------------------------- speech services

@app.post("/api/tts")
def text_to_speech(data: TTSInput, user: User = Depends(current_user)):
    if not server_speech_available():
        raise HTTPException(404, "Server voice is not configured; the browser voice will be used")
    try:
        return FileResponse(synthesise(data.text, data.voice, data.speed), media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(503, f"Voice service unavailable ({type(exc).__name__}); the browser voice will be used")


@app.post("/api/stt")
async def speech_to_text(file: UploadFile = File(...), user: User = Depends(current_user)):
    if not server_speech_available():
        raise HTTPException(404, "Server transcription is not configured")
    data = await read_audio(file)
    folder = Path("uploads") / "stt"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid4().hex}.webm"
    path.write_bytes(data)
    try:
        return {"text": transcribe(path)}
    except Exception as exc:
        raise HTTPException(503, f"Transcription failed ({type(exc).__name__})")
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------- mock examinations

@app.post("/api/mock-exams")
def create_mock(data: MockCreateInput | None = None, user: User = Depends(learner), db: Session = Depends(get_db)):
    profile = profile_for(db, user)
    if not db.scalar(select(Plan.id).where(Plan.user_id == user.id, Plan.status == "ACTIVE")):
        raise HTTPException(409, "Accept a learning plan before the mock exam")
    length = (data or MockCreateInput()).length
    sections = bank.mock_sections(profile.exam, length)
    sections["length"] = length
    exam = MockExam(user_id=user.id, exam=profile.exam, sections=sections)
    db.add(exam)
    db.commit()
    return mock_view(exam, db)


SKILLS = ("listening", "reading", "writing", "speaking")


def mock_view(exam: MockExam, db: Session):
    answers = {answer.skill: answer.answer for answer in db.scalars(select(ExamResponse).where(ExamResponse.exam_id == exam.id))}
    created_at = exam.created_at if exam.created_at.tzinfo else exam.created_at.replace(tzinfo=timezone.utc)
    legacy = "test" not in exam.sections.get("speaking", {})
    sections = {}
    for skill in SKILLS:
        section = exam.sections.get(skill, {})
        if skill in ("listening", "reading") and "sections" in section and exam.status == "IN_PROGRESS":
            section = strip_answers(section)
        sections[skill] = section
    return {"id": exam.id, "exam": exam.exam, "status": exam.status, "length": exam.sections.get("length", "short"), "legacy": legacy, "created_at": created_at,
            "duration_seconds": sum(exam.sections[skill].get("duration_seconds", 0) for skill in SKILLS if skill in exam.sections),
            "sections": sections, "answers": answers, "result": package_view(db.get(ResultPackage, exam.package_id)) if exam.package_id else None}


@app.get("/api/mock-exams")
def list_mocks(user: User = Depends(learner), db: Session = Depends(get_db)):
    return [mock_view(exam, db) for exam in db.scalars(select(MockExam).where(MockExam.user_id == user.id).order_by(MockExam.id.desc()))]


@app.get("/api/mock-exams/{exam_id}")
def get_mock(exam_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    return mock_view(owned(db, MockExam, exam_id, user), db)


@app.put("/api/mock-exams/{exam_id}/{skill}")
def save_exam_answer(exam_id: int, skill: str, data: ExamAnswerInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    exam = owned(db, MockExam, exam_id, user)
    if exam.status != "IN_PROGRESS" or skill not in SKILLS:
        raise HTTPException(409, "Section cannot be edited")
    response = db.scalar(select(ExamResponse).where(ExamResponse.exam_id == exam.id, ExamResponse.skill == skill))
    if response:
        response.answer = data.answer
    else:
        db.add(ExamResponse(exam_id=exam.id, skill=skill, answer=data.answer))
    db.commit()
    return {"saved": True}


def parse_json(value: str) -> dict:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


@app.post("/api/mock-exams/{exam_id}/submit")
def submit_mock(exam_id: int, user: User = Depends(learner), db: Session = Depends(get_db)):
    exam = owned(db, MockExam, exam_id, user)
    if exam.status != "IN_PROGRESS":
        raise HTTPException(409, "Exam already submitted")
    raw = {item.skill: item.answer for item in db.scalars(select(ExamResponse).where(ExamResponse.exam_id == exam.id))}
    answers = {skill: parse_json(raw.get(skill, "")) for skill in SKILLS}
    missing = [skill for skill in SKILLS if not raw.get(skill, "").strip() or (skill == "writing" and not any(str(v).strip() for v in answers["writing"].values()))
               or (skill == "speaking" and not answers["speaking"].get("transcript"))]
    if missing:
        raise HTTPException(409, "Complete all four sections: " + ", ".join(missing) + " still missing")
    runtime = AgentRuntime(db)
    kit = Toolkit(db, "tutor", user.id, exam.exam)
    scores, details = {}, {}
    for skill in ("listening", "reading"):
        graded = objective_output(exam.sections[skill] | {"test": exam.sections[skill]}, answers[skill], skill, exam.exam)
        scores[skill] = graded["estimated_overall"]
        details[skill] = {k: graded[k] for k in ("raw_score", "total", "review", "summary")} | ({"transcript": graded["transcript"]} if skill == "listening" else {})
    task_scores, writing_feedback = [], {}
    for task in exam.sections["writing"]["tasks"]:
        response = str(answers["writing"].get(task["task"], "")).strip()
        if len(response.split()) < 3:
            task_scores.append((task["task"], 1.0 if exam.exam == "IELTS" else 1.0))
            continue
        feedback = runtime.provider.feedback(exam.exam, "writing", response, "normal", task["prompt"], task["task"], toolkit=kit)
        band = round(sum(feedback.criteria.values()) / len(feedback.criteria) * 2) / 2
        task_scores.append((task["task"], band))
        writing_feedback[task["task"]] = {"criteria": feedback.criteria, "summary": feedback.summary, "comments": feedback.comments[:4], "band": band}
    weights = {"task2": 2, "task1": 1}
    total_weight = sum(weights.get(task, 1) for task, _ in task_scores)
    scores["writing"] = round(sum(band * weights.get(task, 1) for task, band in task_scores) / total_weight * 2) / 2
    details["writing"] = writing_feedback
    spoken = answers["speaking"]
    speaking = runtime.provider.feedback(exam.exam, "speaking", spoken["transcript"], "normal", "", "speaking", spoken.get("metrics"), kit)
    kit.log("mock_exam", runtime.provider.mode)
    scores["speaking"] = round(sum(speaking.criteria.values()) / len(speaking.criteria) * 2) / 2
    details["speaking"] = {"criteria": speaking.criteria, "summary": speaking.summary, "comments": speaking.comments[:4], "metrics": spoken.get("metrics"), "pronunciation_note": speaking.pronunciation_note}
    overall = overall_band(list(scores.values()), exam.exam) if exam.exam == "IELTS" else round(sum(scores.values()) / 4 * 2) / 2
    target = db.scalar(select(Profile.target_score).where(Profile.user_id == user.id))
    output = {"summary": f"{'Full-length' if exam.sections.get('length') == 'full' else 'Short-format'} mock estimate. Listening and Reading are marked against answer keys; Writing and Speaking are assessed against the rubric. Pronunciation is not scored from a transcript.",
              "section_scores": scores, "estimated_overall": overall, "readiness": "On track" if target is not None and overall >= target else "Needs further practice",
              "score_scale": "IELTS 0-9 bands" if exam.exam == "IELTS" else "TOEFL 2026 1-6 sections", "official": False,
              "details": details, "confidence": {skill: .82 for skill in scores}}
    package = runtime.verify_output(user.id, "mock_exam", output)
    exam.package_id = package.id
    exam.status = "SUBMITTED"
    if package.state == "RELEASED":
        for skill in ("listening", "reading"):
            notebook.record_objective_mistakes(db, user.id, exam.sections[skill], details[skill]["review"], skill, f"Mock #{exam.id}")
        for task, fb in details["writing"].items():
            notebook.record_feedback(db, user.id, fb, "writing", f"Mock #{exam.id} · {task}")
        notebook.record_feedback(db, user.id, details["speaking"], "speaking", f"Mock #{exam.id}")
        notebook.remember(db, user.id, "progress", f"Mock exam #{exam.id} ({exam.exam}): overall {overall}; sections {scores}", key="progress:mock", source="assessment")
    db.commit()
    view = mock_view(exam, db)
    if package.state == "RELEASED":
        view["adaptation"] = adapt_after_major_assessment(db, user)
    return view


def adapt_after_major_assessment(db: Session, user: User) -> dict | None:
    """UC7 trigger: a completed mock exam (UC5) proposes an adapted plan, unless one is already waiting for the learner.
    The mock result is already saved, so a failure here can never lose it."""
    if not db.scalar(select(Plan.id).where(Plan.user_id == user.id, Plan.status == "ACTIVE")):
        return None
    if db.scalar(select(Plan.id).where(Plan.user_id == user.id, Plan.kind == "adaptation", Plan.status.in_(("PROPOSED", "HELD")))):
        return None
    try:
        result = adaptation.propose(db, user.id, profile_data(profile_for(db, user)), latest_progress(db, user.id), "major_assessment")
        db.commit()
    except Exception:
        db.rollback()
        return None
    return {"outcome": result["outcome"], "plan_id": result["plan"].id if result["plan"] else None, "message": result["message"]}


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
        kit = Toolkit(db, "assessment", user.id, profile_for(db, user).exam)
        narrative = runtime.provider.report(data, kit).model_dump()
        kit.log("report", runtime.provider.mode)
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
    """UC10. The Learning Coordinator builds the list; UC9 checks it before release."""
    profile = profile_for(db, user)
    coordinator = AgentRuntime(db).coordinator
    package = coordinator.request_recommendations(user.id, {"exam": profile.exam, "proficiency": profile.proficiency, "priority_skills": profile.priority_skills},
                                                  latest_progress(db, user.id))
    db.commit()
    result = package_view(package)
    if package.state != "RELEASED":
        result["last_verified"] = coordinator.last_verified_list(user.id, before_id=package.id)  # 6a
    return result


@app.post("/api/materials/{material_id}/interaction")
def material_interaction(material_id: int, relevant: bool | None = None, user: User = Depends(learner), db: Session = Depends(get_db)):
    if not db.get(Material, material_id):
        raise HTTPException(404, "Material not found")
    coordinator = AgentRuntime(db).coordinator
    item = coordinator.dismiss(user.id, material_id) if relevant is False else coordinator.open_material(user.id, material_id, relevant)
    db.commit()
    return {"viewed": item.viewed, "relevant": item.relevant}


@app.get("/api/instructor/agent-memory")
def agent_memory(agent: str | None = None, user_id: int | None = None, limit: int = 100, user: User = Depends(instructor), db: Session = Depends(get_db)):
    """What each agent remembers — developer (teacher) console only."""
    query = select(AgentMemory).order_by(AgentMemory.id.desc()).limit(min(limit, 300))
    if agent:
        query = query.where(AgentMemory.agent == agent)
    if user_id:
        query = query.where(AgentMemory.user_id == user_id)
    names = {u.id: u.name for u in db.scalars(select(User))}
    return [{**dto(row, "id", "agent", "user_id", "kind", "text", "created_at"), "agent_name": agent_core.AGENT_NAMES.get(row.agent, row.agent),
             "user": names.get(row.user_id, "All learners")} for row in db.scalars(query)]


@app.get("/api/events")
def events(agent: str | None = None, workflow: str | None = None, user_id: int | None = None, slow: bool = False, limit: int = 150,
           user: User = Depends(instructor), db: Session = Depends(get_db)):
    """Agent activity trace across all learners — developer (teacher) console only."""
    query = select(AgentEvent).order_by(AgentEvent.id.desc()).limit(max(1, min(limit, 500)))
    if agent:
        query = query.where(AgentEvent.agent == agent)
    if workflow:
        query = query.where(AgentEvent.workflow == workflow)
    if user_id:
        query = query.where(AgentEvent.user_id == user_id)
    if slow:
        query = query.where(AgentEvent.duration_ms > monitoring.SLOW_MS)
    names = {u.id: u for u in db.scalars(select(User))}
    return [{**dto(event, "id", "user_id", "workflow", "agent", "phase", "detail", "mode", "duration_ms", "created_at"),
             "user": names[event.user_id].name if event.user_id in names else "", "email": names[event.user_id].email if event.user_id in names else ""} for event in db.scalars(query)]


@app.get("/api/instructor/overview")
def developer_overview(user: User = Depends(instructor), db: Session = Depends(get_db)):
    config = settings()
    return monitoring.overview(db, config.ai_mode, config.llm_model if config.ai_mode == "REAL" else "built-in engine")


@app.get("/api/instructor/anomalies")
def developer_anomalies(days: int = 7, user: User = Depends(instructor), db: Session = Depends(get_db)):
    return monitoring.anomalies(db, max(1, min(days, 90)))


@app.post("/api/instructor/anomalies/ack")
def acknowledge_anomaly(data: AnomalyAckInput, user: User = Depends(instructor), db: Session = Depends(get_db)):
    db.add(AuditLog(user_id=user.id, action="anomaly_acknowledged", detail={"anomaly_id": data.anomaly_id}))
    db.commit()
    return {"acknowledged": data.anomaly_id}


def report_view(report: IssueReport, db: Session) -> dict:
    owner = db.get(User, report.user_id)
    return {**dto(report, "id", "category", "message", "context", "status", "response", "created_at", "resolved_at"),
            "user": owner.name if owner else "", "email": owner.email if owner else ""}


@app.post("/api/feedback")
def report_issue(data: IssueReportInput, user: User = Depends(learner), db: Session = Depends(get_db)):
    context = {k: v for k, v in (data.context or {}).items() if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 2000}
    report = IssueReport(user_id=user.id, category=data.category, message=data.message.strip(), context=context, status="OPEN")
    db.add(report)
    db.add(AgentEvent(user_id=user.id, workflow="feedback", agent="Learner", phase="report", detail={"category": data.category, "next_agent": "Human Instructor"}, mode=settings().ai_mode))
    db.commit()
    return report_view(report, db)


@app.get("/api/feedback")
def my_reports(user: User = Depends(learner), db: Session = Depends(get_db)):
    return [report_view(r, db) for r in db.scalars(select(IssueReport).where(IssueReport.user_id == user.id).order_by(IssueReport.id.desc()))]


@app.get("/api/instructor/feedback")
def all_reports(status: str | None = None, user: User = Depends(instructor), db: Session = Depends(get_db)):
    query = select(IssueReport).order_by(IssueReport.status.desc(), IssueReport.id.desc())
    if status:
        query = query.where(IssueReport.status == status)
    return [report_view(r, db) for r in db.scalars(query)]


@app.post("/api/instructor/feedback/{report_id}/resolve")
def resolve_report(report_id: int, data: IssueResolveInput, user: User = Depends(instructor), db: Session = Depends(get_db)):
    report = db.get(IssueReport, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    report.status, report.response, report.resolved_by, report.resolved_at = "RESOLVED", data.response.strip(), user.id, datetime.now(timezone.utc)
    db.add(AuditLog(user_id=user.id, action="learner_report_resolved", detail={"report_id": report.id}))
    db.commit()
    return report_view(report, db)


@app.get("/api/instructor/cases")
def cases(user: User = Depends(instructor), db: Session = Depends(get_db)):
    rows = db.scalars(select(Escalation).order_by(Escalation.id.desc())).all()
    return [{**dto(case, "id", "status", "reason", "created_at"), "package": package_view(db.get(ResultPackage, case.package_id), True), "decisions": [dto(dec, "decision", "note", "correction", "created_at") for dec in db.scalars(select(InstructorDecision).where(InstructorDecision.case_id == case.id))]} for case in rows]


@app.post("/api/instructor/cases/{case_id}/decision")
def decide_case(case_id: int, data: ReviewInput, user: User = Depends(instructor), db: Session = Depends(get_db)):
    case = db.get(Escalation, case_id)
    if case and case.status == escalation.QUEUED:
        raise HTTPException(409, "Case is queued until an instructor is available; mark yourself available first")
    if not case or case.status not in escalation.OPEN:
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
    undelivered: list[str] = []
    if data.decision == "request_information":
        case.status = "MORE_INFO"
        package.state = "HUMAN_REVIEW"
        escalation.notify_agents(db, case, package, data.decision, data.note, only=["quality"])
        escalation.gather_evidence(db, case, package, user.id)  # 5c: the requested information comes back and the case returns for review
        db.add(AgentEvent(user_id=package.user_id, workflow=package.kind, agent="Quality Manager", phase="state", detail={"package_id": package.id, "state": "HUMAN_REVIEW"}, mode=package.source_mode))
    else:
        package.state = "APPROVED" if data.decision == "approve" else "CORRECTED"
        db.add(AgentEvent(user_id=package.user_id, workflow=package.kind, agent="Quality Manager", phase="state", detail={"package_id": package.id, "state": package.state}, mode=package.source_mode))
        db.add(QualityCheck(package_id=package.id, verdict="HUMAN_APPROVED", issues=[], threshold=AgentRuntime(db).threshold(), method="HUMAN"))
        AgentRuntime(db).release_after_human(package)
        if package.kind in ("writing", "speaking"):
            notebook.record_feedback(db, package.user_id, package.payload, package.kind, "Instructor-reviewed result")
        case.status = "RESOLVED"  # 7a: stays resolved even if an agent cannot be told right away
        escalation.log(db, user.id, "case_resolved", case.id, decision=data.decision)
        undelivered = escalation.notify_agents(db, case, package, data.decision, data.note)
        for plan in db.scalars(select(Plan).where(Plan.package_id == package.id)):
            plan.content = package.payload
            plan.status = "PROPOSED"
    db.commit()
    return {"status": case.status, "package": package_view(package, True), "notifications_pending": undelivered}


@app.get("/api/instructor/cases/{case_id}")
def case_detail(case_id: int, user: User = Depends(instructor), db: Session = Depends(get_db)):
    """UC8 steps 3-4: the held result with the learner's earlier results, previous decisions, highlights and the case history."""
    case = db.get(Escalation, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return {**dto(case, "id", "status", "reason", "created_at"), "package": package_view(db.get(ResultPackage, case.package_id), True), **escalation.case_detail(db, case)}


@app.post("/api/instructor/cases/{case_id}/request-evidence")
def request_case_evidence(case_id: int, user: User = Depends(instructor), db: Session = Depends(get_db)):
    """UC8 3a: the case stays open while the Quality Manager gathers the missing evidence."""
    case = db.get(Escalation, case_id)
    if not case or case.status not in escalation.OPEN:
        raise HTTPException(409, "Case is not open for review")
    escalation.gather_evidence(db, case, db.get(ResultPackage, case.package_id), user.id)
    db.commit()
    return case_detail(case_id, user, db)


@app.post("/api/instructor/cases/{case_id}/retry-notifications")
def retry_case_notifications(case_id: int, user: User = Depends(instructor), db: Session = Depends(get_db)):
    """UC8 7a: re-deliver the outcome to any agent that has not received it."""
    case = db.get(Escalation, case_id)
    if not case or case.status != "RESOLVED":
        raise HTTPException(409, "Only a resolved case has an outcome to deliver")
    delivered = escalation.retry_notifications(db, case)
    db.commit()
    return {"delivered": delivered, "notifications_pending": escalation.pending_agents(db, case.id)}


@app.get("/api/instructor/availability")
def instructor_availability(user: User = Depends(instructor), db: Session = Depends(get_db)):
    return {"available": escalation.is_available(db, user.id), "queued": db.scalar(select(func.count()).select_from(Escalation).where(Escalation.status == escalation.QUEUED)),
            "notifications": escalation.notifications(db, user.id)}


@app.put("/api/instructor/availability")
def set_instructor_availability(data: AvailabilityInput, user: User = Depends(instructor), db: Session = Depends(get_db)):
    """UC8 2a: becoming available releases the queued cases to this instructor."""
    released = escalation.set_available(db, user, data.available)
    db.add(AuditLog(user_id=user.id, action="instructor_available" if data.available else "instructor_away", detail={"released": released}))
    db.commit()
    return {"available": data.available, "released": released}


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
