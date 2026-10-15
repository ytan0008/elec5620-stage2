"""Learner notebooks and tutor memory.

Four notebooks share one table:
  mistake  - wrong listening/reading answers, grouped by question type
  word     - words the learner did not know (from any page, the tutor or a selection)
  grammar  - grammar/usage errors found in the learner's writing and speech
  sentence - advanced sentences worth imitating (rewrites, model answers, selections)
Entries with the same normalised key are merged and their count increases, so the
notebooks show what goes wrong most often. Words and mistakes use spaced repetition.
"""
import gzip
import json
import re
from datetime import datetime, timedelta, timezone
import httpx
from functools import lru_cache
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import LearnerMemory, NotebookEntry
from backend.scoring import is_correct

KINDS = ("mistake", "word", "grammar", "sentence")
INTERVALS = [0, 1, 3, 7, 14, 30]  # days until the next review for each level
TYPE_LABELS = {"completion": "Completion / gap fill", "mcq": "Multiple choice", "matching": "Matching", "tfng": "True / False / Not Given",
               "ynng": "Yes / No / Not Given", "cwords": "Complete the Words"}
PATTERNS = [
    ("Relative clause", r"\b(which|who|whose|whom)\b"), ("Concession", r"\b(although|even though|whereas|despite|in spite of|while)\b"),
    ("Conditional", r"\b(if|unless|provided that|were .+ to)\b"), ("Passive voice", r"\b(is|are|was|were|been|be)\s+\w+(ed|en)\b"),
    ("Cleft sentence", r"^\s*(it is|it was|what)\b.+\b(that|is|was)\b"), ("Inversion", r"^\s*(not only|rarely|seldom|never|only when|no sooner|hardly)\b"),
    ("Participle clause", r"^\s*\w+(ing|ed),"), ("Comparative structure", r"\bthe (more|less|\w+er)\b.+,\s*the (more|less|\w+er)\b"),
    ("Cause and effect", r"\b(as a result|consequently|therefore|thus|leading to|resulting in)\b"), ("Hedging", r"\b(arguably|to some extent|it could be argued|tends? to|is likely to)\b"),
]


def now() -> datetime:
    return datetime.now(timezone.utc)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s'-]", "", (text or "").lower())).strip()[:300]


def sentence_patterns(sentence: str) -> list[str]:
    lower = sentence.lower()
    return [name for name, pattern in PATTERNS if re.search(pattern, lower)]


def view(entry: NotebookEntry) -> dict:
    due = entry.next_review if entry.next_review.tzinfo else entry.next_review.replace(tzinfo=timezone.utc)
    return {"id": entry.id, "kind": entry.kind, "text": entry.text, "category": entry.category, "skill": entry.skill, "source": entry.source,
            "detail": entry.detail or {}, "count": entry.count, "mastered": entry.mastered, "review_level": entry.review_level,
            "due": (not entry.mastered) and due <= now(), "next_review": due, "created_at": entry.created_at, "updated_at": entry.updated_at}


def add_entry(db: Session, user_id: int, kind: str, text: str, *, key: str | None = None, category: str = "", skill: str = "", source: str = "", detail: dict | None = None) -> tuple[NotebookEntry, bool]:
    """Create an entry or merge it into an existing one. Returns (entry, created)."""
    key = (key or norm(text))[:300]
    entry = db.scalar(select(NotebookEntry).where(NotebookEntry.user_id == user_id, NotebookEntry.kind == kind, NotebookEntry.key == key))
    if entry:
        entry.count += 1
        merged = dict(entry.detail or {})
        for name, value in (detail or {}).items():
            if name == "contexts":
                merged["contexts"] = list(dict.fromkeys((merged.get("contexts") or []) + value))[-5:]
            elif value not in (None, "", [], {}):
                merged[name] = value
        entry.detail = merged
        if kind in ("mistake", "grammar", "word"):
            entry.mastered = False  # the same problem came back
            entry.review_level = min(entry.review_level, 1)
            entry.next_review = now()
        entry.source = source or entry.source
        entry.updated_at = now()
        return entry, False
    entry = NotebookEntry(user_id=user_id, kind=kind, text=text.strip()[:4000], key=key, category=category[:120], skill=skill[:20], source=source[:200],
                          detail=detail or {}, count=1, mastered=False, review_level=0, next_review=now())
    db.add(entry)
    db.flush()
    return entry, True


