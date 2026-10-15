"""Live speaking-test examiner.

A deterministic state machine guarantees the real test structure (IELTS Parts
1-3 with one-minute preparation and a two-minute long turn; TOEFL 2026 Listen
and Repeat followed by Take an Interview). When a cloud model is configured it
may phrase transitions and choose natural follow-up questions, but it can never
skip a part or change the timing.
"""
import random
from typing import Callable

PERSONAS = {"witch": "Luna", "boy": "Kai"}
P1_FOLLOW = ["Why is that?", "Could you tell me a little more about that?", "Why do you say that?", "Can you give me an example?"]
P3_FOLLOW = ["Can you give me an example of that?", "Why do you think that is?", "How might that change in the future?", "Is that true for everyone, do you think?"]

# rephrase(stage, scripted_text, learner_text, allow_followup) -> (text, used_followup) or None
Rephrase = Callable[[str, str, str, bool], "tuple[str, bool] | None"]


def _words(text: str) -> int:
    return len((text or "").split())


def start(test: dict, persona: str) -> tuple[dict, str, dict]:
    name = PERSONAS.get(persona, "Luna")
    if test["exam"] == "TOEFL":
        state = {"stage": "repeat", "i": 0, "scores": []}
        first = test["repeat"][0]["text"]
        text = (f"Hello, I'm {name}, and I'll guide you through the speaking section. First is Listen and Repeat. "
                f"You will hear a sentence once. Repeat it exactly as you heard it. Here is the first sentence. {first}")
        return state, text, ui(test, state)
    state = {"stage": "intro", "topic": 0, "q": 0, "followed": False}
    text = f"Good afternoon. My name is {name}, and I'll be your examiner today. Could you tell me your full name, please?"
    return state, text, ui(test, state)


def ui(test: dict, state: dict) -> dict:
    stage = state["stage"]
    if test["exam"] == "TOEFL":
        if stage == "repeat":
            return {"part": "Listen and Repeat", "stage": stage, "progress": f"{state['i'] + 1}/{len(test['repeat'])}", "timer": {"kind": "answer", "seconds": 15}}
        if stage == "interview":
            return {"part": "Take an Interview", "stage": stage, "progress": f"{state['i'] + 1}/{len(test['interview']['questions'])}", "timer": {"kind": "answer", "seconds": test.get("answer_seconds", 45)}}
        return {"part": "Complete", "stage": "done"}
    part = {"intro": "Introduction", "p1": "Part 1", "p2_prep": "Part 2", "p2_talk": "Part 2", "p2_close": "Part 2", "p3": "Part 3", "done": "Complete"}[stage]
    result = {"part": part, "stage": stage}
    if stage.startswith("p2"):
        result["cue_card"] = test["part2"]
    if stage == "p2_prep":
        result["timer"] = {"kind": "prep", "seconds": test.get("prep_seconds", 60)}
    elif stage == "p2_talk":
        result["timer"] = {"kind": "talk", "seconds": test.get("talk_seconds", 120)}
    elif stage == "p1":
        result["progress"] = f"Topic {state['topic'] + 1} · Question {state['q'] + 1}"
    elif stage == "p3":
        result["progress"] = f"Question {state['q'] + 1}/{len(test['part3']['questions'])}"
    return result


