"""Objective answer marking, score conversion and the local language analyser.

The local analyser is a transparent, rule-based assessor used when no cloud
model is configured. It measures observable features (length, paragraphing,
cohesive devices, lexical range, sentence complexity and common learner
errors) and maps them onto the exam criteria. It is an estimate, not an
official score, and it never claims to hear pronunciation.
"""
import math
import re
from statistics import pstdev

NUMBER_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
                "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "fifty": "50", "hundred": "100"}

# IELTS raw score (out of 40) to band, from the publicly described conversion ranges.
LISTENING_BANDS = [(39, 9), (37, 8.5), (35, 8), (32, 7.5), (30, 7), (26, 6.5), (23, 6), (18, 5.5), (16, 5), (13, 4.5), (10, 4), (8, 3.5), (6, 3), (4, 2.5), (2, 2), (1, 1), (0, 0)]
READING_BANDS = [(39, 9), (37, 8.5), (35, 8), (33, 7.5), (30, 7), (27, 6.5), (23, 6), (19, 5.5), (15, 5), (13, 4.5), (10, 4), (8, 3.5), (6, 3), (4, 2.5), (2, 2), (1, 1), (0, 0)]


def normalise(value: str) -> str:
    value = (value or "").strip().lower().replace("’", "'")
    value = re.sub(r"[£$€,!?;\"()]", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = re.sub(r"^(a|an|the)\s+", "", value)
    words = [NUMBER_WORDS.get(word, word) for word in value.split(" ")]
    value = " ".join(words)
    if re.fullmatch(r"\d{1,2}[:.]\d{2}", value):
        value = value.replace(":", ".")
    return value


def is_correct(question: dict, response: str, group_type: str) -> bool:
    if response is None or not str(response).strip():
        return False
    if group_type in ("mcq", "matching", "tfng", "ynng"):
        return str(response).strip().upper() == str(question["answer"]).strip().upper()
    accepted = {normalise(item) for item in [question["answer"], *question.get("accepts", [])]}
    given = normalise(str(response))
    return given in accepted or given.replace(" ", "") in {item.replace(" ", "") for item in accepted}


def iter_questions(test: dict):
    """Yield (section, group, question) for a listening or reading test with one or more sections."""
    for section in test.get("sections", [test]):
        for group in section.get("groups", []):
            for question in group.get("questions", []):
                yield section, group, question


def grade_objective(test: dict, answers: dict, skill: str, exam: str) -> dict:
    items = []
    for section, group, question in iter_questions(test):
        given = answers.get(str(question["n"]), "")
        correct = is_correct(question, given, group["type"])
        items.append({"n": question["n"], "section": section.get("title"), "given": given, "answer": question["answer"],
                      "correct": correct, "evidence": question.get("evidence", ""), "type": group["type"]})
    total = len(items)
    raw = sum(item["correct"] for item in items)
    if exam == "IELTS":
        scaled = round(raw / total * 40) if total else 0
        table = LISTENING_BANDS if skill == "listening" else READING_BANDS
        band = next(score for minimum, score in table if scaled >= minimum)
        scale = "IELTS 0-9 bands"
    else:
        scaled = None
        band = toefl_band(raw / total if total else 0)
        scale = "TOEFL 2026 1-6 sections"
    return {"raw": raw, "total": total, "scaled_40": scaled, "band": band, "score_scale": scale, "items": items}


def toefl_band(proportion: float) -> float:
    for minimum, score in [(.95, 6), (.85, 5.5), (.75, 5), (.65, 4.5), (.55, 4), (.45, 3.5), (.35, 3), (.25, 2.5), (.15, 2), (.05, 1.5)]:
        if proportion >= minimum:
            return score
    return 1.0


def strip_answers(test: dict) -> dict:
    """Copy of a test without answer keys or evidence, safe to send before submission."""
    def clean_group(group):
        return {**group, "questions": [{k: v for k, v in q.items() if k not in ("answer", "accepts", "evidence")} for q in group.get("questions", [])]}
    if "sections" in test:
        return {**test, "sections": [{**section, "groups": [clean_group(g) for g in section.get("groups", [])]} for section in test["sections"]]}
    if "groups" in test:
        return {**test, "groups": [clean_group(g) for g in test["groups"]]}
    return test


def validate_test(test: dict) -> list[str]:
    """Structural checks used by the Quality Manager for generated listening/reading tests."""
    issues = []
    sections = test.get("sections", [test])
    count = 0
    for section in sections:
        source = " ".join(line.get("text", "") for line in section.get("script", [])) + " " + " ".join(p.get("text", "") for p in section.get("passage", []))
        for clip_group in section.get("groups", []):
            for question in clip_group.get("questions", []):
                source += " " + " ".join(line.get("text", "") for line in question.get("clip", []))
        source_norm = normalise(source)
        if section.get("kind") == "listening" and not section.get("script") and not any(q.get("clip") for g in section.get("groups", []) for q in g.get("questions", [])):
            issues.append("Listening section has no audio script")
        for group in section.get("groups", []):
            keys = {str(option.get("key")).upper() for option in group.get("options", [])}
            for question in group.get("questions", []):
                count += 1
                answer = str(question.get("answer", "")).strip()
                if not answer:
                    issues.append(f"Question {question.get('n')} has no answer")
                    continue
                if group["type"] == "mcq":
                    option_keys = {str(option.get("key")).upper() for option in question.get("options", [])}
                    if answer.upper() not in option_keys:
                        issues.append(f"Question {question.get('n')} answer is not one of its options")
                elif group["type"] == "matching" and answer.upper() not in keys:
                    issues.append(f"Question {question.get('n')} answer is not in the option list")
                elif group["type"] == "tfng" and answer.upper() not in ("TRUE", "FALSE", "NOT GIVEN"):
                    issues.append(f"Question {question.get('n')} needs TRUE, FALSE or NOT GIVEN")
                elif group["type"] == "ynng" and answer.upper() not in ("YES", "NO", "NOT GIVEN"):
                    issues.append(f"Question {question.get('n')} needs YES, NO or NOT GIVEN")
                elif group["type"] == "completion" and not re.fullmatch(r"\d{5,}", answer.replace(" ", "")):
                    accepted = [normalise(item) for item in [answer, *question.get("accepts", [])]]
                    if not any(item and item in source_norm for item in accepted):
                        issues.append(f"Question {question.get('n')} answer is not supported by the audio script or passage")
    if count < 4:
        issues.append("Test must contain at least four questions")
    return issues


# ---------------------------------------------------------------- local language analyser

LINKERS = ["however", "moreover", "furthermore", "in addition", "additionally", "for example", "for instance", "such as", "therefore", "consequently",
           "as a result", "on the other hand", "in contrast", "although", "whereas", "while", "firstly", "secondly", "finally", "in conclusion",
           "to sum up", "overall", "because", "since", "thus", "nevertheless", "despite", "even though", "similarly", "meanwhile", "in particular",
           "on the whole", "to begin with", "what is more", "as well as", "not only", "this means", "instead"]
COMPLEX = [r"\bwhich\b", r"\bwho\b", r"\bwhose\b", r"\bwhom\b", r"\bif\b", r"\bunless\b", r"\balthough\b", r"\bwhereas\b", r"\bwhile\b",
           r"\bbecause\b", r"\bsince\b", r"\bwhen\b", r"\bdespite\b", r"\b(?:is|are|was|were|been|be)\s+\w+ed\b", r"\bwould\b", r"\bhad\s+\w+ed\b",
           r"\bnot only\b", r"\bthat\b"]
FILLERS = re.compile(r"\b(um+|uh+|er+|erm+|hmm+|you know|i mean|kind of|sort of)\b", re.I)
ACADEMIC = {"significant", "consequently", "substantial", "approximately", "considerable", "proportion", "contribute", "perspective", "beneficial",
            "detrimental", "fundamental", "crucial", "inevitable", "phenomenon", "sustainable", "infrastructure", "implement", "facilitate",
            "enhance", "promote", "alleviate", "comprehensive", "diverse", "potential", "access", "economic", "environmental", "individual",
            "particularly", "whereas", "furthermore", "nevertheless", "illustrate", "demonstrate", "emphasise", "emphasize", "decline", "fluctuate"}
ERRORS = [
    (r"\bpeoples\b(?!')", "Use 'people' (already plural) unless you mean nations.", lambda s: re.sub(r"\bpeoples\b", "people", s)),
    (r"\b(informations|advices|knowledges|equipments|furnitures|homeworks|researches|evidences|feedbacks)\b", "This noun is uncountable; drop the -s.", lambda s: re.sub(r"\b(information|advice|knowledge|equipment|furniture|homework|research|evidence|feedback)s\b", r"\1", s)),
    (r"\bmore (better|easier|worse|bigger|faster|cheaper|happier)\b", "Do not combine 'more' with a comparative adjective.", lambda s: re.sub(r"\bmore (better|easier|worse|bigger|faster|cheaper|happier)\b", r"\1", s)),
    (r"\b(didn't|did not|doesn't|does not|don't|do not) (went|saw|came|took|made|had|got|bought|thought|ate|wrote|knew)\b", "After do/does/did, use the base form of the verb.", None),
    (r"\b(he|she|it) don't\b", "Use 'doesn't' with he/she/it.", lambda s: re.sub(r"\b(he|she|it) don't\b", r"\1 doesn't", s, flags=re.I)),
    (r"(?:^|[,;]\s*|\band\s|\bbecause\s)(he|she|it) (have|go|want|like|need|think)\b", "Third-person singular verbs need -s (e.g. 'she wants').", None),
    (r"\bpeople is\b", "'People' takes a plural verb: 'people are'.", lambda s: re.sub(r"\bpeople is\b", "people are", s)),
    (r"\b(everyone|everybody|someone|nobody) are\b", "Indefinite pronouns take a singular verb: 'everyone is'.", lambda s: re.sub(r"\b(everyone|everybody|someone|nobody) are\b", r"\1 is", s)),
    (r"\bchildrens\b", "'Children' is already plural.", lambda s: re.sub(r"\bchildrens\b", "children", s)),
    (r"\bin the other hand\b", "The fixed phrase is 'on the other hand'.", lambda s: s.replace("in the other hand", "on the other hand")),
    (r"\b(discuss|emphasise|emphasize|mention) about\b", "This verb takes a direct object; remove 'about'/'on'.", lambda s: re.sub(r"\b(discuss|emphasise|emphasize|mention) about\b", r"\1", s)),
    (r"\b(can|could) able to\b", "Use 'can' or 'be able to', not both.", lambda s: re.sub(r"\b(can|could) able to\b", r"\1", s)),
    (r"\bmake (a )?research\b", "We 'do' or 'carry out' research.", lambda s: re.sub(r"\bmake (a )?research\b", "do research", s)),
    (r"\bexplain me\b", "Use 'explain to me'.", lambda s: s.replace("explain me", "explain to me")),
    (r"\bthe the\b|\ba a\b|\bto to\b", "A word is repeated by mistake.", lambda s: re.sub(r"\b(the|a|to) \1\b", r"\1", s)),
    (r"\ba (?!uni|use|usu|one|euro|u\b)([aeiou]\w*)", "Use 'an' before a vowel sound.", lambda s: re.sub(r"\ba (?!uni|use|usu|one|euro)([aeiou]\w*)", r"an \1", s)),
    (r"\bsince (\d+ )?(years|months|days|weeks)\b", "Use 'for' with a period of time (for two years).", None),
    (r"\b(we|they|you) am\b|\bi (is|are)\b", "Check subject-verb agreement (I am, we are).", None),
]
STOP = set("the a an and or but of to in on at for with by from this that these those is are was were be been being it its as into than then there their they them some many much more most other such can could should would will may might must not no do does did have has had about also very what which who whom whose when where why how all any each few both own same so too only just your you our we i he she his her my me".split())


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if len(part.strip().split()) >= 2]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _mattr(words: list[str], window: int = 50) -> float:
    if len(words) < 10:
        return len(set(words)) / max(len(words), 1)
    if len(words) <= window:
        return len(set(words)) / len(words)
    ratios = [len(set(words[i:i + window])) / window for i in range(0, len(words) - window + 1, 5)]
    return sum(ratios) / len(ratios)