def review(entry: NotebookEntry, remembered: bool) -> NotebookEntry:
    entry.review_level = min(len(INTERVALS) - 1, entry.review_level + 1) if remembered else 0
    entry.next_review = now() + timedelta(days=INTERVALS[entry.review_level]) if remembered else now() + timedelta(minutes=10)
    entry.mastered = entry.review_level >= len(INTERVALS) - 1
    detail = dict(entry.detail or {})
    detail["reviews"] = int(detail.get("reviews", 0)) + 1
    detail["last_result"] = "remembered" if remembered else "forgot"
    entry.detail = detail
    return entry


def retry_mistake(entry: NotebookEntry, answer: str) -> bool:
    detail = entry.detail or {}
    correct = is_correct({"answer": detail.get("answer", ""), "accepts": detail.get("accepts", [])}, answer, detail.get("type", "completion"))
    review(entry, correct)
    if correct and entry.review_level >= 2:
        entry.mastered = True  # answered correctly on two separate reviews
    return correct


# ---------------------------------------------------------------- automatic recording

def record_objective_mistakes(db: Session, user_id: int, test: dict, review_items: list[dict], skill: str, source: str) -> int:
    questions = {}
    for section in test.get("sections", [test]):
        for group in section.get("groups", []):
            for question in group.get("questions", []):
                questions[question["n"]] = (section, group, question)
    added = 0
    for item in review_items:
        if item.get("correct") or item["n"] not in questions:
            continue
        section, group, question = questions[item["n"]]
        prompt = question.get("prompt") or (f"{question.get('prefix', '')}___" if group["type"] == "cwords" else "")
        if question.get("clip"):
            prompt = f"{' '.join(line['text'] for line in question['clip'])} — {prompt}"
        options = question.get("options") or group.get("options") or []
        add_entry(db, user_id, "mistake", prompt or f"Question {item['n']}", key=f"{section.get('id', source)}:{item['n']}", category=TYPE_LABELS.get(group["type"], group["type"]),
                  skill=skill, source=f"{section.get('title', source)}",
                  detail={"n": item["n"], "type": group["type"], "instructions": group.get("instructions", ""), "heading": group.get("heading"), "options": options,
                          "given": item.get("given", ""), "answer": question["answer"], "accepts": question.get("accepts", []), "evidence": question.get("evidence", ""),
                          "test_title": test.get("title", source)})
        added += 1
    return added


GRAMMAR_HINT = re.compile(r"grammar|verb|tense|plural|article|agreement|preposition|uncountable|comparative|capital|repeated|form|word order|spelling|collocation|subject", re.I)


def record_feedback(db: Session, user_id: int, payload: dict, skill: str, source: str) -> dict:
    """Save grammar errors and model sentences from a released writing/speaking result."""
    grammar = sentences = 0
    for comment in payload.get("comments", []) or []:
        sentence = (comment.get("sentence") or "").strip()
        issue = (comment.get("issue") or "").strip()
        if len(sentence.split()) < 3 or not issue:
            continue
        if not (comment.get("correction") or GRAMMAR_HINT.search(issue + " " + (comment.get("suggestion") or ""))):
            continue
        add_entry(db, user_id, "grammar", sentence, key=f"{norm(issue)}|{norm(sentence)}"[:300], category=issue[:120], skill=skill, source=source,
                  detail={"issue": issue, "suggestion": comment.get("suggestion", ""), "correction": comment.get("correction", "")})
        grammar += 1
    for item in payload.get("improved_sentences", []) or []:
        improved = (item.get("improved") or "").strip()
        if len(improved.split()) < 5:
            continue
        add_entry(db, user_id, "sentence", improved, category=", ".join(sentence_patterns(improved)[:3]) or "Corrected sentence", skill=skill, source=source,
                  detail={"origin": "rewrite", "original": item.get("original", ""), "patterns": sentence_patterns(improved)})
        sentences += 1
    return {"grammar": grammar, "sentences": sentences}


# ---------------------------------------------------------------- dictionary

