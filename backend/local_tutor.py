"""Offline conversational tutor used when no cloud language model is configured.

It recognises common learner intents (exam strategy, task types, vocabulary,
sentence checks, plans and goals) and, in Speaking, keeps an IELTS-style
conversation going with gentle corrections. It is transparent about being a
built-in engine and never invents scores.
"""
import random
import re
from backend.content.ielts_production import PART1_TOPICS, PART2_CARDS
from backend.scoring import find_errors

SYNONYMS = {
    "important": ["crucial", "essential", "vital", "significant"], "good": ["beneficial", "advantageous", "valuable", "favourable"],
    "bad": ["detrimental", "harmful", "undesirable", "adverse"], "big": ["substantial", "considerable", "significant", "sizeable"],
    "increase": ["rise", "grow", "climb", "surge"], "decrease": ["fall", "decline", "drop", "dip"], "show": ["illustrate", "demonstrate", "indicate", "reveal"],
    "think": ["believe", "argue", "maintain", "contend"], "help": ["assist", "support", "facilitate", "enable"], "many": ["numerous", "a large number of", "a wide range of"],
    "problem": ["issue", "challenge", "difficulty", "drawback"], "use": ["employ", "utilise", "make use of", "rely on"], "change": ["transform", "alter", "shift", "modify"],
    "happy": ["delighted", "content", "thrilled", "over the moon"], "interesting": ["fascinating", "engaging", "intriguing", "compelling"],
}
TIPS = {
    "tfng": "For TRUE / FALSE / NOT GIVEN: find the sentence that matches the statement's topic. TRUE means it says the same thing, FALSE means it says the opposite, and NOT GIVEN means the passage doesn't say either way. Don't use your own knowledge.",
    "headings": "For Matching Headings: read each paragraph's first and last sentences, decide its main idea, then match. Ignore headings that only match a detail.",
    "completion": "For completion tasks: predict the word type (noun, number, adjective) before listening or reading, respect the word limit, and check spelling. Answers usually follow the order of the recording or passage.",
    "task1": "Writing Task 1: paraphrase the chart in your introduction, write a clear overview of the main trends (no numbers needed), then two body paragraphs comparing key figures. Aim for 150-190 words; don't give opinions.",
    "task2": "Writing Task 2: answer every part of the question, state your position in the introduction, give each body paragraph one main idea with an explanation and an example, and finish with a conclusion that restates your view. Aim for 260-300 words.",
    "part2": "Speaking Part 2: use the one minute to note keywords for each bullet point. Speak for the full two minutes by adding a story, feelings and a reason for each bullet. If you finish early, explain why it matters to you now.",
    "part3": "Speaking Part 3: give an opinion, explain the reason, add an example, and consider another point of view. Phrases like 'It depends on...' and 'On the other hand...' help you develop ideas.",
    "listening": "Listening: read ahead during the pauses, underline keywords, and listen for corrections such as 'actually' or 'sorry, I mean'. The second piece of information is often the answer.",
    "reading": "Reading: skim each passage in two minutes, then scan for keywords from each question. Spend about 20 minutes per passage and never leave a blank.",
    "fluency": "To speak more fluently, extend each answer with 'because' and 'for example', use fillers like 'Let me think...' instead of silence, and practise answering timed questions daily.",
    "vocabulary": "Build vocabulary by topic (environment, technology, education). Learn collocations, such as 'make a decision' and 'heavy traffic', and reuse new words in your own sentences the same day.",
    "time": "Time management: in Writing spend about 20 minutes on Task 1 and 40 on Task 2, in Reading about 20 minutes per passage, and in Listening use every pause to read the next questions.",
}
KEYWORDS = [("tfng", ["true false", "not given", "tfng", "yes no"]), ("headings", ["heading"]), ("completion", ["completion", "fill in", "gap", "blank"]),
            ("task1", ["task 1", "task1", "chart", "graph", "table", "diagram"]), ("task2", ["task 2", "task2", "essay", "opinion essay"]),
            ("part2", ["part 2", "part2", "cue card", "long turn"]), ("part3", ["part 3", "part3", "discussion"]),
            ("listening", ["listening", "listen"]), ("reading", ["reading", "passage"]), ("fluency", ["fluent", "fluency", "nervous", "hesitat"]),
            ("vocabulary", ["vocabulary", "words", "lexical"]), ("time", ["time", "manage", "minutes"])]


def _first_name(persona: str) -> str:
    return "Kai" if persona == "boy" else "Luna"