def _half(value: float, low: float = 3.0, high: float = 8.5) -> float:
    return max(low, min(high, round(value * 2) / 2))


def find_errors(text: str, spoken: bool = False) -> list[dict]:
    found = []
    for sentence in _sentences(text):
        lower = sentence.lower()
        for pattern, advice, fix in ERRORS:
            if re.search(pattern, lower, flags=re.I):
                corrected = fix(lower) if fix else None
                found.append({"sentence": sentence[:220], "issue": advice.split(";")[0].split(".")[0], "suggestion": advice,
                              **({"correction": corrected} if corrected and corrected != lower else {})})
        if spoken:
            continue  # Recognised speech has no reliable capitals or punctuation.
        if re.search(r"(^|\s)i(\s|'|$)", sentence):
            found.append({"sentence": sentence[:220], "issue": "Capitalise the pronoun 'I'", "suggestion": "The pronoun 'I' is always written with a capital letter."})
        if sentence[:1].islower():
            found.append({"sentence": sentence[:220], "issue": "Sentence should start with a capital letter", "suggestion": "Begin every sentence with a capital letter."})
        if len(sentence.split()) > 42:
            found.append({"sentence": sentence[:220], "issue": "Very long sentence", "suggestion": "Split this into two sentences or use clearer punctuation to avoid a run-on."})
    return found


