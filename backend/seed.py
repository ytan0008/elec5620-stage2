from sqlalchemy import select, delete
from backend.db import SessionLocal
from backend.models import User, Material, QuestionItem
from backend.questions import QUESTIONS
from backend.auth import hash_password
from backend.config import settings
from backend import content

MATERIALS = [
    ("IELTS Task 2 argument structure", "IELTS", "writing", "intermediate", "Plan a clear claim, reason and example for each paragraph.",
     "Introduction: paraphrase the question in one sentence, then give a clear position ('I strongly believe that...').\n\nBody paragraph: topic sentence -> explanation (why?) -> specific example (who, where, numbers) -> link back to the question.\n\nConclusion: restate your position in new words and summarise both main reasons. Never add a new idea.\n\nTime plan: 5 minutes planning, 30 minutes writing, 5 minutes checking articles, plurals and verb tenses."),
    ("IELTS Task 1 overview first", "IELTS", "writing", "intermediate", "Report charts with a clear overview and grouped comparisons.",
     "Sentence 1 paraphrases the chart: 'The bar chart compares...'.\n\nSentence 2-3 is the overview: two big features without numbers, e.g. 'Overall, car use fell while train and bicycle commuting rose.'\n\nBody 1 and 2 group related data and compare it with exact figures: 'rose from 25% to 35%', 'twice as many', 'by contrast'.\n\nUseful verbs: rise, climb, surge, fall, decline, dip, fluctuate, remain stable, peak at, bottom out at."),
    ("IELTS speaking cue-card rehearsal", "IELTS", "speaking", "intermediate", "Practise organised two-minute answers.",
     "Use the minute to write four keywords, one per bullet. Start with a short scene-setter ('I'd like to talk about...'), tell the story in past tenses, describe feelings, and finish with why it still matters.\n\nIf you run out of ideas: compare then and now, describe a detail with the five senses, or explain what you learned.\n\nRecord yourself with the AI examiner and check whether you reached the full two minutes."),
    ("IELTS speaking Part 3 idea builder", "IELTS", "speaking", "advanced", "Extend abstract answers with the O-R-E-C pattern.",
     "Opinion -> Reason -> Example -> Contrast. 'I'd say that... mainly because... For instance, in my city... That said, for older people it might be different.'\n\nUse hedging for abstract questions: 'It depends on...', 'To some extent...', 'Generally speaking...'. Speculate about the future with 'is likely to', 'might well', 'I'd imagine'."),
    ("IELTS reading evidence scan", "IELTS", "reading", "beginner", "Locate evidence before choosing an answer.",
     "Read the question first and underline key nouns, names and numbers. Scan the passage for those words or their synonyms, then read the whole sentence around them.\n\nTRUE/FALSE/NOT GIVEN: FALSE needs a direct contradiction; NOT GIVEN means the passage is silent. Completion answers must be copied exactly from the passage and respect the word limit."),
    ("IELTS reading: matching headings", "IELTS", "reading", "intermediate", "Choose headings by main idea, not by matching words.",
     "Read the first two and the last sentence of each paragraph and write a five-word summary in the margin. Then compare your summary with the headings.\n\nBeware of headings that repeat a word from the paragraph but describe only one detail. Do the easiest paragraphs first and cross out used headings."),
    ("IELTS listening signposts", "IELTS", "listening", "intermediate", "Recognise corrections and transitions in spoken passages.",
     "Speakers often give a wrong detail first and then correct it: 'It's at seven... oh no, sorry, seven fifteen.' Write the corrected fact.\n\nSignposts announce the next answer: 'Moving on to...', 'The main problem was...', 'Finally...'. Use the pause before each part to predict the word type of every gap."),
    ("IELTS listening: spelling and numbers", "IELTS", "listening", "beginner", "Never lose marks on names, dates and numbers.",
     "Practise the alphabet aloud, especially A/E/I, G/J and doubles ('double s'). Phone numbers are read in groups and '0' is often said 'oh'.\n\nDates can be written '14 June' or 'June 14th'. Check plurals: if the gap says 'two ___', the answer needs an -s."),
    ("TOEFL academic discussion response", "TOEFL", "writing", "intermediate", "Support a concise discussion contribution.",
     "State your view in the first sentence, react to one classmate by name ('Unlike Amara, I think...'), add a new reason that nobody mentioned and a concrete example. 100-120 words is enough; finish with a one-line conclusion."),
    ("TOEFL write an email", "TOEFL", "writing", "beginner", "Cover all three bullet points with the right tone.",
     "Greeting -> purpose in one sentence -> one short paragraph per bullet point -> polite closing. Match the tone to the reader: friendly for a classmate, polite for a professor or manager. Use clear request forms such as 'Would it be possible to...?'"),
    ("TOEFL speaking: listen and repeat", "TOEFL", "speaking", "intermediate", "Hold the sentence in memory and repeat it exactly.",
     "Listen for the sentence's meaning, not individual words; meaning chunks are easier to remember. Repeat with the same rhythm and stress. Don't add or drop articles, and keep plural endings."),
    ("TOEFL speaking: take an interview", "TOEFL", "speaking", "intermediate", "Give organised 45-second answers.",
     "Answer the question in the first sentence, give two reasons or a reason plus an example, and wrap up. Use natural connectors ('The main reason is...', 'On top of that...'). Keep talking until the time is nearly up."),
    ("TOEFL reading inference", "TOEFL", "reading", "advanced", "Separate stated evidence from inference.",
     "Identify the sentence that supports an inference. Eliminate choices that add unsupported facts or extreme words such as 'always' and 'never'. For Complete the Words, use grammar (part of speech) and the sentence's meaning to finish each word."),
    ("TOEFL listening lecture notes", "TOEFL", "listening", "intermediate", "Capture lecture structure in notes.",
     "Write the main topic, then one line per point with examples. Note when the professor gives an opinion or says something is 'puzzling' or 'surprising'; those parts are often tested."),
]


