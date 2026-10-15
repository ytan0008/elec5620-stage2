"""Structured practice content catalogue (IELTS and TOEFL 2026 formats)."""
import random
from backend.content import ielts_listening, ielts_reading, ielts_production, toefl

LISTENING = {item["id"]: item for item in ielts_listening.PARTS + toefl.LISTENING}
READING = {item["id"]: item for item in ielts_reading.PASSAGES + toefl.READING}
WRITING = {item["id"]: item for item in ielts_production.WRITING + toefl.WRITING}
SPEAKING = {item["id"]: item for item in ielts_production.SPEAKING_TESTS + toefl.SPEAKING}
ALL = {**LISTENING, **READING, **WRITING, **SPEAKING}

TASK_LABELS = {
    ("IELTS", "listening"): lambda item: f"Listening Part {item['part']}",
    ("IELTS", "reading"): lambda item: f"Academic Reading Passage {item['part']}",
    ("IELTS", "writing"): lambda item: "Academic Writing Task 1" if item["task"] == "task1" else "Writing Task 2",
    ("IELTS", "speaking"): lambda item: "Full Speaking test (Parts 1-3)",
    ("TOEFL", "listening"): lambda item: item["title"].split(":")[0],
    ("TOEFL", "reading"): lambda item: item["title"].split(":")[0],
    ("TOEFL", "writing"): lambda item: {"email": "Write an Email", "discussion": "Academic Discussion"}[item["task"]],
    ("TOEFL", "speaking"): lambda item: "Listen and Repeat + Interview",
}


def task_type(item: dict) -> str:
    return TASK_LABELS[(item["exam"], item["kind"])](item)


def summary(item: dict) -> str:
    """Short, answer-free description used in the question bank list."""
    if item["kind"] == "writing":
        return item["prompt"]
    if item["kind"] == "speaking":
        if item["exam"] == "IELTS":
            return f"Part 1: {item['part1'][0]['topic']} and {item['part1'][1]['topic']}. Part 2: {item['part2']['cue']} Part 3: {item['part3']['theme']}."
        return f"Repeat {len(item['repeat'])} campus sentences, then answer {len(item['interview']['questions'])} interview questions. {item['interview']['scenario']}"
    count = sum(len(group["questions"]) for group in item["groups"])
    kinds = ", ".join(dict.fromkeys(group["type"].upper() if group["type"] in ("tfng", "ynng", "mcq") else group["type"] for group in item["groups"]))
    return f"{item.get('context') or item['title']} {count} questions ({kinds})."


def catalogue_rows():
    for item in ALL.values():
        yield {"exam": item["exam"], "skill": item["kind"], "task_type": task_type(item), "title": item["title"], "prompt": summary(item),
               "topic": item.get("topic", "general"), "content": item}


def wrap(skill: str, sections: list[dict]) -> dict:
    """A practice/mock test is always a list of sections for listening and reading."""
    title = sections[0]["title"] if len(sections) == 1 else f"{sections[0]['exam']} {skill} test ({len(sections)} parts)"
    return {"kind": skill, "exam": sections[0]["exam"], "title": title, "sections": sections,
            "minutes": sum(section.get("minutes", 10) for section in sections) if skill == "reading" else None}


def pick(exam: str, skill: str, avoid: set[str] | None = None, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    pool = {"listening": LISTENING, "reading": READING, "writing": WRITING, "speaking": SPEAKING}[skill]
    items = [item for item in pool.values() if item["exam"] == exam]
    fresh = [item for item in items if item["id"] not in (avoid or set())] or items
    return rng.choice(fresh)


def mock_sections(exam: str, length: str, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    if exam == "IELTS":
        listening = [LISTENING[i] for i in ielts_listening.FULL_TEST] if length == "full" else [LISTENING["ielts-listening-1a"], LISTENING["ielts-listening-2a"]]
        reading = [READING[i] for i in ielts_reading.FULL_TEST] if length == "full" else [READING[rng.choice(ielts_reading.FULL_TEST)]]
        task1 = rng.choice([w for w in ielts_production.WRITING if w["task"] == "task1"])
        task2 = rng.choice([w for w in ielts_production.WRITING if w["task"] == "task2"])
        writing = [task1, task2] if length == "full" else [task2]
        speaking = rng.choice(ielts_production.SPEAKING_TESTS)
        minutes = {"listening": 32 if length == "full" else 16, "reading": 60 if length == "full" else 20, "writing": 60 if length == "full" else 40, "speaking": 14}
    else:
        listening = toefl.LISTENING
        reading = toefl.READING
        writing = toefl.WRITING
        speaking = toefl.SPEAKING[0]
        minutes = {"listening": 18, "reading": 18, "writing": 20, "speaking": 8}
    return {
        "listening": {**wrap("listening", listening), "duration_seconds": minutes["listening"] * 60},
        "reading": {**wrap("reading", reading), "duration_seconds": minutes["reading"] * 60},
        "writing": {"kind": "writing", "exam": exam, "title": f"{exam} Writing", "tasks": writing, "duration_seconds": minutes["writing"] * 60},
        "speaking": {"kind": "speaking", "exam": exam, "title": f"{exam} Speaking", "test": speaking, "duration_seconds": minutes["speaking"] * 60},
    }