def text_features(text: str, prompt: str = "", spoken: bool = False) -> dict:
    words = _words(text)
    sentences = _sentences(text)
    paragraphs = [p for p in re.split(r"\n\s*\n|\n(?=\s*[A-Z])", text.strip()) if len(p.split()) >= 8]
    lower = " " + text.lower() + " "
    linkers = {item: len(re.findall(rf"\b{re.escape(item)}\b", lower)) for item in LINKERS}
    used = {k: v for k, v in linkers.items() if v}
    complex_hits = sum(len(re.findall(pattern, lower)) for pattern in COMPLEX)
    lengths = [len(s.split()) for s in sentences] or [0]
    content_words = [w for w in words if len(w) > 3 and w not in STOP]
    prompt_terms = {w for w in _words(prompt) if len(w) > 4 and w not in STOP}
    relevance = len(prompt_terms & set(content_words)) / len(prompt_terms) if prompt_terms else .5
    errors = find_errors(text, spoken)
    return {
        "words": len(text.split()), "sentences": len(sentences), "paragraphs": max(len(paragraphs), 1),
        "lexical_diversity": round(_mattr(words), 3),
        "long_word_ratio": round(sum(len(w) >= 7 for w in words) / max(len(words), 1), 3),
        "academic_words": sorted({w for w in words if w in ACADEMIC}),
        "linkers_used": used, "linker_variety": len(used), "overused_linkers": [k for k, v in used.items() if v > 3],
        "complex_per_sentence": round(complex_hits / max(len(sentences), 1), 2),
        "avg_sentence_length": round(sum(lengths) / len(lengths), 1), "sentence_length_spread": round(pstdev(lengths), 1) if len(lengths) > 1 else 0,
        "relevance": round(relevance, 2), "errors": errors, "error_rate_per_100": round(len(errors) / max(len(words), 1) * 100, 2),
        "fillers": len(FILLERS.findall(text)),
        "examples": len(re.findall(r"\b(for example|for instance|such as|e\.g\.|to illustrate)\b", lower)),
        "position": bool(re.search(r"\b(i believe|in my opinion|i agree|i disagree|i think|in my view|i would argue|this essay (will|argues))\b", lower)),
        "overview": bool(re.search(r"\b(overall|in general|it is clear|it is noticeable|generally speaking|the most striking)\b", lower)),
        "numbers": len(re.findall(r"\d", text)),
        "contractions": len(re.findall(r"\b\w+n't\b|\b(i'm|it's|they're|we're|you're)\b", lower)),
    }


