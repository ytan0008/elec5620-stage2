"""Assessment & Analytics tools (UC5 steps 6-7, UC6 steps 2-6).

Pure analysis of verified (RELEASED) results: per-skill estimates, strengths and
weaknesses against the target, trends, readiness, recommendations and mock
comparisons. AssessmentAgent in backend/agents.py calls these and records what it
did; nothing here talks to the language model.
"""
import re
from collections import Counter
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import MockExam, Profile, ResultPackage
from backend.scoring import grade_objective


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
    target = db.scalar(select(Profile.target_score).where(Profile.user_id == user_id))
    # Strengths are at or above the target, weaknesses below it, so a skill is never both (UC6 step 4).
    strong, weak = split_skills(averages, target) if averages else ([], [])
    trends, trend_note = skill_trends(history)
    readiness, readiness_note = progress_readiness(averages, target, len(packages))
    return {"skill_scores": averages, "history": history, "weaknesses": [w["skill"] for w in weak], "strengths": [s["skill"] for s in strong],
            "weakness_notes": weak, "strength_notes": strong, "trends": trends, "trend_note": trend_note,
            "repeated_errors": [{"issue": issue, "count": count} for issue, count in error_counts.items() if count >= 2], "sample_count": len(packages),
            "readiness": readiness, "readiness_note": readiness_note}


TREND_STEP = .25  # Smaller changes than a quarter band are treated as steady.


def skill_trends(history: list[dict]) -> tuple[dict, str]:
    """Per-skill trend: the latest verified result against the average of the earlier ones (UC6 step 5)."""
    by_skill: dict[str, list[float]] = {}
    for item in history:
        by_skill.setdefault(item["skill"], []).append(item["score"])
    trends = {}
    for skill, values in by_skill.items():
        if len(values) < 2:
            trends[skill] = {"results": 1, "latest": values[-1], "direction": "not enough data"}
            continue
        change = round(values[-1] - sum(values[:-1]) / len(values[:-1]), 2)
        trends[skill] = {"results": len(values), "first": values[0], "latest": values[-1], "change": change,
                         "direction": "improving" if change >= TREND_STEP else "declining" if change <= -TREND_STEP else "steady"}
    thin = sorted(skill for skill, t in trends.items() if t["direction"] == "not enough data")
    if not trends or len(thin) == len(trends):
        note = "Not enough results to show a trend yet: complete at least two verified results in a skill."
    elif thin:
        note = f"Not enough data for a trend in {', '.join(thin)} yet: one more verified result in each is needed."
    else:
        note = ""
    return trends, note


def progress_readiness(averages: dict[str, float], target: float | None, samples: int) -> tuple[str, str]:
    """One readiness rule for the Performance page and saved reports."""
    if samples < 2 or not averages or target is None:
        return "Insufficient data", "Complete at least two verified results before readiness is estimated."
    mean = round(sum(averages.values()) / len(averages), 2)
    gap = round(target - mean, 2)
    level = "On track" if gap <= 0 else "Close to target" if gap <= .5 else "Needs further practice"
    return level, f"Your average verified estimate is {mean} against a target of {target}" + (f" ({gap} to go)." if gap > 0 else ".")


def issue_history(db: Session, user_id: int) -> dict[str, int]:
    """How often each feedback issue appeared in the learner's earlier verified writing, speaking and mock results."""
    counts: dict[str, int] = {}
    for package in db.scalars(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.state == "RELEASED",
                                                          ResultPackage.kind.in_(["writing", "speaking", "mock_exam"]))):
        payload = package.payload or {}
        comments = payload.get("comments", []) if package.kind != "mock_exam" else \
            [c for fb in (payload.get("details", {}).get("writing") or {}).values() for c in fb.get("comments", [])] + (payload.get("details", {}).get("speaking") or {}).get("comments", [])
        for comment in comments:
            if comment.get("issue"):
                counts[comment["issue"]] = counts.get(comment["issue"], 0) + 1
    return counts