def _check_sentence(message: str) -> str | None:
    errors = find_errors(message, spoken=True)
    if not errors:
        return None
    first = errors[0]
    fix = f" Try: \"{first['correction']}\"" if first.get("correction") else ""
    return f"Small correction: {first['suggestion']}{fix}"


def reply(context: str, message: str, profile: dict, plan: dict | None, history: list[dict], persona: str = "witch") -> str:
    lower = message.lower().strip()
    name = _first_name(persona)
    rng = random.Random(len(history) * 7 + len(message))
    skill = context if context in ("speaking", "writing", "reading", "listening") else None
    if re.search(r"[一-鿿]", message):
        prefix = "I'll answer in English so you get extra practice. "
    else:
        prefix = ""

    synonym = re.search(r"(?:synonym|another word|other word|instead of|replace)\s+(?:for\s+)?['\"]?([a-z]+)", lower)
    if synonym and synonym.group(1) in SYNONYMS:
        word = synonym.group(1)
        return prefix + f"Instead of '{word}', try: {', '.join(SYNONYMS[word])}. Choose the one that fits the formality of your sentence. Can you write a sentence using one of them?"
    check = re.match(r"(?:check|correct|is this correct|is this right)[:\s]+(.+)", message, flags=re.I)
    if check:
        verdict = _check_sentence(check.group(1))
        return prefix + (verdict or "I couldn't find any common errors in that sentence. Nice work! To raise it further, try adding a subordinate clause or a more precise word.")

    if skill == "speaking":
        if not history or any(word in lower for word in ("start", "hello", "hi ", "practice", "practise", "question")) and len(lower.split()) < 6:
            topic = PART1_TOPICS[rng.randrange(len(PART1_TOPICS))]
            return prefix + f"Hi, I'm {name}! Let's have a relaxed speaking practice. We'll talk about {topic['topic']}. {topic['questions'][0]}"
        asked = len([item for item in history if item.get("role") == "assistant"])
        correction = _check_sentence(message)
        words = len(message.split())
        if words < 8:
            follow = "Could you say a bit more? Try adding a reason with 'because' and an example."
        else:
            nouns = [w for w in re.findall(r"[a-zA-Z]{5,}", message) if w.lower() not in {"because", "really", "think", "would", "there", "about", "which", "maybe", "actually"}]
            echo = f"Interesting point about {nouns[-1].lower()}. " if nouns else "Thanks for sharing that. "
            if asked % 4 == 3:
                card = PART2_CARDS[rng.randrange(len(PART2_CARDS))]
                follow = echo + f"Let's try a longer answer, like Part 2. {card['cue']} Talk for about a minute."
            else:
                topic = PART1_TOPICS[(asked + rng.randrange(3)) % len(PART1_TOPICS)]
                follow = echo + topic["questions"][asked % len(topic["questions"])]
        return prefix + (correction + " " if correction else "") + follow

    for key, words in KEYWORDS:
        if any(word in lower for word in words):
            return prefix + TIPS[key] + " Would you like a practice question on this?"

    priorities = ", ".join(profile.get("priority_skills", [])) or "your chosen skills"
    if "plan" in lower or "schedule" in lower or "week" in lower:
        if plan:
            activities = "; ".join(f"{item.get('skill')}: {item.get('minutes_per_week')} min" for item in plan.get("activities", [])[:4])
            return prefix + f"Your active plan is '{plan.get('title')}'. Weekly time: {activities}. Want me to suggest what to do today?"
        return prefix + f"You don't have an active plan yet. Open Learning plan and generate one; I'll build it around {priorities} and your {profile.get('weekly_hours')} hours a week."
    if any(word in lower for word in ("goal", "profile", "target", "score", "band")):
        return prefix + f"Your goal is {profile.get('exam')} {profile.get('target_score')} by {profile.get('exam_date')}, starting from a self-reported {profile.get('proficiency')} level. Your priorities are {priorities}."
    if any(word in lower for word in ("today", "what should", "next", "start")):
        focus = (profile.get("priority_skills") or ["writing"])[0]
        return prefix + f"Today, try one {focus} task from the Question bank, then review the feedback and redo your weakest part. Short daily practice beats one long session."
    if skill:
        return prefix + TIPS.get(skill, TIPS["task2"]) + " Tell me which question type you find hardest."
    return prefix + f"I'm {name}, your study companion. Ask me about question types, strategies, vocabulary, your plan, or type 'check: your sentence' and I'll look for mistakes. Your priorities are {priorities}."