def _criterion_scores(f: dict, min_words: int, task: str, spoken: bool, metrics: dict | None) -> dict:
    # Task response / achievement
    tr = 5.0
    if f["words"] >= min_words:
        tr += .5
    if f["words"] >= min_words * 1.1:
        tr += .5
    if f["words"] < min_words * .6:
        tr -= 1
    if f["relevance"] >= .35:
        tr += .5
    elif f["relevance"] < .15 and not spoken:
        tr -= .5
    if (task == "task1" and f["overview"]) or (task != "task1" and (f["position"] or spoken)):
        tr += .5
    if f["examples"] or (task == "task1" and f["numbers"] >= 6):
        tr += .5
    # Coherence and cohesion
    cc = 5.0
    if not spoken and f["paragraphs"] >= (3 if task == "task1" else 4):
        cc += .5
    elif not spoken and f["paragraphs"] < 2:
        cc -= .5
    cc += .5 if f["linker_variety"] >= 4 else 0
    cc += .5 if f["linker_variety"] >= 7 else 0
    cc -= .5 if f["overused_linkers"] else 0
    cc += .5 if 11 <= f["avg_sentence_length"] <= 26 else 0
    # Lexical resource
    lr = 5.0
    lr += .5 if f["lexical_diversity"] >= .68 else 0
    lr += .5 if f["lexical_diversity"] >= .75 else 0
    lr += .5 if f["long_word_ratio"] >= .16 else 0
    lr += .5 if len(f["academic_words"]) >= 4 else 0
    lr -= .5 if any("uncountable" in e["suggestion"] for e in f["errors"]) else 0
    # Grammatical range and accuracy
    gr = 5.0
    gr += .5 if f["complex_per_sentence"] >= .5 else 0
    gr += .5 if f["complex_per_sentence"] >= .9 else 0
    gr += 1 if f["error_rate_per_100"] < .5 else .5 if f["error_rate_per_100"] < 1.5 else -.5 if f["error_rate_per_100"] > 3 else 0
    gr += .5 if f["sentence_length_spread"] >= 5 else 0
    scores = {"task": tr, "coherence": cc, "lexical": lr, "grammar": gr}
    if spoken:
        fl = 5.0
        wpm = (metrics or {}).get("words_per_minute")
        if wpm:
            fl += 1 if 110 <= wpm <= 175 else .5 if 90 <= wpm < 110 or 175 < wpm <= 200 else -.5 if wpm < 70 else 0
        avg_turn = (metrics or {}).get("average_turn_words") or f["words"]
        fl += .5 if avg_turn >= 25 else -.5 if avg_turn < 10 else 0
        fl += .5 if f["linker_variety"] >= 4 else 0
        filler_rate = f["fillers"] / max(f["words"], 1)
        fl += .5 if filler_rate < .02 else -.5 if filler_rate > .08 else 0
        scores["fluency"] = fl
    if f["words"] < 40:
        scores = {k: min(v, 4.5) for k, v in scores.items()}
    return {k: _half(v) for k, v in scores.items()}