def split_skills(scores: dict[str, float], target: float | None) -> tuple[list[dict], list[dict]]:
    """Strengths and weaknesses never overlap: below target is a weakness, at or above is a strength.
    When every skill sits on one side, the clearest outlier (at least half a band away) is named relative to the others."""
    ordered = sorted(scores, key=scores.get)
    if target is None:
        target = sum(scores.values()) / len(scores)
    weak = [{"skill": s, "score": scores[s], "note": f"{round(target - scores[s], 1)} below target"} for s in ordered if scores[s] < target]
    strong = [{"skill": s, "score": scores[s], "note": "at or above target"} for s in reversed(ordered) if scores[s] >= target]
    spread = scores[ordered[-1]] - scores[ordered[0]] if ordered else 0
    if not weak and spread >= .5:
        weak = [{"skill": ordered[0], "score": scores[ordered[0]], "note": "lowest of your skills (still at target)"}]
        strong = [item for item in strong if item["skill"] != ordered[0]]
    if not strong and spread >= .5:
        strong = [{"skill": ordered[-1], "score": scores[ordered[-1]], "note": "highest of your skills (still below target)"}]
        weak = [item for item in weak if item["skill"] != ordered[-1]]
    return strong, weak


def mock_insights(db: Session, user_id: int, scores: dict[str, float], overall: float, target: float | None, current_issues: list[str]) -> dict:
    """Compare with earlier assessments, name strengths and weaknesses, and estimate readiness from the trend (UC5 steps 6-7)."""
    previous = db.scalar(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.kind == "mock_exam", ResultPackage.state == "RELEASED")
                         .order_by(ResultPackage.id.desc()))
    if previous:
        prev_exam = db.scalar(select(MockExam.id).where(MockExam.package_id == previous.id))
        before = previous.payload.get("section_scores", {})
        against = f"Mock #{prev_exam} ({previous.created_at.date().isoformat()})" if prev_exam else f"your previous mock ({previous.created_at.date().isoformat()})"
        overall_change = round(overall - previous.payload.get("estimated_overall", overall), 1)
    else:
        before = latest_progress(db, user_id)["skill_scores"]
        against = "your practice average" if before else None
        overall_change = None
    comparison = {"against": against, "overall_change": overall_change,
                  "skills": {skill: {"before": before[skill], "now": scores[skill], "change": round(scores[skill] - before[skill], 1)} for skill in scores if skill in before}} if against else None
    strengths, weaknesses = split_skills(scores, target)
    history = issue_history(db, user_id)
    persistent = sorted({issue for issue in current_issues if history.get(issue)}, key=lambda issue: -history[issue])[:5]
    gap = round(target - overall, 1) if target is not None else None
    level = "Not enough data" if gap is None else "On track" if gap <= 0 else "Close to target" if gap <= .5 else "Needs further practice"
    if overall_change is None:
        trend = "This is your first mock, so there is no trend yet: take another mock in two to three weeks to see your progress."
    else:
        trend = (f"Up {overall_change} since {against}." if overall_change > 0 else f"Down {abs(overall_change)} since {against}." if overall_change < 0 else f"No change since {against}.")
    explanation = (f"Estimated {overall} against your target {target}" + (f" ({gap} to go). " if gap and gap > 0 else ". ") if target is not None else "") + trend
    if weaknesses:
        explanation += f" Focus next on {', '.join(item['skill'] for item in weaknesses[:2])}."
    return {"comparison": comparison, "strengths": strengths, "weaknesses": weaknesses, "persistent_issues": persistent,
            "readiness_detail": {"level": level, "gap": gap, "target": target, "trend": trend, "explanation": explanation}}


def progress_recommendations(progress: dict) -> list[str]:
    """Recommendations from the main skill gaps, declining trends and repeated problems (UC6 step 6)."""
    tips = [f"{item['skill'].title()} is {item['note']}: do two timed {item['skill']} tasks this week and review every comment." for item in progress["weakness_notes"][:2]]
    tips += [f"{skill.title()} is declining ({t['change']:+}): revisit your last {skill} feedback before practising again." for skill, t in progress["trends"].items()
             if t["direction"] == "declining" and skill not in progress["weaknesses"][:2]]
    tips += [f"'{item['issue']}' came up {item['count']} times in your feedback: make it your focus in the next task." for item in progress["repeated_errors"][:2]]
    return tips or ["Keep practising all four skills to maintain your level."]


# ---------------------------------------------------------------- section-by-section diagnosis for the report

TYPE_NAMES = {"completion": "Form / note / sentence completion", "mcq": "Multiple choice", "matching": "Matching", "tfng": "True / False / Not Given",
              "ynng": "Yes / No / Not Given", "headings": "Matching headings", "cwords": "Complete the Words"}