DICT_PATH = Path(__file__).parent / "data" / "ecdict_lite.json.gz"
NEWLINE = "\n"
POS = {"n": "noun", "v": "verb", "vt": "verb", "vi": "verb", "a": "adjective", "adj": "adjective", "s": "adjective", "r": "adverb", "adv": "adverb", "prep": "preposition", "conj": "conjunction", "pron": "pronoun", "int": "interjection"}
EXAM_TAGS = {"zk": "中考", "gk": "高考", "cet4": "CET-4", "cet6": "CET-6", "ky": "考研", "ielts": "IELTS", "toefl": "TOEFL", "gre": "GRE"}


@lru_cache(maxsize=1)
def _offline() -> dict:
    try:
        with gzip.open(DICT_PATH, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    except OSError:
        return {"entries": {}, "forms": {}}


def offline_lookup(word: str) -> dict:
    """ECDICT (MIT licence) subset bundled with the app: phonetics, English definitions and Chinese meanings."""
    data = _offline()
    key = word.strip().lower()
    lemma = key if key in data["entries"] else data["forms"].get(key) or (key[:-1] if key.endswith("s") and key[:-1] in data["entries"] else None)
    if not lemma:
        return {}
    phonetic, translation, definition, tags = data["entries"][lemma]
    meanings = []
    for line in definition.split(NEWLINE):
        match = re.match(r"^(n|v|vt|vi|a|adj|s|r|adv|prep|conj|pron|int)\.?\s+(.+)$", line.strip())
        if match:
            meanings.append({"pos": POS.get(match.group(1), match.group(1)), "definition": match.group(2), "example": ""})
        elif line.strip():
            meanings.append({"pos": "", "definition": line.strip(), "example": ""})
    return {"phonetic": f"/{phonetic}/" if phonetic else "", "translation": "；".join(line.strip() for line in translation.split(NEWLINE) if line.strip())[:160],
            "meanings": meanings[:3], "lemma": lemma if lemma != key else "", "exam_tags": [EXAM_TAGS[t] for t in tags.split() if t in EXAM_TAGS], "dictionary": "ECDICT (offline)"}


def dictionary_lookup(word: str) -> dict:
    """Bundled offline dictionary first; the free online dictionary adds examples when reachable."""
    offline = offline_lookup(word)
    if offline:
        return offline
    try:
        response = httpx.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.strip().lower()}", timeout=2.5)
        if response.status_code != 200:
            return offline
        data = response.json()[0]
        meanings = [{"pos": meaning.get("partOfSpeech", ""), "definition": d.get("definition", ""), "example": d.get("example", "")}
                    for meaning in data.get("meanings", [])[:3] for d in meaning.get("definitions", [])[:2]]
        phonetic = data.get("phonetic") or next((p.get("text") for p in data.get("phonetics", []) if p.get("text")), "")
        synonyms = list(dict.fromkeys(s for meaning in data.get("meanings", []) for s in meaning.get("synonyms", [])))[:6]
        return {**offline, "phonetic": offline.get("phonetic") or phonetic, "meanings": meanings[:4] or offline.get("meanings", []), "synonyms": synonyms,
                "dictionary": "ECDICT + dictionaryapi.dev" if offline else "dictionaryapi.dev"}
    except Exception:
        return offline


# ---------------------------------------------------------------- tutor memory

ABOUT = [
    (r"\bmy name is ([a-z][a-z'-]{1,20}(?: (?!and\b|i\b|but\b|so\b)[a-z][a-z'-]{1,20})?)", "about", "Name: {0}"),
    (r"\bi(?: am|'m) (?:a|an) ([a-z][a-z ]{2,40}?)(?:\.|,|$| and| who| at| in)", "about", "Is a {0}"),
    (r"\bi work (?:as|in) ([a-z][a-z ]{2,40}?)(?:\.|,|$| and)", "about", "Works as/in {0}"),
    (r"\bi(?: am|'m) from ([a-z][a-z ]{2,40}?)(?:\.|,|$| and)", "about", "From {0}"),
    (r"\bi (?:want|need|hope|plan) to ([a-z][^.!?]{4,80})", "goal", "Wants to {0}"),
    (r"\bi(?: am|'m) (?:nervous|worried|scared|anxious) (?:about|when|of) ([^.!?]{3,80})", "difficulty", "Feels anxious about {0}"),
    (r"\bi (?:struggle|have trouble|have difficulty|find it hard) (?:with |to )?([^.!?]{3,80})", "difficulty", "Struggles with {0}"),
    (r"\bmy (?:weakness|weak point|problem) is ([^.!?]{3,80})", "difficulty", "Weakness: {0}"),
    (r"\bi (?:like|love|enjoy|prefer) ([^.!?]{3,80})", "preference", "Likes {0}"),
]