def advance(test: dict, state: dict, learner_text: str, event: str = "answer", rephrase: Rephrase | None = None, rng: random.Random | None = None) -> tuple[dict, str, dict, bool, dict]:
    """Return (state, examiner_text, ui, done, turn_meta)."""
    rng = rng or random.Random()
    state = dict(state)
    meta: dict = {}
    if test["exam"] == "TOEFL":
        return _advance_toefl(test, state, learner_text, meta)

    def phrase(stage: str, scripted: str, allow_followup: bool, followups: list[str]) -> tuple[str, bool]:
        if rephrase:
            try:
                result = rephrase(stage, scripted, learner_text, allow_followup)
                if result and result[0].strip():
                    return result
            except Exception:
                pass
        if allow_followup:
            return rng.choice(followups), True
        return scripted, False

    stage = state["stage"]
    if stage == "intro":
        topic = test["part1"][0]
        state.update(stage="p1", topic=0, q=0, followed=False)
        text = f"Thank you. Now, in this first part, I'd like to ask you some questions about yourself. Let's talk about {topic['topic']}. {topic['questions'][0]}"
        return state, text, ui(test, state), False, meta

    if stage == "p1":
        topics = test["part1"]
        short = _words(learner_text) < 8 and not state.get("followed")
        nxt_topic, nxt_q = state["topic"], state["q"] + 1
        if nxt_q >= len(topics[nxt_topic]["questions"]):
            nxt_topic, nxt_q = nxt_topic + 1, 0
        if nxt_topic >= len(topics):
            scripted = None
        elif nxt_q == 0:
            scripted = f"Now let's talk about {topics[nxt_topic]['topic']}. {topics[nxt_topic]['questions'][0]}"
        else:
            scripted = topics[nxt_topic]["questions"][nxt_q]
        if scripted:
            text, followed = phrase("part1", scripted, short, P1_FOLLOW)
            if followed:
                state["followed"] = True
                return state, text, ui(test, state), False, {"follow_up": True}
            state.update(topic=nxt_topic, q=nxt_q, followed=False)
            return state, text, ui(test, state), False, meta
        state.update(stage="p2_prep")
        card = test["part2"]
        text = ("Thank you. Now, I'm going to give you a topic, and I'd like you to talk about it for one to two minutes. "
                "Before you talk, you'll have one minute to think about what you're going to say. You can make some notes if you wish. "
                f"Here is your topic. {card['cue']} You should say: {', '.join(card['bullets'][:-1])}, {card['bullets'][-1]}.")
        return state, text, ui(test, state), False, meta

    if stage == "p2_prep":
        state["stage"] = "p2_talk"
        text = "All right? Remember, you have one to two minutes for this, so don't worry if I stop you. I'll tell you when the time is up. Can you start speaking now, please?"
        return state, text, ui(test, state), False, meta

    if stage == "p2_talk":
        state["stage"] = "p2_close"
        text = f"Thank you. {test['part2']['closing']}"
        meta["long_turn"] = True
        return state, text, ui(test, state), False, meta

    if stage == "p2_close":
        state.update(stage="p3", q=0, followed=False)
        p3 = test["part3"]
        text = f"Thank you. We've been talking about {test['part2']['topic']}, and I'd like to discuss with you one or two more general questions related to this. Let's consider {p3['theme']}. {p3['questions'][0]}"
        return state, text, ui(test, state), False, meta

    if stage == "p3":
        questions = test["part3"]["questions"]
        short = _words(learner_text) < 20 and not state.get("followed")
        nxt = state["q"] + 1
        if nxt < len(questions) or short:
            scripted = questions[nxt] if nxt < len(questions) else ""
            text, followed = phrase("part3", scripted or rng.choice(P3_FOLLOW), short, P3_FOLLOW)
            if followed or nxt >= len(questions):
                state["followed"] = True
                return state, text, ui(test, state), False, {"follow_up": True}
            state.update(q=nxt, followed=False)
            return state, text, ui(test, state), False, meta
        state["stage"] = "done"
        return state, "Thank you very much. That is the end of the speaking test. I'll prepare your feedback now.", ui(test, state), True, meta

    return state, "The speaking test has finished.", ui(test, state), True, meta


def _advance_toefl(test: dict, state: dict, learner_text: str, meta: dict):
    from backend.scoring import repeat_accuracy
    if state["stage"] == "repeat":
        target = test["repeat"][state["i"]]["text"]
        accuracy = repeat_accuracy(target, learner_text)
        state["scores"] = state.get("scores", []) + [accuracy]
        meta.update(repeat_target=target, repeat_accuracy=accuracy)
        nxt = state["i"] + 1
        if nxt < len(test["repeat"]):
            state["i"] = nxt
            return state, f"Next sentence. {test['repeat'][nxt]['text']}", ui(test, state), False, meta
        state.update(stage="interview", i=0)
        interview = test["interview"]
        text = (f"Well done. Now, Take an Interview. {interview['scenario']} You will have {test.get('answer_seconds', 45)} seconds to answer each question. "
                f"{interview['questions'][0]}")
        return state, text, ui(test, state), False, meta
    if state["stage"] == "interview":
        nxt = state["i"] + 1
        questions = test["interview"]["questions"]
        if nxt < len(questions):
            state["i"] = nxt
            return state, questions[nxt], ui(test, state), False, meta
        state["stage"] = "done"
        return state, "Thank you. That completes the speaking section. I'll prepare your feedback now.", ui(test, state), True, meta
    return state, "The speaking section has finished.", ui(test, state), True, meta


def transcript_for_assessment(test: dict, log: list[dict]) -> tuple[str, dict]:
    """Join the learner's turns and compute delivery metrics from client timings."""
    turns = [item for item in log if item.get("role") == "learner" and item.get("stage") not in ("intro", "repeat") and item.get("text", "").strip()]
    text = "\n".join(f"[{item.get('part', '')}] {item['text']}" for item in turns)
    words = sum(len(item["text"].split()) for item in turns)
    seconds = sum(float(item.get("seconds") or 0) for item in turns)
    metrics = {"turns": len(turns), "speaking_seconds": round(seconds), "average_turn_words": round(words / len(turns), 1) if turns else 0}
    if seconds >= 10:
        metrics["words_per_minute"] = round(words / seconds * 60)
    repeats = [item["repeat_accuracy"] for item in log if isinstance(item.get("repeat_accuracy"), (int, float))]
    if repeats:
        metrics["repeat_accuracy"] = round(sum(repeats) / len(repeats), 2)
    long_turn = next((item for item in turns if item.get("stage") == "p2_talk"), None)
    if long_turn:
        metrics["long_turn_words"] = len(long_turn["text"].split())
    return text, metrics