# Feedback comments are sorted into the kind of problem they describe (works for rule-based and model-written comments).
GRAMMAR_TYPES = [
    ("Subject-verb agreement", r"agreement|plural verb|singular verb|third-person|'doesn't' with|people' takes"),
    ("Plurals and uncountable nouns", r"uncountable|already plural|plural unless"),
    ("Comparatives", r"comparative"),
    ("Verb forms and tenses", r"base form|tense|past participle|verb form"),
    ("Articles (a / an / the)", r"'an' before|article"),
    ("Prepositions", r"direct object|explain to me|'for' with|preposition"),
    ("Modal verbs", r"be able to|modal"),
    ("Capital letters", r"capital"),
    ("Repeated words", r"repeated by mistake"),
    ("Sentence structure", r"long sentence|run-on|fragment|sentence structure"),
]
VOCABULARY_TYPES = [
    ("Collocation", r"collocation|'do' or 'carry out'"),
    ("Formal style", r"contraction|informal"),
    ("Linking words", r"connector|linking|cohesive"),
    ("Range of vocabulary", r"higher-level|wider range|vocabulary|word choice|repetit"),
]
TASK_TYPES = [
    ("Length", r"under length|aim for at least"),
    ("Overview", r"overview"),
    ("Clear position", r"position|opinion"),
    ("Developing ideas", r"example|develop"),
    ("Fluency", r"filler|hesitat|pause"),
]


STOPWORDS = {"about", "after", "again", "because", "before", "being", "could", "every", "other", "their", "there", "these", "thing", "things",
             "think", "those", "would", "which", "while", "where", "really", "should", "maybe", "people", "always", "usually", "something"}
MIN_WORDS_FOR_STRENGTHS = {"writing": 80, "speaking": 40}  # too little text says nothing reliable about range or accuracy


MARKERS = re.compile(r"\[[^\]]*\]\s*")  # transcript markers such as [Part 1]


def clean_sentence(text: str) -> str:
    text = MARKERS.sub("", text or "").strip()
    return text[:1].upper() + text[1:] if text else text


def classify_comment(comment: dict) -> tuple[str, str]:
    text = f"{comment.get('issue', '')} {comment.get('suggestion', '')}".lower()
    for area, table in (("grammar", GRAMMAR_TYPES), ("vocabulary", VOCABULARY_TYPES), ("task", TASK_TYPES)):
        for label, pattern in table:
            if re.search(pattern, text):
                return area, label
    return "other", comment.get("issue") or "Other"


def objective_breakdown(skill: str, detail: dict, score: float | None) -> dict:
    """Listening / reading: accuracy by question type and every missed question (not written, misspelled or wrong)."""
    review = detail.get("review", [])
    types: dict[str, dict] = {}
    for item in review:
        bucket = types.setdefault(item.get("type", "other"), {"correct": 0, "total": 0})
        bucket["correct"] += bool(item.get("correct"))
        bucket["total"] += 1
    table = sorted(({"type": TYPE_NAMES.get(k, k), "correct": v["correct"], "total": v["total"], "accuracy": round(v["correct"] / v["total"], 2)} for k, v in types.items()),
                   key=lambda row: row["accuracy"])
    missed = []
    for item in review:
        if item.get("correct"):
            continue
        given, answer = str(item.get("given") or "").strip(), str(item.get("answer") or "")
        written = item.get("type") in ("completion", "cwords")
        kind = "not written" if not given else "misspelled" if written and SequenceMatcher(None, given.lower(), answer.lower()).ratio() >= .75 else "wrong"
        missed.append({"n": item.get("n"), "question": item.get("prompt", ""), "your_answer": given, "correct_answer": answer, "kind": kind,
                       "type": TYPE_NAMES.get(item.get("type"), item.get("type")), "evidence": item.get("evidence", "")})
    counts = {kind: sum(m["kind"] == kind for m in missed) for kind in ("not written", "misspelled", "wrong")}
    raw, total = detail.get("raw_score", sum(i.get("correct", False) for i in review)), detail.get("total", len(review))
    well = [f"{row['type']}: {row['correct']}/{row['total']} correct" for row in reversed(table) if row["accuracy"] >= .7]
    poor = [f"{row['type']}: only {row['correct']}/{row['total']} correct" for row in table if row["accuracy"] < .5]
    if counts["not written"]:
        poor.append(f"{counts['not written']} question{'s' if counts['not written'] > 1 else ''} left blank" + (" (missed while listening)" if skill == "listening" else ""))
    if counts["misspelled"]:
        poor.append(f"{counts['misspelled']} answer{'s' if counts['misspelled'] > 1 else ''} nearly right but misspelled (spelling counts in the real test)")
    return {"skill": skill, "score": score, "raw": raw, "total": total, "went_well": well or (["Every question answered correctly"] if not missed else []),
            "to_improve": poor, "question_types": table, "missed": missed, "missed_counts": counts,
            "words_not_written": [m["correct_answer"] for m in missed if m["kind"] == "not written" and m["type"] == TYPE_NAMES["completion"]],
            "misspelled": [{"you_wrote": m["your_answer"], "correct": m["correct_answer"]} for m in missed if m["kind"] == "misspelled"]}