def extract_memories(message: str) -> list[tuple[str, str]]:
    lower = message.lower().strip()
    found = []
    explicit = re.match(r"^(?:please )?remember(?: that)?[:\s]+(.{4,240})", lower) or re.match(r"^\s*(?:请)?记住[:：\s]*(.{2,240})", message.strip())
    if explicit:
        found.append(("note", explicit.group(1).strip().rstrip(".")))
    for pattern, kind, template in ABOUT:
        match = re.search(pattern, lower)
        if match:
            value = match.group(1).strip().rstrip(".")
            found.append((kind, template.format(value.title() if template.startswith("Name") else value)))
    return found[:4]


def remember(db: Session, user_id: int, kind: str, text: str, key: str = "", source: str = "chat") -> LearnerMemory:
    text = text.strip()[:500]
    existing = db.scalar(select(LearnerMemory).where(LearnerMemory.user_id == user_id, LearnerMemory.key == key)) if key else \
        db.scalar(select(LearnerMemory).where(LearnerMemory.user_id == user_id, LearnerMemory.text == text))
    if existing:
        existing.text, existing.kind, existing.updated_at = text, kind, now()
        return existing
    memory = LearnerMemory(user_id=user_id, kind=kind, key=key, text=text, source=source)
    db.add(memory)
    db.flush()
    return memory


def memories(db: Session, user_id: int, limit: int = 40) -> list[LearnerMemory]:
    return list(db.scalars(select(LearnerMemory).where(LearnerMemory.user_id == user_id).order_by(LearnerMemory.updated_at.desc()).limit(limit)))


def update_progress_memory(db: Session, user_id: int, skill: str, payload: dict) -> None:
    criteria = payload.get("criteria") or {}
    score = payload.get("estimated_overall")
    if score is None:
        return
    weakest = min(criteria, key=criteria.get).replace("_", " ") if len(criteria) > 1 else None
    text = f"Latest verified {skill} estimate: {score} ({now().date().isoformat()})" + (f"; weakest criterion: {weakest}" if weakest else "")
    if payload.get("raw_score") is not None:
        text += f"; {payload['raw_score']}/{payload.get('total')} correct"
    remember(db, user_id, "progress", text, key=f"progress:{skill}", source="assessment")


# ---------------------------------------------------------------- chat commands

WORD = r"([A-Za-z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,3})"
WORD_REQUESTS = [
    rf"(?:i )?(?:don'?t|do not) (?:know|understand|recognise|recognize) (?:the )?(?:word|phrase|expression)?\s*['\"“‘]?{WORD}['\"”’]?",
    rf"what (?:does|do) ['\"“‘]?{WORD}['\"”’]? mean",
    rf"(?:what is|what's) the meaning of ['\"“‘]?{WORD}['\"”’]?",
    rf"(?:meaning of|define|definition of) ['\"“‘]?{WORD}['\"”’]?",
    rf"add ['\"“‘]?{WORD}['\"”’]? to (?:my )?(?:word ?book|vocab\w*|notebook|word list)",
    rf"(?:不认识|认不到|不认得|不懂|记录|加入生词本|生词)\s*[:：]?\s*['\"“‘]?{WORD}",
    rf"['\"“‘]?{WORD}['\"”’]?\s*(?:是什么意思|什么意思|啥意思|不认识|认不到)",
]
STOPWORDS = {"it", "this", "that", "the word", "word", "a", "an", "the", "what", "me", "you"}


def requested_words(message: str) -> list[str]:
    words = []
    for pattern in WORD_REQUESTS:
        for match in re.finditer(pattern, message, flags=re.I):
            word = match.group(1).strip().strip("'\"").lower()
            if word and word not in STOPWORDS and len(word) <= 40:
                words.append(word)
    return list(dict.fromkeys(words))[:3]


def is_quiz_request(message: str) -> bool:
    return bool(re.search(r"\b(quiz me|test me|review (my )?words)\b|考考我|测试我|复习单词", message, flags=re.I))


