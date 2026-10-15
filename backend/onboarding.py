"""Guided profile interview and deterministic, labelled demo extraction."""
import re
from datetime import date

FIELDS = ("exam", "proficiency", "target_score", "exam_date", "weekly_hours", "priority_skills")
QUESTIONS = {
    "exam": "Which exam are you preparing for: IELTS or TOEFL?",
    "proficiency": "How would you describe your current English level: beginner, intermediate or advanced?",
    "target_score": "What target band or score would you like to reach? For example, IELTS 7.0.",
    "exam_date": "When is your target test date? Please use YYYY-MM-DD.",
    "weekly_hours": "How many hours can you study each week? Choose a number from 1 to 40.",
    "priority_skills": "Which skills need the most attention: writing, speaking, reading or listening? You can name several.",
}


def next_field(draft: dict) -> str | None:
    return next((field for field in FIELDS if not draft.get(field)), None)


def parse_demo_message(message: str, draft: dict) -> dict:
    """Only extracts facts clearly present in the learner's latest message."""
    lower = message.lower()
    found = {}
    for exam in ("IELTS", "TOEFL"):
        if re.search(rf"\b{exam.lower()}\b", lower):
            found["exam"] = exam
            break
    for level in ("beginner", "intermediate", "advanced"):
        if re.search(rf"\b{level}\b", lower):
            found["proficiency"] = level
            break
    match = re.search(r"\b(?:target|band|score)\s*(?:of|is|:)?\s*(\d(?:\.\d)?)\b", lower)
    if match:
        found["target_score"] = float(match.group(1))
    elif next_field(draft) == "target_score" and re.fullmatch(r"\s*\d(?:\.\d)?\s*", message):
        found["target_score"] = float(message)
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message)
    if match:
        found["exam_date"] = match.group(1)
    match = re.search(r"\b(\d{1,2})\s*(?:hours?|hrs?)\b", lower)
    if match:
        found["weekly_hours"] = int(match.group(1))
    elif next_field(draft) == "weekly_hours" and re.fullmatch(r"\s*\d{1,2}\s*", message):
        found["weekly_hours"] = int(message)
    skills = [skill for skill in ("writing", "speaking", "reading", "listening") if re.search(rf"\b{skill}\b", lower)]
    if "all four" in lower or "all skills" in lower:
        skills = ["writing", "speaking", "reading", "listening"]
    if skills:
        found["priority_skills"] = skills
    return found


def clean_extraction(values: dict, draft: dict) -> tuple[dict, list[str]]:
    updated = dict(draft)
    errors = []
    for field in FIELDS:
        value = values.get(field)
        if value is None:
            continue
        try:
            if field == "exam" and value not in ("IELTS", "TOEFL"):
                raise ValueError("Choose IELTS or TOEFL")
            if field == "proficiency" and value not in ("beginner", "intermediate", "advanced"):
                raise ValueError("Choose beginner, intermediate or advanced")
            if field == "target_score":
                value = float(value)
                exam = updated.get("exam") or values.get("exam")
                low, high = (0, 9) if exam == "IELTS" else (1, 6)
                if exam and (not low <= value <= high or value * 2 != int(value * 2)):
                    raise ValueError(f"{exam} targets use half-point steps from {low} to {high}")
            if field == "exam_date":
                value = date.fromisoformat(str(value)).isoformat()
                if date.fromisoformat(value) < date.today():
                    raise ValueError("Choose a future test date")
            if field == "weekly_hours":
                value = int(value)
                if not 1 <= value <= 40:
                    raise ValueError("Study hours must be from 1 to 40")
            if field == "priority_skills":
                value = list(dict.fromkeys(value))
                if not value or any(skill not in ("writing", "speaking", "reading", "listening") for skill in value):
                    raise ValueError("Choose at least one of the four skills")
            updated[field] = value
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    return updated, errors