def production_breakdown(skill: str, feedback: dict, text: str, target: float | None, metrics: dict | None = None) -> dict:
    """Writing / speaking: criteria against the target, grammar errors by type with corrections, vocabulary, task and fluency."""
    from backend.scoring import find_errors, text_features
    spoken = skill == "speaking"
    criteria = feedback.get("criteria") or {}
    rows = [{"name": name.replace("_", " "), "score": value, "status": "strength" if target is not None and value >= target else "to improve"} for name, value in criteria.items()]
    text = MARKERS.sub("", text or "")
    comments = [{**c, "sentence": clean_sentence(c.get("sentence", "")), "correction": clean_sentence(c.get("correction", ""))} for c in feedback.get("comments") or []]
    # Re-check the full text so no grammar error is lost to the comment limit.
    if text:
        known = {(c.get("sentence", "").lower(), c.get("issue")) for c in comments}
        comments += [{**e, "sentence": clean_sentence(e.get("sentence", "")), "correction": clean_sentence(e.get("correction", ""))}
                     for e in find_errors(text, spoken) if (clean_sentence(e.get("sentence", "")).lower(), e.get("issue")) not in known]
    groups: dict[tuple[str, str], list[dict]] = {}
    for comment in comments:
        groups.setdefault(classify_comment(comment), []).append(comment)
    def listing(area: str) -> list[dict]:
        rows = []
        for (kind, label), items in groups.items():
            if kind != area:
                continue
            distinct = {(c.get("sentence", "").lower(), c.get("issue")): c for c in items}  # one error per sentence and rule
            examples = {}
            for c in distinct.values():  # show each sentence once, however many errors it has
                if c.get("sentence") and c["sentence"] not in examples:
                    examples[c["sentence"]] = {"sentence": c["sentence"], "correction": c.get("correction", "")}
            rows.append({"type": label, "count": len(distinct), "advice": items[0].get("suggestion", ""), "examples": list(examples.values())[:3]})
        return sorted(rows, key=lambda row: -row["count"])
    grammar, vocabulary, task = listing("grammar"), listing("vocabulary"), listing("task") + listing("other")
    stats = {**(text_features(text, spoken=spoken) if text else {}), **(feedback.get("analysis") or {})}
    words = re.findall(r"[a-z][a-z']+", re.sub(r"\[[^\]]*\]", " ", (text or "").lower()))  # drop markers such as [Part 1]
    repeated = [w for w, n in Counter(w for w in words if len(w) > 4 and w not in STOPWORDS).most_common(4) if n >= (4 if spoken else 3)]
    enough = len(words) >= MIN_WORDS_FOR_STRENGTHS[skill]
    vocab = {"words": stats.get("words", len(words)), "lexical_diversity": stats.get("lexical_diversity"), "academic_words": stats.get("academic_words", [])[:8],
             "linker_variety": stats.get("linker_variety"), "repeated_words": repeated}
    well = [f"{row['name'].title()} {row['score']} (at or above your target)" for row in rows if row["status"] == "strength"]
    poor: list[str] = []
    if enough and (vocab["lexical_diversity"] or 0) >= .65:
        well.append(f"Varied vocabulary (diversity {vocab['lexical_diversity']})")
    if vocab["academic_words"]:
        well.append("Uses academic words: " + ", ".join(vocab["academic_words"][:5]))
    if enough and (vocab["linker_variety"] or 0) >= 3:
        well.append(f"Good range of linking words ({vocab['linker_variety']} different)")
    if enough and (stats.get("complex_per_sentence") or 0) >= .5:
        well.append("Mixes in complex sentences")
    if enough and not grammar:
        well.append("No grammar errors found")
    if text and not enough:
        poor.insert(0, f"Only {len(words)} words: too little to show your range (aim for {'250+ words' if skill == 'writing' else 'longer, developed answers'})")
    poor += [f"{row['name'].title()} {row['score']} (below your target {target})" for row in rows if row["status"] == "to improve" and target is not None]
    poor += [f"Grammar - {row['type']}: {row['count']} error{'s' if row['count'] > 1 else ''}" for row in grammar[:4]]
    poor += [f"Vocabulary - {row['type']}" for row in vocabulary[:3]]
    if repeated:
        poor.append("Repeats the same words: " + ", ".join(repeated))
    poor += [row["type"] for row in task[:3]]
    fluency = None
    if spoken:
        m = metrics or {}
        fluency = {"words_per_minute": m.get("words_per_minute") or stats.get("words_per_minute"), "fillers": m.get("fillers", stats.get("fillers")),
                   "turns": m.get("turns"), "average_turn_words": m.get("average_turn_words"), "part2_words": m.get("long_turn_words")}
        if fluency["part2_words"] is not None:
            (well if fluency["part2_words"] >= 170 else poor).append(f"Part 2 long turn: {fluency['part2_words']} words" + ("" if fluency["part2_words"] >= 170 else " (aim for about 200 words in two minutes)"))
        if fluency["average_turn_words"] is not None and fluency["average_turn_words"] < 25:
            poor.append(f"Short answers: about {fluency['average_turn_words']} words per answer (extend with a reason and an example)")
        wpm = fluency["words_per_minute"]
        if wpm and 110 <= wpm <= 170:
            well.append(f"Natural speaking pace ({wpm} words per minute)")
        elif wpm:
            poor.append(f"Speaking pace {wpm} words per minute ({'too slow' if wpm < 110 else 'very fast'}; aim for about 120-160)")
        if fluency["fillers"] is not None:
            (well if fluency["fillers"] <= 2 else poor).append(f"{fluency['fillers']} filler words (um, er, you know)")
    return {"skill": skill, "criteria": rows, "went_well": well, "to_improve": poor, "grammar": grammar, "vocabulary": {**vocab, "issues": vocabulary},
            "task_issues": task, "fluency": fluency,
            "better_sentences": list({clean_sentence(b.get("original", "")): {"original": clean_sentence(b.get("original", "")), "improved": clean_sentence(b.get("improved", ""))}
                                      for b in feedback.get("improved_sentences") or [] if b.get("original")}.values())[:4],
            "pronunciation_note": feedback.get("pronunciation_note")}


