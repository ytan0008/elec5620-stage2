from sqlalchemy import select
from backend.db import SessionLocal
from backend.models import User, Material
from backend.auth import hash_password
from backend.config import settings

MATERIALS = [
    ("IELTS Task 2 argument structure", "IELTS", "writing", "intermediate", "Plan a clear claim, reason and example for each paragraph.", "Write an introduction with a position. In each body paragraph, use a topic sentence, supporting reason, specific example and a link back to the question."),
    ("IELTS speaking cue-card rehearsal", "IELTS", "speaking", "intermediate", "Practise organised two-minute answers.", "Spend one minute making four bullet points: person, place, event and why it matters. Speak for two minutes and compare your recording with the outline."),
    ("IELTS reading evidence scan", "IELTS", "reading", "beginner", "Locate evidence before choosing an answer.", "Read the question first. Underline key nouns, scan for synonyms, then verify the whole sentence before answering."),
    ("IELTS listening signposts", "IELTS", "listening", "intermediate", "Recognise corrections and transitions in spoken passages.", "Listen for however, actually and instead. Record the corrected fact rather than the first fact you heard."),
    ("TOEFL academic discussion response", "TOEFL", "writing", "intermediate", "Support a concise discussion contribution.", "State your view, connect it to a classmate's idea, and add one original concrete example. Revise for precision and clarity."),
    ("TOEFL speaking delivery", "TOEFL", "speaking", "intermediate", "Build a concise answer with examples.", "Use a short claim, two reasons and a conclusion. Record and check pacing, pauses and completeness."),
    ("TOEFL reading inference", "TOEFL", "reading", "advanced", "Separate stated evidence from inference.", "Identify the sentence that supports an inference. Eliminate choices that add unsupported facts."),
    ("TOEFL listening lecture notes", "TOEFL", "listening", "intermediate", "Capture lecture structure in notes.", "Write the main idea and one example per section. Compare details with the lecture's signposts."),
]


def seed():
    with SessionLocal.begin() as db:
        if not db.scalar(select(User).where(User.email == settings().instructor_email)):
            db.add(User(email=settings().instructor_email, name="Demo Instructor", role="instructor", password_hash=hash_password(settings().instructor_password)))
        if not db.scalar(select(Material.id)):
            db.add_all(Material(title=t, exam=e, skill=s, level=l, description=d, content=c) for t,e,s,l,d,c in MATERIALS)


if __name__ == "__main__":
    seed()
    print("Database seeded")
