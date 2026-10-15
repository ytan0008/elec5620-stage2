from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Boolean, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="learner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Profile(Base):
    __tablename__ = "learner_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    exam: Mapped[str] = mapped_column(String(10))
    proficiency: Mapped[str] = mapped_column(String(30))
    target_score: Mapped[float] = mapped_column(Float)
    exam_date: Mapped[str] = mapped_column(String(10))
    weekly_hours: Mapped[int] = mapped_column(Integer)
    priority_skills: Mapped[list] = mapped_column(JSON, default=list)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)


class Plan(Base):
    __tablename__ = "learning_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="initial")
    status: Mapped[str] = mapped_column(String(20), default="PROPOSED")
    content: Mapped[dict] = mapped_column(JSON)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("result_packages.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StudyTask(Base):
    __tablename__ = "study_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("learning_plans.id"))
    skill: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    complete: Mapped[bool] = mapped_column(Boolean, default=False)


class Practice(Base):
    __tablename__ = "practice_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    skill: Mapped[str] = mapped_column(String(20))
    exam: Mapped[str] = mapped_column(String(10))
    prompt: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    practice_id: Mapped[int] = mapped_column(ForeignKey("practice_sessions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("result_packages.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MockExam(Base):
    __tablename__ = "mock_examinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exam: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="IN_PROGRESS")
    sections: Mapped[dict] = mapped_column(JSON)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("result_packages.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExamResponse(Base):
    __tablename__ = "examination_responses"
    __table_args__ = (UniqueConstraint("exam_id", "skill"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("mock_examinations.id"))
    skill: Mapped[str] = mapped_column(String(20))
    answer: Mapped[str] = mapped_column(Text)


class ResultPackage(Base):
    __tablename__ = "result_packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(20), default="SUBMITTED")
    payload: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[dict] = mapped_column(JSON)
    source_mode: Mapped[str] = mapped_column(String(10))
    issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class QualityCheck(Base):
    __tablename__ = "quality_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("result_packages.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(20))
    issues: Mapped[list] = mapped_column(JSON)
    threshold: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Escalation(Base):
    __tablename__ = "escalation_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("result_packages.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InstructorDecision(Base):
    __tablename__ = "instructor_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("escalation_cases.id"))
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)
    correction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    exam: Mapped[str] = mapped_column(String(10))
    skill: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)


class MaterialInteraction(Base):
    __tablename__ = "material_interactions"
    __table_args__ = (UniqueConstraint("user_id", "material_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class PerformanceReport(Base):
    __tablename__ = "performance_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    package_id: Mapped[int] = mapped_column(ForeignKey("result_packages.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentEvent(Base):
    __tablename__ = "agent_execution_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workflow: Mapped[str] = mapped_column(String(40))
    agent: Mapped[str] = mapped_column(String(40))
    phase: Mapped[str] = mapped_column(String(25))
    detail: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(10))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