def word_summary(entry: NotebookEntry) -> str:
    detail = entry.detail or {}
    first = (detail.get("meanings") or [{}])[0]
    parts = [f"“{entry.text}”"]
    if detail.get("phonetic"):
        parts.append(detail["phonetic"])
    if first.get("pos"):
        parts.append(f"({first['pos']})")
    text = " ".join(parts)
    if detail.get("translation"):
        text += f" — {detail['translation']}"
    if first.get("definition"):
        text += f": {first['definition']}"
    if first.get("example"):
        text += f" Example: “{first['example']}”"
    return text


# ---------------------------------------------------------------- statistics and coaching

def stats(db: Session, user_id: int) -> dict:
    entries = list(db.scalars(select(NotebookEntry).where(NotebookEntry.user_id == user_id)))
    counts = {kind: {"total": 0, "active": 0, "mastered": 0} for kind in KINDS}
    by_type, by_skill, grammar = {}, {}, {}
    due_words = due_mistakes = 0
    current = now()
    for entry in entries:
        bucket = counts.setdefault(entry.kind, {"total": 0, "active": 0, "mastered": 0})
        bucket["total"] += 1
        bucket["mastered" if entry.mastered else "active"] += 1
        due = (entry.next_review if entry.next_review.tzinfo else entry.next_review.replace(tzinfo=timezone.utc)) <= current
        if entry.kind == "mistake":
            by_type[entry.category] = by_type.get(entry.category, 0) + entry.count
            by_skill[entry.skill] = by_skill.get(entry.skill, 0) + entry.count
            due_mistakes += due and not entry.mastered
        elif entry.kind == "grammar":
            grammar[entry.category] = grammar.get(entry.category, 0) + entry.count
        elif entry.kind == "word":
            due_words += due and not entry.mastered
    order = lambda data: [{"name": k, "count": v} for k, v in sorted(data.items(), key=lambda pair: -pair[1])]
    return {"counts": counts, "mistakes_by_type": order(by_type), "mistakes_by_skill": order(by_skill), "grammar_issues": order(grammar)[:8],
            "due_words": due_words, "due_mistakes": due_mistakes}


def coaching_points(summary: dict, profile: dict, memory_texts: list[str]) -> list[str]:
    points = []
    if summary["mistakes_by_type"]:
        top = summary["mistakes_by_type"][0]
        tips = {"True / False / Not Given": "FALSE needs a direct contradiction; NOT GIVEN means the passage is silent. Underline the exact sentence before choosing.",
                "Completion / gap fill": "Predict the word type before you listen or read, respect the word limit and check spelling and plurals.",
                "Multiple choice": "Eliminate options that are only partly true or that repeat words from the text without matching the meaning.",
                "Matching": "Match the main idea, not a shared word. Do the easiest items first and cross out used options.",
                "Yes / No / Not Given": "Ask what the writer claims, not what is true in the world.",
                "Complete the Words": "Use grammar (part of speech, plural, tense) and meaning of the whole sentence."}
        points.append(f"Your most frequent mistake type is {top['name']} ({top['count']} errors). {tips.get(top['name'], 'Redo these items in the Mistake book until you get them right twice.')}")
    if summary["grammar_issues"]:
        top = summary["grammar_issues"][0]
        points.append(f"Your most repeated grammar problem: “{top['name']}” ({top['count']}×). Review the examples in your Grammar book and write three correct sentences of your own.")
    if summary["due_words"]:
        points.append(f"{summary['due_words']} word(s) are due for review in your Word book. Reviewing at the right time is how they move into long-term memory.")
    if summary["due_mistakes"]:
        points.append(f"{summary['due_mistakes']} mistake(s) are ready to retry. Answer each one again without looking at the evidence first.")
    difficulties = [text for text in memory_texts if text.lower().startswith(("struggles", "feels anxious", "weakness"))]
    if difficulties:
        points.append(f"You told me earlier: {difficulties[0].lower()}. Let's work on that with a short focused task today.")
    if not points:
        focus = (profile.get("priority_skills") or ["writing"])[0]
        points.append(f"Your notebooks are still empty. Start with one {focus} task; I'll record every mistake, unknown word and grammar slip automatically.")
    return points