def mock_section_report(payload: dict, texts: dict, target: float | None) -> dict:
    """The four sections of one marked mock exam."""
    details, scores = payload.get("details", {}), payload.get("section_scores", {})
    sections = {skill: objective_breakdown(skill, details.get(skill, {}), scores.get(skill)) for skill in ("listening", "reading")}
    tasks = []
    for task, feedback in (details.get("writing") or {}).items():
        tasks.append({"task": task, "band": feedback.get("band"), **production_breakdown("writing", feedback, texts.get(f"writing:{task}", ""), target)})
    label = (lambda t: f"{t['task'].replace('task', 'Task ')}: ") if len(tasks) > 1 else (lambda t: "")  # name the task only when there are two
    sections["writing"] = {"skill": "writing", "score": scores.get("writing"), "tasks": tasks,
                           "went_well": [f"{label(t)}{item}" for t in tasks for item in t["went_well"]],
                           "to_improve": [f"{label(t)}{item}" for t in tasks for item in t["to_improve"]]}
    speaking = details.get("speaking") or {}
    sections["speaking"] = {**production_breakdown("speaking", speaking, texts.get("speaking", ""), target, speaking.get("metrics")), "score": scores.get("speaking")}
    return sections


def practice_section_report(db: Session, user_id: int, target: float | None) -> dict:
    """Without a mock: the latest verified result in each skill."""
    from backend.models import Submission
    sections = {}
    for skill in ("listening", "reading", "writing", "speaking"):
        package = db.scalar(select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.kind == skill, ResultPackage.state == "RELEASED").order_by(ResultPackage.id.desc()))
        if not package:
            continue
        payload = package.payload or {}
        if skill in ("listening", "reading"):
            sections[skill] = objective_breakdown(skill, payload, payload.get("estimated_overall"))
        else:
            text = db.scalar(select(Submission.text).where(Submission.package_id == package.id)) or ""
            sections[skill] = {**production_breakdown(skill, payload, text, target, payload.get("metrics")), "score": payload.get("estimated_overall")}
        sections[skill]["source"] = f"Latest {skill} practice ({package.created_at.date().isoformat()})"
    return sections


def learning_patterns(db: Session, user_id: int) -> dict:
    """Patterns across all verified practice: most-missed question types and repeated grammar problems."""
    from backend import notebook
    summary = notebook.stats(db, user_id)
    return {"mistakes_by_type": summary.get("mistakes_by_type", [])[:5], "grammar_issues": summary.get("grammar_issues", [])[:5]}


# ---------------------------------------------------------------- answer-key marking (listening and reading)

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