def seed():
    with SessionLocal.begin() as db:
        if not db.scalar(select(User).where(User.email == settings().instructor_email)):
            db.add(User(email=settings().instructor_email, name="Instructor", role="instructor", avatar="witch", password_hash=hash_password(settings().instructor_password)))
        existing_materials = set(db.scalars(select(Material.title)).all())
        db.add_all(Material(title=t, exam=e, skill=s, level=l, description=d, content=c) for t, e, s, l, d, c in MATERIALS if t not in existing_materials)
        # Older releases stored text-only practice items; the structured catalogue replaces them.
        db.execute(delete(QuestionItem).where(QuestionItem.user_id.is_(None), QuestionItem.source_kind == "ORIGINAL", QuestionItem.content.is_(None)))
        existing = set(db.scalars(select(QuestionItem.title).where(QuestionItem.user_id.is_(None))).all())
        db.add_all(QuestionItem(exam=e, skill=s, task_type=task, title=title, prompt=prompt, answer_key=key, topic=topic, source_kind=kind, source_url=url)
                   for e, s, task, title, prompt, key, topic, kind, url in QUESTIONS if title not in existing)
        for row in content.catalogue_rows():
            current = db.scalar(select(QuestionItem).where(QuestionItem.user_id.is_(None), QuestionItem.title == row["title"], QuestionItem.exam == row["exam"]))
            if current:
                current.content, current.prompt, current.task_type = row["content"], row["prompt"], row["task_type"]
            else:
                db.add(QuestionItem(exam=row["exam"], skill=row["skill"], task_type=row["task_type"], title=row["title"], prompt=row["prompt"], answer_key=None,
                                    topic=row["topic"], source_kind="ORIGINAL", source_url=None, content=row["content"]))


if __name__ == "__main__":
    seed()
    print("Database seeded")
