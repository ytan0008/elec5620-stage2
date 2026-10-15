from datetime import date
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

Skill = Literal["writing", "speaking", "reading", "listening"]


class ProfileInput(BaseModel):
    exam: Literal["IELTS", "TOEFL"]
    proficiency: Literal["beginner", "intermediate", "advanced"]
    target_score: float
    exam_date: date
    weekly_hours: int = Field(ge=1, le=40)
    priority_skills: list[Skill] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_score(self):
        low, high = (0, 9) if self.exam == "IELTS" else (1, 6)
        if not low <= self.target_score <= high or self.target_score * 2 != int(self.target_score * 2):
            raise ValueError(f"{self.exam} target must be a half-point increment from {low} to {high}")
        return self


class RegisterInput(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    exam: Literal["IELTS", "TOEFL"] | None = None
    proficiency: Literal["beginner", "intermediate", "advanced"] | None = None
    target_score: float | None = None
    exam_date: date | None = None
    weekly_hours: int | None = Field(default=None, ge=1, le=40)
    priority_skills: list[Skill] | None = None

    @model_validator(mode="after")
    def optional_profile(self):
        values = [self.exam, self.proficiency, self.target_score, self.exam_date, self.weekly_hours, self.priority_skills]
        if any(value is not None for value in values):
            if not all(value is not None for value in values):
                raise ValueError("Complete all profile fields or set them after sign-up")
            ProfileInput.model_validate(self.model_dump(exclude={"email", "name", "password"}))
        return self


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class SubmitInput(BaseModel):
    text: str = Field(default="", max_length=20000)
    answers: dict[str, str] | None = None
    task: str | None = None
    metrics: dict[str, float] | None = None
    # Quality-gate test hooks; honoured only by the local engine and never shown in the UI.
    scenario: Literal["normal", "low_confidence", "contradiction", "invalid"] = "normal"

    @model_validator(mode="after")
    def has_response(self):
        if self.answers is None and len(self.text.strip()) < 8:
            raise ValueError("Write at least a short response before submitting")
        return self


class ExamAnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=40000)


class MockCreateInput(BaseModel):
    length: Literal["full", "short"] = "short"


class ReviewInput(BaseModel):
    decision: Literal["approve", "correct", "request_information"]
    note: str = Field(min_length=3, max_length=2000)
    correction: dict | None = None


class FeedbackOutput(BaseModel):
    summary: str = Field(min_length=10)
    criteria: dict[str, float]
    comments: list[dict]
    improvements: list[str]
    confidence: dict[str, float]
    pronunciation_available: bool = False
    pronunciation_note: str | None = None
    improved_sentences: list[dict] = []
    model_answer: str | None = None
    analysis: dict = {}

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, values):
        if not values or any(not 0 <= value <= 1 for value in values.values()):
            raise ValueError("Each confidence must be in [0,1]")
        return values


class PlanOutput(BaseModel):
    title: str = Field(min_length=5)
    rationale: str = Field(min_length=10)
    priorities: list[Skill] = Field(min_length=1)
    activities: list[dict] = Field(min_length=1)
    changes: list[str] = []
    confidence: dict[str, float]


class VerdictOutput(BaseModel):
    consistent: bool
    reason: str
    confidence: float = Field(ge=0, le=1)


class RecommendationOutput(BaseModel):
    summary: str = Field(min_length=5)
    items: list[dict] = Field(min_length=1)
    confidence: dict[str, float]


class ReportNarrative(BaseModel):
    summary: str = Field(min_length=10)
    recommendations: list[str] = Field(min_length=1)
    confidence: dict[str, float]


class ThresholdInput(BaseModel):
    value: float = Field(ge=0.5, le=0.95)


class ChangeRequestInput(BaseModel):
    note: str = Field(min_length=5, max_length=1000)


class OnboardingTurn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


Persona = Literal["witch", "boy"]


class AgentChatTurn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    persona: Persona = "witch"


class AgentChatReply(BaseModel):
    reply: str = Field(min_length=2, max_length=2000)
    # Durable facts about the learner worth remembering (filled by the cloud model).
    remember: list[str] = []


class AvatarInput(BaseModel):
    avatar: Persona


class SpeakingStartInput(BaseModel):
    question_id: int | None = None
    mock_id: int | None = None
    persona: Persona = "witch"


class SpeakingTurnInput(BaseModel):
    text: str = Field(default="", max_length=8000)
    seconds: float = Field(default=0, ge=0, le=900)
    event: Literal["answer", "ready"] = "answer"


class TTSInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str = Field(default="female", max_length=20)
    speed: float = Field(default=1.0, ge=0.5, le=1.5)


class ExaminerTurn(BaseModel):
    say: str = Field(min_length=2, max_length=900)
    follow_up: bool = False


class OnboardingExtraction(BaseModel):
    exam: Literal["IELTS", "TOEFL"] | None = None
    proficiency: Literal["beginner", "intermediate", "advanced"] | None = None
    target_score: float | None = None
    exam_date: str | None = None
    weekly_hours: int | None = None
    priority_skills: list[Skill] | None = None


class PortraitOutput(BaseModel):
    summary: str = Field(min_length=15)
    goal: str = Field(min_length=5)
    focus_areas: list[Skill] = Field(min_length=1)
    starting_point: str = Field(min_length=5)
    study_rhythm: str = Field(min_length=5)
    next_steps: list[str] = Field(min_length=1)
    confidence: dict[str, float]


class QuestionGenerationInput(BaseModel):
    skill: Skill
    topic: str = Field(min_length=3, max_length=80)
    task: Literal["task1", "task2", "part1", "part2", "part3", "part4", "email", "discussion", "auto"] = "auto"


class GenLine(BaseModel):
    speaker: str = Field(min_length=1, max_length=40)
    voice: Literal["narrator", "female", "male", "female2", "male2"]
    text: str = Field(min_length=2, max_length=1200)


class GenOption(BaseModel):
    key: str = Field(min_length=1, max_length=6)
    text: str = Field(min_length=1, max_length=300)


class GenQuestion(BaseModel):
    n: int
    prompt: str = Field(min_length=1, max_length=400)
    options: list[GenOption] = []
    answer: str = Field(min_length=1, max_length=80)
    accepts: list[str] = []
    evidence: str = Field(default="", max_length=400)


class GenGroup(BaseModel):
    title: str
    type: Literal["completion", "mcq", "matching", "tfng", "ynng"]
    instructions: str
    heading: str | None = None
    options: list[GenOption] = []
    questions: list[GenQuestion] = Field(min_length=1)


class GenParagraph(BaseModel):
    label: str = ""
    text: str = Field(min_length=20)


class ListeningGen(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    context: str = Field(min_length=5, max_length=300)
    script: list[GenLine] = Field(min_length=4)
    groups: list[GenGroup] = Field(min_length=1)
    confidence: dict[str, float]


class ReadingGen(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    passage: list[GenParagraph] = Field(min_length=3)
    groups: list[GenGroup] = Field(min_length=1)
    confidence: dict[str, float]


class SpeakingGen(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    cue: str = Field(min_length=10, max_length=200)
    bullets: list[str] = Field(min_length=3, max_length=4)
    closing: str = Field(min_length=5, max_length=200)
    part3_theme: str = Field(min_length=3, max_length=80)
    part3_questions: list[str] = Field(min_length=3, max_length=5)
    confidence: dict[str, float]


class QuestionOutput(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    prompt: str = Field(min_length=30)
    task_type: str = Field(min_length=5)
    confidence: dict[str, float]


NotebookKind = Literal["mistake", "word", "grammar", "sentence"]


class NotebookAddInput(BaseModel):
    kind: NotebookKind
    text: str = Field(min_length=1, max_length=4000)
    context: str | None = Field(default=None, max_length=1200)
    skill: str = Field(default="", max_length=20)
    source: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    correction: str | None = Field(default=None, max_length=2000)
    language: str = Field(default="Chinese (Simplified)", max_length=40)


class NotebookUpdateInput(BaseModel):
    mastered: bool | None = None
    note: str | None = Field(default=None, max_length=2000)
    translation: str | None = Field(default=None, max_length=400)


class NotebookReviewInput(BaseModel):
    remembered: bool


class NotebookRetryInput(BaseModel):
    answer: str = Field(min_length=1, max_length=200)


class MemoryInput(BaseModel):
    kind: Literal["about", "goal", "preference", "difficulty", "progress", "note"] = "note"
    text: str = Field(min_length=2, max_length=500)


class WordInfo(BaseModel):
    phonetic: str = ""
    part_of_speech: str = ""
    definition: str = Field(min_length=2, max_length=400)
    translation: str = Field(default="", max_length=200)
    example: str = Field(default="", max_length=300)
    synonyms: list[str] = []
    collocations: list[str] = []


class CoachOutput(BaseModel):
    message: str = Field(min_length=10, max_length=2500)