def analyse_response(exam: str, skill: str, text: str, prompt: str = "", task: str = "task2", metrics: dict | None = None) -> dict:
    """Return a FeedbackOutput-shaped dict from observable text features."""
    spoken = skill == "speaking"
    if spoken:
        min_words = 150
    else:
        min_words = {"task1": 150, "task2": 250, "email": 100, "discussion": 100}.get(task, 250 if exam == "IELTS" else 100)
    f = text_features(text, prompt, spoken)
    s = _criterion_scores(f, min_words, task, spoken, metrics)
    if exam == "IELTS":
        criteria = ({"fluency": s["fluency"], "lexical_resource": s["lexical"], "grammar": s["grammar"]} if spoken else
                    {"task_response": s["task"], "coherence": s["coherence"], "lexical_resource": s["lexical"], "grammar": s["grammar"]})
    else:
        conv = lambda band: max(1.0, min(6.0, round(((band - 3) / 5.5 * 5 + 1) * 2) / 2))
        criteria = ({"language_use": conv((s["lexical"] + s["grammar"]) / 2), "topic_development": conv((s["task"] + s["fluency"]) / 2)} if spoken else
                    {"task_fulfillment": conv(s["task"]), "organisation": conv(s["coherence"]), "language_use": conv((s["lexical"] + s["grammar"]) / 2)})
        repeat = (metrics or {}).get("repeat_accuracy")
        if spoken and isinstance(repeat, (int, float)):
            criteria["language_use"] = max(1.0, min(6.0, round(((criteria["language_use"] + 1 + repeat * 5) / 2) * 2) / 2))
    comments = []
    for error in f["errors"][:5]:
        comments.append({k: v for k, v in error.items()})
    if f["words"] < min_words:
        comments.append({"sentence": "", "issue": "Response is under length", "suggestion": f"You wrote {f['words']} words; aim for at least {min_words}. Under-length answers are limited in Task Response." if not spoken else f"You spoke {f['words']} words in total. Extend each answer with a reason and an example."})
    if not spoken and task == "task1" and not f["overview"]:
        comments.append({"sentence": "", "issue": "No clear overview", "suggestion": "Add an overview sentence (e.g. 'Overall, ...') summarising the main trends before the details."})
    if not spoken and task == "task2" and not f["position"]:
        comments.append({"sentence": "", "issue": "Position is unclear", "suggestion": "State your opinion clearly in the introduction and restate it in the conclusion."})
    if f["examples"] == 0 and task != "task1":
        comments.append({"sentence": "", "issue": "Develop ideas with examples", "suggestion": "Support each main point with a specific example, statistic or personal experience."})
    if f["linker_variety"] < 3:
        comments.append({"sentence": "", "issue": "Limited cohesive devices", "suggestion": "Link ideas with a range of connectors such as 'however', 'as a result' and 'for instance'."})
    if f["overused_linkers"]:
        comments.append({"sentence": "", "issue": "Overused linking words", "suggestion": f"Vary these connectors: {', '.join(f['overused_linkers'])}."})
    if not spoken and exam == "IELTS" and f["contractions"] >= 2:
        comments.append({"sentence": "", "issue": "Informal contractions", "suggestion": "Write 'do not' instead of 'don't' in academic writing."})
    if spoken and f["fillers"] >= 4:
        comments.append({"sentence": "", "issue": "Frequent filler words", "suggestion": f"You used {f['fillers']} fillers (um, er, you know). Pause silently or use phrases like 'Let me think...'."})
    if not comments:
        comments.append({"sentence": _sentences(text)[0][:200] if _sentences(text) else "", "issue": "Push for higher-level language", "suggestion": "Try a wider range of complex sentences and less common vocabulary to reach the next band."})
    strengths = []
    if f["lexical_diversity"] >= .72:
        strengths.append("a good range of vocabulary")
    if f["linker_variety"] >= 5:
        strengths.append("varied linking words")
    if f["complex_per_sentence"] >= .7:
        strengths.append("a mix of complex sentence structures")
    if f["error_rate_per_100"] < 1:
        strengths.append("generally accurate grammar")
    if f["words"] >= min_words:
        strengths.append("sufficient length")
    lowest = min(criteria, key=criteria.get)
    summary = (f"This {'spoken' if spoken else 'written'} response contains {f['words']} words. "
               + (f"Strengths include {', '.join(strengths[:3])}. " if strengths else "")
               + f"The main area to improve is {lowest.replace('_', ' ')}; see the specific comments below.")
    improvements = list(dict.fromkeys(c["suggestion"] for c in comments))[:4]
    # Rule-based measures are less reliable on very short samples, but a clearly under-length answer is still scorable.
    confidence_value = .78 if f["words"] < min_words * .5 else .84
    corrected = [{"original": c["sentence"], "improved": c["correction"]} for c in comments if c.get("correction")]
    result = {
        "summary": summary, "criteria": criteria, "comments": comments[:8], "improvements": improvements,
        "confidence": {k: confidence_value for k in criteria},
        "pronunciation_available": False,
        "pronunciation_note": ("Pronunciation is not scored: the transcript shows what was recognised, not how it sounded. "
                               + (f"Speech rate: {metrics['words_per_minute']} words per minute." if metrics and metrics.get("words_per_minute") else "")) if spoken else None,
        "improved_sentences": corrected[:5],
        "analysis": {k: f[k] for k in ("words", "sentences", "paragraphs", "lexical_diversity", "linker_variety", "complex_per_sentence", "error_rate_per_100", "academic_words")},
    }
    if spoken and metrics:
        result["analysis"].update({k: metrics[k] for k in ("words_per_minute", "speaking_seconds", "repeat_accuracy") if k in metrics})
    return result


def repeat_accuracy(target: str, spoken: str) -> float:
    """Word-level accuracy for TOEFL Listen and Repeat (longest common subsequence)."""
    a, b = _words(target), _words(spoken)
    if not a:
        return 0.0
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            table[i + 1][j + 1] = table[i][j] + 1 if a[i] == b[j] else max(table[i][j + 1], table[i + 1][j])
    return round(table[-1][-1] / len(a), 2)


def overall_band(scores: list[float], exam: str) -> float:
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    if exam == "IELTS":
        return math.floor(mean * 2 + .5) / 2  # IELTS rounds .25 up to the next half band
    return round(mean * 2) / 2
