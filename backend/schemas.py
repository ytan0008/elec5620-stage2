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


class RegisterInput(ProfileInput):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class SubmitInput(BaseModel):
    text: str = Field(min_length=8, max_length=20000)
    scenario: Literal["normal", "low_confidence", "contradiction", "invalid"] = "normal"


class ExamAnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=20000)


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
