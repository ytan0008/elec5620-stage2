"""Executable StateGraphs. All model access goes through ProviderAdapter.

ProviderAdapter runs in one of two modes:
  REAL  - a configured OpenAI-compatible chat model produces structured output.
  LOCAL - the built-in engine: curated exam content, rule-based language
          analysis and a scripted examiner. No network access is needed.
"""
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.config import settings
from backend.models import AgentEvent, AuditLog, Escalation, QualityCheck, ResultPackage, SystemSetting
from backend.schemas import (FeedbackOutput, PlanOutput, VerdictOutput, RecommendationOutput, ReportNarrative, OnboardingExtraction, PortraitOutput,
                             QuestionOutput, AgentChatReply, ExaminerTurn, ListeningGen, ReadingGen, SpeakingGen)
from backend.onboarding import parse_demo_message
from backend import content as bank
from backend import local_tutor
from backend.scoring import analyse_response, validate_test


class LocalGenerationUnavailable(Exception):
    """Raised when a request needs a cloud model in LOCAL mode."""


class FlowState(TypedDict, total=False):
    user_id: int
    workflow: str
    profile: dict
    progress: dict
    skill: str
    text: str
    prompt: str
    task: str
    metrics: dict
    scenario: str
    output: dict
    package_id: int
    issues: list[str]
    route: str
    source_mode: str


@tool
def priority_tool(priority_skills: list[str], weakness_skills: list[str]) -> list[str]:
    """Order learning skills by observed weaknesses and learner priorities."""
    return list(dict.fromkeys(weakness_skills + priority_skills + ["writing", "speaking", "reading", "listening"]))


@tool
def criterion_average(scores: dict[str, float]) -> float:
    """Compute an indicative mean of assessed criteria, rounded to a half point."""
    return round((sum(scores.values()) / len(scores)) * 2) / 2 if scores else 0.0


PERSONA_STYLE = {
    "witch": "You are Luna, a warm, witty pixel-art witch who tutors English with a light touch of magic metaphors.",
    "boy": "You are Kai, a friendly, upbeat pixel-art boy who tutors English like an encouraging study buddy.",
}
RUBRICS = {
    "IELTS": "IELTS band descriptors (0-9): Task Response/Achievement (addresses all parts, clear position or overview, developed ideas), "
             "Coherence and Cohesion (logical paragraphing, range of cohesive devices without overuse), Lexical Resource (range, precision, collocation, spelling), "
             "Grammatical Range and Accuracy (mix of complex structures, frequency of errors). Speaking Fluency and Coherence covers length of turn, hesitation and discourse markers.",
    "TOEFL": "TOEFL iBT 2026 section scale 1-6: task fulfilment (addresses all requirements, elaborated ideas), organisation (clear progression), "
             "language use (range and accuracy of vocabulary and grammar). Speaking topic development covers relevance, elaboration and coherence.",
}


class ProviderAdapter:
    def __init__(self):
        self.config = settings()
        self.mode = self.config.ai_mode
        self.llm = None
        if self.mode == "REAL":
            self.llm = ChatOpenAI(model=self.config.llm_model, api_key=self.config.openai_api_key, base_url=self.config.openai_base_url or None, timeout=60, max_retries=1)

    @property
    def local(self) -> bool:
        return self.mode == "LOCAL"

    def structured(self, schema, system: str, user: dict, local: dict):
        if self.local:
            return schema.model_validate(local)
        # Callers pass only exam goals, learning text and scores; account identity is excluded.
        chain = self.llm.with_structured_output(schema)
        messages = [("system", system), ("human", json.dumps(user, ensure_ascii=False))]
        try:
            return chain.invoke(messages)
        except Exception:
            return chain.invoke(messages)  # One bounded retry before the caller holds the result.

    def extract_onboarding(self, message: str, draft: dict) -> OnboardingExtraction:
        return self.structured(
            OnboardingExtraction,
            "Extract only explicitly stated IELTS/TOEFL learner goals from the latest message. "
            "Do not invent missing values. Dates must be YYYY-MM-DD. Skills must be writing, speaking, reading or listening. "
            "Return null for fields not supplied in the latest message.",
            {"latest_message": message, "current_draft": draft, "today": datetime.now(timezone.utc).date().isoformat()}, parse_demo_message(message, draft),
        )

    def chat(self, context: str, message: str, profile: dict, plan: dict | None, history: list[dict], persona: str = "witch") -> AgentChatReply:
        """Instructional conversation; formal scores and plans use the verified workflows."""
        local = local_tutor.reply(context, message, profile, plan, history, persona)
        if self.local:
            return AgentChatReply(reply=local)
        skill = context if context in ("speaking", "writing", "reading", "listening") else None
        role = "AI Tutor" if skill else "Learning Coordinator"
        speaking_rules = ("This is a spoken conversation practice: reply in 1-3 short natural sentences (under 70 words) that will be read aloud. "
                          "React to what the learner said, gently correct at most one clear grammar or vocabulary mistake by recasting it, then ask one follow-up question. "
                          "Use IELTS Speaking Part 1/3 style topics. No markdown, lists or emojis.") if skill == "speaking" else \
                         "Be concise (under 150 words), practical and warm; ask at most one follow-up. Plain text only, no markdown tables."
        return self.structured(
            AgentChatReply,
            f"{PERSONA_STYLE.get(persona, PERSONA_STYLE['witch'])} You act as the {role} of an IELTS/TOEFL preparation platform; the current page is '{context}'. "
            f"{speaking_rules} Do not claim an official IELTS/TOEFL score or calibrated confidence. Formal evaluations come from the separate quality-checked "
            "workflow. If the learner writes in another language, answer in simple English and optionally add a brief translation. Never ask for passwords or identity details.",
            {"message": message, "profile": profile, "active_plan": plan, "recent_messages": history[-10:]},
            {"reply": local},
        )

    def examiner_rephrase(self, stage: str, scripted: str, learner_text: str, allow_followup: bool, persona: str):
        """Let a cloud model phrase the next examiner turn naturally. LOCAL mode keeps the script."""
        if self.local:
            return None
        rules = ("You are a certified IELTS Speaking examiner. Never give feedback, praise or scores during the test. "
                 "Reply with exactly what the examiner says next in under 45 words, plain text.")
        task = (f"Stage: {stage}. The candidate just said: \"{learner_text[:600]}\". The next scripted question is: \"{scripted}\". "
                + ("The answer was short: you may ask ONE brief natural follow-up about what they said instead (set follow_up true), or move on with the scripted question. "
                   if allow_followup else "You must move on by asking the scripted question, optionally preceded by a two-to-four word acknowledgement such as 'Thank you.'. Set follow_up false."))
        result = self.llm.with_structured_output(ExaminerTurn).invoke([("system", rules), ("human", task)])
        if not result.follow_up and scripted and scripted.split("?")[0][-25:].lower() not in result.say.lower():
            return (scripted, False)  # The model must not drop the scripted question.
        return (result.say, result.follow_up)

    def portrait(self, profile: dict) -> PortraitOutput:
        priorities = profile["priority_skills"]
        local = {
            "summary": f"Starting portrait for a {profile['proficiency']} {profile['exam']} learner aiming for {profile['target_score']}. It reflects stated goals until verified practice results arrive.",
            "goal": f"Reach an estimated {profile['target_score']} by {profile['exam_date']}.",
            "focus_areas": priorities,
            "starting_point": f"Self-reported {profile['proficiency']} level; confirm with a first practice task in each priority skill.",
            "study_rhythm": f"{profile['weekly_hours']} hours per week, about {round(profile['weekly_hours'] * 60 / 6)} minutes on six days.",
            "next_steps": [f"Complete a {skill} diagnostic task from the question bank" for skill in priorities[:2]] + ["Take a short mock test after two weeks"],
            "confidence": {"portrait": .84},
        }
        return self.structured(
            PortraitOutput,
            "You are the Learning Coordinator. Create a concise learning portrait from stated goals only. "
            "Never claim a measured strength without verified performance. Give a self-reported heuristic confidence.",
            {"profile": profile}, local,
        )

    # ---------------------------------------------------------------- content
    def generate_question(self, exam: str, skill: str, topic: str, task: str = "auto") -> dict:
        """Return {title, task_type, prompt, content, confidence} for a new original item."""
        rng = random.Random(hash((exam, skill, topic, task, time.time())))
        if skill == "writing":
            return self._generate_writing(exam, topic, task, rng)
        if skill == "speaking":
            return self._generate_speaking(exam, topic, rng)
        if self.local:
            raise LocalGenerationUnavailable("Generating brand-new listening or reading tests needs a cloud AI model. Configure OPENAI_API_KEY, or practise with the built-in tests.")
        part = {"auto": 0, "part1": 1, "part2": 2, "part3": 3, "part4": 4}.get(task, 0) or rng.choice([1, 2, 3, 4])
        if skill == "listening":
            spec = {1: "Part 1: a phone or face-to-face conversation between two people in an everyday social context (booking, enquiry); 10 form/note completion questions, ONE WORD AND/OR A NUMBER, answers include spelled names and numbers.",
                    2: "Part 2: a monologue in an everyday context (tour guide, radio talk); 5 multiple-choice (A-C) questions then 5 matching questions with a shared A-G option box.",
                    3: "Part 3: a discussion between two students and a tutor about an academic assignment; 5 multiple-choice questions then 5 matching questions.",
                    4: "Part 4: an academic lecture by one speaker; 10 note-completion questions, ONE WORD ONLY."}[part] if exam == "IELTS" else \
                "A TOEFL 2026 listening set: a campus conversation or academic talk (300-450 words) with 5 multiple-choice (A-D) questions."
            output = self.structured(ListeningGen,
                f"Write ONE ORIGINAL {exam} Listening section about '{topic}'. {spec} The script must be 450-750 words of natural spoken English with "
                "hesitations, corrections and distractors (a speaker mentions a wrong detail and then corrects it). Start with a narrator line introducing the situation "
                "and add narrator lines for reading time. Every completion answer must appear verbatim in the script and respect the word limit; put alternative spellings in accepts. "
                "Use voices: narrator, female, male, female2, male2 (different speakers different voices). Number questions from 1. Evidence must quote the script. "
                "Never copy published test material. Return a self-reported confidence {\"test\": 0-1}.",
                {"exam": exam, "topic": topic, "part": part}, {}).model_dump()
            item = {"id": f"gen-listening-{int(time.time())}", "kind": "listening", "exam": exam, "part": part, "topic": topic, **{k: output[k] for k in ("title", "context", "script", "groups")}}
            return {"title": output["title"], "task_type": f"Listening Part {part}" if exam == "IELTS" else "Listening set", "prompt": output["context"], "content": item, "confidence": output["confidence"]}
        output = self.structured(ReadingGen,
            f"Write ONE ORIGINAL {exam} Academic Reading passage about '{topic}' (650-850 words, 5-7 paragraphs labelled A-G when using heading matching). "
            "Then write 13 questions in 2-3 groups using authentic types: TRUE/FALSE/NOT GIVEN (tfng), YES/NO/NOT GIVEN (ynng), matching headings (matching, roman numeral keys with 2 extra headings), "
            "multiple choice A-D (mcq) and sentence/summary completion (completion, answers copied verbatim from the passage, max two words). Include believable distractors. "
            "Evidence must quote the passage. Never copy published material. Return a self-reported confidence {\"test\": 0-1}." if exam == "IELTS" else
            f"Write ONE ORIGINAL TOEFL 2026 'Read an Academic Passage' text about '{topic}' (about 200-280 words, 3 paragraphs) with 5 multiple-choice (A-D) questions including one vocabulary-in-context item. "
            "Evidence must quote the passage. Return a self-reported confidence {\"test\": 0-1}.",
            {"exam": exam, "topic": topic}, {}).model_dump()
        item = {"id": f"gen-reading-{int(time.time())}", "kind": "reading", "exam": exam, "part": 1, "topic": topic, "minutes": 20 if exam == "IELTS" else 8,
                **{k: output[k] for k in ("title", "passage", "groups")}}
        return {"title": output["title"], "task_type": "Academic Reading passage" if exam == "IELTS" else "Academic passage", "prompt": f"{output['title']}: {sum(len(g['questions']) for g in output['groups'])} questions.", "content": item, "confidence": output["confidence"]}

    def _generate_writing(self, exam: str, topic: str, task: str, rng: random.Random) -> dict:
        if exam == "TOEFL":
            task = task if task in ("email", "discussion") else rng.choice(["email", "discussion"])
            local_prompt = (f"You are a member of a university society about {topic}, and an upcoming event has been changed in a way that causes you a problem.\n\nWrite an email to the organiser. In your email, do the following:\n- Explain the problem.\n- Suggest a solution.\n- Ask a related question.\n\nWrite as much as you can and in complete sentences."
                            if task == "email" else
                            f"Your professor is leading a discussion about {topic}. Write a post responding to the professor's question, giving and supporting your opinion.\n\nProfessor: Should governments invest more public money in {topic}? Why or why not?\n\nStudent A: Yes. Public funding makes it available to everyone, not just people who can afford it.\n\nStudent B: I disagree. Private organisations are usually more efficient, and public money is needed elsewhere.")
            out = self.structured(QuestionOutput, f"Write one ORIGINAL TOEFL 2026 '{'Write an Email' if task == 'email' else 'Academic Discussion'}' task about '{topic}' in the official layout "
                                  "(email: situation + three bullet requirements; discussion: professor question and two short student posts with opposing views). Return a self-reported confidence {\"task\": 0-1}.",
                                  {"topic": topic}, {"title": f"{topic.title()} - {'email' if task == 'email' else 'discussion'}", "prompt": local_prompt, "task_type": "Write an Email" if task == "email" else "Academic Discussion", "confidence": {"task": .84}}).model_dump()
            item = {"id": f"gen-writing-{int(time.time())}", "kind": "writing", "exam": exam, "task": task, "title": out["title"], "topic": topic, "prompt": out["prompt"], "min_words": 100, "minutes": 7 if task == "email" else 10}
            return {**out, "content": item}
        task = task if task in ("task1", "task2") else "task2"
        if task == "task1":
            categories = rng.sample(["2000", "2005", "2010", "2015", "2020", "2025"], 4) if rng.random() < .5 else ["City A", "City B", "City C", "City D"]
            categories.sort()
            base = [rng.randint(20, 70) for _ in categories]
            series = [{"name": "Men", "values": base}, {"name": "Women", "values": [max(5, v + rng.randint(-20, 20)) for v in base]}]
            local = {"title": f"{topic.title()} participation", "task_type": "Academic Writing Task 1", "confidence": {"task": .82},
                     "prompt": f"The chart below shows the percentage of men and women involved in {topic} in four {'years' if categories[0].isdigit() else 'cities'}. Summarise the information by selecting and reporting the main features, and make comparisons where relevant."}
            out = self.structured(QuestionOutput, "Write the rubric sentence for one ORIGINAL IELTS Academic Writing Task 1 bar chart about the given topic and data. Return a self-reported confidence.",
                                  {"topic": topic, "categories": categories, "series": series}, local).model_dump()
            item = {"id": f"gen-writing-{int(time.time())}", "kind": "writing", "exam": exam, "task": "task1", "title": out["title"], "topic": topic, "prompt": out["prompt"],
                    "chart": {"type": "bar", "title": out["title"], "unit": "%", "categories": categories, "series": series}, "min_words": 150, "minutes": 20}
            return {**out, "content": item}
        templates = [
            "Some people think that {t} should receive more public funding, while others believe the money would be better spent elsewhere. Discuss both these views and give your own opinion.",
            "In many countries, attitudes towards {t} have changed significantly in recent years. What are the reasons for this? Is it a positive or negative development?",
            "{T} has become a major issue in many cities. What problems does it cause, and what solutions can you suggest?",
            "To what extent do you agree or disagree that governments, rather than individuals, are responsible for {t}?",
            "Some argue that {t} brings more advantages than disadvantages for society. Do the advantages outweigh the disadvantages?",
        ]
        prompt = rng.choice(templates).format(t=topic, T=topic[:1].upper() + topic[1:]) + "\n\nGive reasons for your answer and include any relevant examples from your own knowledge or experience."
        out = self.structured(QuestionOutput, "Create one ORIGINAL IELTS Writing Task 2 question about the topic using an authentic question type (opinion, discussion, problem-solution, "
                              "advantages-disadvantages or two-part) and the standard closing instruction. Never reproduce a published question. Return a self-reported confidence.",
                              {"topic": topic}, {"title": f"{topic.title()} - Task 2", "prompt": prompt, "task_type": "Writing Task 2", "confidence": {"task": .84}}).model_dump()
        item = {"id": f"gen-writing-{int(time.time())}", "kind": "writing", "exam": exam, "task": "task2", "title": out["title"], "topic": topic, "prompt": out["prompt"], "min_words": 250, "minutes": 40}
        return {**out, "content": item}

    def _generate_speaking(self, exam: str, topic: str, rng: random.Random) -> dict:
        if exam == "TOEFL":
            base = dict(bank.pick("TOEFL", "speaking", rng=rng))
            questions = [f"Thanks for talking with me. How often do you encounter {topic} in your daily life?",
                         f"What do you think is the most important benefit of {topic} for students?",
                         f"Some people believe {topic} should be regulated more strictly. What is your view, and why?",
                         f"Finally, how do you think {topic} will change over the next ten years?"]
            out = self.structured(QuestionOutput, "Write four ORIGINAL TOEFL 2026 'Take an Interview' questions about the topic, from personal to abstract, separated by newlines. Return a self-reported confidence.",
                                  {"topic": topic}, {"title": f"Interview: {topic}", "prompt": "\n".join(questions), "task_type": "Listen and Repeat + Interview", "confidence": {"task": .84}}).model_dump()
            lines = [line.strip() for line in out["prompt"].split("\n") if line.strip().endswith("?")][:4] or questions
            item = {**base, "id": f"gen-speaking-{int(time.time())}", "title": out["title"], "topic": topic, "interview": {"scenario": f"A researcher is interviewing students about {topic}.", "questions": lines}}
            return {**out, "content": item}
        local = {"title": f"Speaking test: {topic}", "cue": f"Describe an experience you had that was connected with {topic}.",
                 "bullets": ["what happened", "when and where it happened", "who was involved", f"and explain how you felt about it"],
                 "closing": f"Would you like to have a similar experience again?", "part3_theme": topic,
                 "part3_questions": [f"Why do you think {topic} matters to people today?", f"How has {topic} changed compared with the past?",
                                     f"Should governments do more to support {topic}?", f"What might {topic} look like in the future?"],
                 "confidence": {"task": .84}}
        out = self.structured(SpeakingGen, "Create an ORIGINAL IELTS Speaking Part 2 cue card ('Describe ...' + 3-4 'You should say' bullets, the last starting 'and explain') "
                              "with a short rounding-off question, plus 4 related Part 3 discussion questions from concrete to abstract. Never reproduce published cue cards. Return a self-reported confidence.",
                              {"topic": topic}, local).model_dump()
        test = bank.ielts_production.speaking_test(rng.randrange(1000))
        item = {**test, "id": f"gen-speaking-{int(time.time())}", "title": out["title"], "topic": topic,
                "part2": {"topic": topic, "cue": out["cue"], "bullets": out["bullets"], "closing": out["closing"]},
                "part3": {"theme": out["part3_theme"], "questions": out["part3_questions"]}}
        return {"title": out["title"], "task_type": "Full Speaking test (Parts 1-3)", "prompt": out["cue"], "content": item, "confidence": out["confidence"]}

    # ---------------------------------------------------------------- plans and assessment
    def plan(self, profile: dict, progress: dict, adaptation: bool) -> PlanOutput:
        priorities = priority_tool.invoke({"priority_skills": profile["priority_skills"], "weakness_skills": progress.get("weaknesses", [])})
        change_request = progress.get("change_request")
        if change_request:
            for skill in ("writing", "speaking", "reading", "listening"):
                if skill in change_request.lower():
                    priorities.remove(skill)
                    priorities.insert(0 if "less " + skill not in change_request.lower() else len(priorities), skill)
                    break
        total_minutes = profile["weekly_hours"] * 60
        detail = {"writing": "Write one Task 2 essay and one Task 1 report; revise using the feedback", "speaking": "Complete a full speaking test with the AI examiner and redo Part 2",
                  "reading": "Do one timed passage (20 min) and review every wrong answer", "listening": "Do one listening part at exam speed and study the transcript"}
        activities = [{"skill": skill, "title": detail[skill] if index < 2 else f"{skill.title()} maintenance practice", "minutes_per_week": round(total_minutes * (.4 if index == 0 else .25 if index == 1 else .175)),
                       "reason": "Weakest verified skill" if skill in progress.get("weaknesses", []) else "Learner priority" if skill in profile["priority_skills"] else "Keep all four skills balanced"}
                      for index, skill in enumerate(priorities)]
        local = {"title": f"{profile['exam']} {'adapted' if adaptation else 'revised' if change_request else 'starter'} plan",
                 "rationale": f"Focus on {', '.join(priorities[:2])} within {profile['weekly_hours']} study hours each week before {profile['exam_date']}." + (f" Learner requested: {change_request}." if change_request else ""),
                 "priorities": priorities, "activities": activities,
                 "changes": (["Increase practice on recent weak skills"] if adaptation else []) + ([f"Consider learner request: {change_request}"] if change_request else []), "confidence": {"plan": .87}}
        return self.structured(PlanOutput, "You are the Learning Coordinator. Propose actionable IELTS or TOEFL weekly study activities (skill, title, minutes_per_week, reason) whose minutes sum to the "
                               "learner's weekly hours. Return confidence as a self-reported heuristic, not a calibrated probability.", {"profile": profile, "progress": progress, "adaptation": adaptation}, local)

    def prompt(self, exam: str, skill: str, avoid: set[str] | None = None) -> dict:
        """Pick an item from the curated bank, preferring ones the learner has not seen."""
        item = bank.pick(exam, skill, avoid)
        return practice_prompt(item, "ORIGINAL")

    def feedback(self, exam: str, skill: str, text: str, scenario: str, prompt: str = "", task: str = "task2", metrics: dict | None = None) -> FeedbackOutput:
        local = analyse_response(exam, skill, text, prompt, task, metrics)
        if self.local:
            if scenario == "low_confidence":
                local["confidence"] = {key: .42 for key in local["criteria"]}
            if scenario == "contradiction":
                first = next(iter(local["criteria"]))
                local["summary"] = f"Excellent {first.replace('_', ' ')} with no weaknesses."
                local["criteria"][first] = 2.0
            if scenario == "invalid":
                local["confidence"] = {}
        keys = ", ".join(local["criteria"])
        system = (f"You are an experienced {exam} examiner and tutor assessing {skill} ({task}). {RUBRICS[exam]} "
                  f"Return exactly these criterion keys: {keys}. IELTS uses 0-9 half bands; TOEFL 2026 uses a 1-6 scale in half points. "
                  "Base scores on the response; the 'measured_features' are objective counts you may use as evidence. "
                  "Give 3-6 sentence-specific comments (quote the sentence, name the issue, give a concrete fix), 3-4 improvements, up to 5 improved_sentences "
                  "({original, improved}), and a short model_answer paragraph showing a higher-band version of one part. "
                  "Never infer pronunciation from a transcript: set pronunciation_available false and explain that audio was not assessed. "
                  "Provide self-reported confidence (0-1) for every criterion. These are unofficial estimates.")
        output = self.structured(FeedbackOutput, system, {"exam": exam, "skill": skill, "task": task, "question": prompt[:3000], "response": text[:12000],
                                                          "measured_features": local["analysis"], "delivery_metrics": metrics or {}}, local)
        if not self.local:
            output.analysis = local["analysis"]
            if skill != "speaking":
                output.pronunciation_note = None
        return output

    def consistency(self, payload: dict) -> VerdictOutput:
        scores = payload.get("criteria", {})
        summary = payload.get("summary", "").lower()
        issues = bool(scores) and ("excellent" in summary or "no weaknesses" in summary) and min(scores.values()) <= 3
        local = {"consistent": not issues, "reason": "Praise conflicts with a very low criterion score" if issues else "No obvious score and feedback contradiction", "confidence": .85}
        return self.structured(VerdictOutput, "Check whether feedback statements contradict criterion scores. Be conservative and return a short reason.", {"summary": payload.get("summary"), "criteria": scores, "comments": payload.get("comments", [])}, local)

    def recommendations(self, catalog: list[dict], priorities: list[str]) -> RecommendationOutput:
        ranked = sorted(catalog, key=lambda item: item["skill"] not in priorities)[:4]
        local = {"items": [{"id": item["id"], "title": item["title"], "skill": item["skill"], "reason": f"Targets your {'priority' if item['skill'] in priorities else 'supporting'} skill: {item['skill']}", "confidence": .84} for item in ranked],
                 "summary": "Ranked study material suggestions", "confidence": {str(item["id"]): .84 for item in ranked}}
        return self.structured(RecommendationOutput, "You are the Learning Coordinator. Rank only catalog IDs provided, explain each match and return self-reported confidence per item.", {"catalog": catalog, "priorities": priorities}, local)

    def report(self, progress: dict) -> ReportNarrative:
        scores = progress.get("skill_scores", {})
        best = max(scores, key=scores.get) if scores else None
        local = {"summary": (f"Across {progress.get('sample_count', 0)} verified results, your strongest skill is {best} ({scores[best]}). " if best else "")
                 + (f"Focus next on {', '.join(progress.get('weaknesses', []))}." if progress.get("weaknesses") else "Collect more practice results for a clearer picture."),
                 "recommendations": [f"Practise {skill} twice this week and review every feedback comment" for skill in progress.get("weaknesses", [])] or ["Collect more practice results"],
                 "confidence": {"report": .81}}
        return self.structured(ReportNarrative, "You are the Assessment and Analytics agent. Explain observed scores conservatively; readiness is an estimate and never an official score. Return self-reported confidence.", progress, local)


def practice_prompt(item: dict, source: str) -> dict:
    """Shape a bank item into the Practice.prompt record (answer keys stay server-side)."""
    kind = item["kind"]
    if kind in ("listening", "reading"):
        test = bank.wrap(kind, [item])
        minutes = item.get("minutes") or (10 if kind == "listening" else 20)
        return {"title": item["title"], "text": item.get("context") or item["title"], "mode": source, "task_type": bank.task_type(item) if item["id"] in bank.ALL else kind,
                "duration_seconds": minutes * 60, "test": test, "content_id": item["id"]}
    if kind == "writing":
        return {"title": item["title"], "text": item["prompt"], "mode": source, "task_type": bank.task_type(item) if item["id"] in bank.ALL else item["task"], "task": item["task"],
                "duration_seconds": item.get("minutes", 40) * 60, "min_words": item.get("min_words", 250), "chart": item.get("chart"), "content_id": item["id"]}
    return {"title": item["title"], "text": item.get("part2", {}).get("cue") or item.get("interview", {}).get("scenario", item["title"]), "mode": source,
            "task_type": "Full Speaking test", "duration_seconds": 900, "test": item, "content_id": item["id"]}


class AgentRuntime:
    def __init__(self, db: Session):
        self.db = db
        self.provider = ProviderAdapter()

    def threshold(self) -> float:
        row = self.db.get(SystemSetting, "quality_threshold")
        return float(row.value) if row else settings().quality_threshold

    def event(self, state: FlowState, agent: str, phase: str, detail: dict, started: float | None = None):
        self.db.add(AgentEvent(user_id=state["user_id"], workflow=state["workflow"], agent=agent, phase=phase, detail=detail, mode=self.provider.mode, duration_ms=int((time.perf_counter()-started)*1000) if started else 0))
        self.db.flush()

    def coordinator(self, state: FlowState) -> dict:
        t = time.perf_counter()
        self.event(state, "Learning Coordinator", "perception", {"exam": state["profile"]["exam"], "priorities": state["profile"]["priority_skills"]})
        try:
            output = self.provider.plan(state["profile"], state.get("progress", {}), state["workflow"] == "adaptation").model_dump()
        except Exception as exc:
            output = {"summary": "Plan generation failed structured validation", "confidence": {}, "error_type": type(exc).__name__}
        self.event(state, "Learning Coordinator", "handoff", {"decision": "submit proposed plan", "next_agent": "Quality Manager", "tool": "LLM adapter"}, t)
        return {"output": output, "source_mode": self.provider.mode}

    def request_insights(self, state: FlowState) -> dict:
        self.event(state, "Learning Coordinator", "handoff", {"decision": "request performance analysis", "next_agent": "Assessment & Analytics"})
        return {}

    def assessment_insights(self, state: FlowState) -> dict:
        self.event(state, "Assessment & Analytics", "handoff", {"decision": "return verified progress insights", "weaknesses": state.get("progress", {}).get("weaknesses", []), "next_agent": "Learning Coordinator"})
        return {}

    def tutor(self, state: FlowState) -> dict:
        t = time.perf_counter()
        self.event(state, "AI Tutor", "perception", {"skill": state["skill"], "response_length": len(state["text"])})
        try:
            result = self.provider.feedback(state["profile"]["exam"], state["skill"], state["text"], state.get("scenario", "normal"),
                                            state.get("prompt", ""), state.get("task") or "task2", state.get("metrics")).model_dump()
        except Exception as exc:
            result = {"summary": "Feedback generation failed structured validation", "criteria": {}, "comments": [], "confidence": {}, "error_type": type(exc).__name__}
        self.event(state, "AI Tutor", "handoff", {"decision": "generate feedback", "next_agent": "Assessment & Analytics", "tool": "LLM adapter"}, t)
        return {"output": result, "source_mode": self.provider.mode}

    def assessment(self, state: FlowState) -> dict:
        t = time.perf_counter()
        result = dict(state["output"])
        scores = result.get("criteria", {})
        result["estimated_overall"] = criterion_average.invoke({"scores": scores})
        result["score_scale"] = "IELTS 0-9 bands" if state["profile"]["exam"] == "IELTS" else "TOEFL 2026 1-6 sections"
        result["official"] = False
        self.event(state, "Assessment & Analytics", "handoff", {"decision": "calculate indicative criterion mean", "next_agent": "Quality Manager", "tool": "criterion_average"}, t)
        return {"output": result}

    def quality(self, state: FlowState) -> dict:
        t = time.perf_counter()
        payload = state["output"]
        package = ResultPackage(user_id=state["user_id"], kind=state["workflow"], state="SUBMITTED", payload=payload, confidence=payload.get("confidence", {}), source_mode=state.get("source_mode", self.provider.mode), issues=[])
        self.db.add(package)
        self.db.flush()
        self.event(state, "Quality Manager", "state", {"package_id": package.id, "state": "SUBMITTED"})
        package.state = "VALIDATING"
        self.event(state, "Quality Manager", "state", {"package_id": package.id, "state": "VALIDATING"})
        issues = []
        confidence = package.confidence
        if not payload or not confidence or any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in confidence.values()):
            issues.append("Missing or invalid structured output/confidence")
        if state["workflow"] in ("writing", "speaking") and (not payload.get("summary") or not payload.get("criteria") or not payload.get("comments")):
            issues.append("Required feedback fields missing")
        if state["workflow"] in ("writing", "speaking"):
            criteria = payload.get("criteria", {})
            exam = state.get("profile", {}).get("exam")
            expected = ({"task_response", "coherence", "lexical_resource", "grammar"} if state["workflow"] == "writing" else {"fluency", "lexical_resource", "grammar"}) if exam == "IELTS" else ({"task_fulfillment", "organisation", "language_use"} if state["workflow"] == "writing" else {"language_use", "topic_development"})
            if set(criteria) != expected:
                issues.append("Criteria do not match the selected exam rubric")
            if state["workflow"] == "speaking" and (payload.get("pronunciation_available") is not False or not payload.get("pronunciation_note")):
                issues.append("Speaking feedback must disclose unavailable audio assessment")
            if set(criteria) != set(confidence):
                issues.append("Every criterion requires its own confidence value")
            max_score = 9 if exam == "IELTS" else 6
            if any(not isinstance(v, (int, float)) or v < 0 or v > max_score for v in criteria.values()):
                issues.append("Criterion score outside exam scale")
            if criteria and isinstance(payload.get("estimated_overall"), (int, float)) and abs(payload["estimated_overall"] - criterion_average.invoke({"scores": criteria})) > 0.5:
                issues.append("Overall estimate conflicts with criterion scores")
        if state["workflow"] in ("plan", "adaptation") and (not payload.get("priorities") or not payload.get("activities") or not payload.get("rationale")):
            issues.append("Plan is incomplete")
        if state["workflow"] == "recommendations" and (not payload.get("items") or any(not item.get("reason") for item in payload.get("items", []))):
            issues.append("Recommendation list is incomplete")
        if state["workflow"] == "mock_exam" and (set(payload.get("section_scores", {})) != {"reading", "writing", "speaking", "listening"}):
            issues.append("Mock exam requires four section scores")
        if state["workflow"] == "mock_exam" and (any(not isinstance(v, (int, float)) or v < 0 or v > (9 if payload.get("score_scale", "").startswith("IELTS") else 6) for v in payload.get("section_scores", {}).values())):
            issues.append("Mock section score outside exam scale")
        if state["workflow"] == "portrait" and (not payload.get("summary") or not payload.get("focus_areas") or not payload.get("next_steps")):
            issues.append("Learner portrait is incomplete")
        if state["workflow"] == "question" and (not payload.get("title") or not payload.get("prompt") or not payload.get("task_type")):
            issues.append("Generated question is incomplete")
        if state["workflow"] == "question" and isinstance(payload.get("content"), dict) and payload["content"].get("kind") in ("listening", "reading"):
            issues.extend(validate_test(payload["content"]))
        if state["workflow"] == "question" and "official ielts" in (str(payload.get("title", "")) + " " + str(payload.get("prompt", ""))).lower():
            issues.append("Generated question must not claim to be official IELTS content")
        package.state = "CHECKING"
        self.event(state, "Quality Manager", "state", {"package_id": package.id, "state": "CHECKING"})
        if any(v < self.threshold() for v in confidence.values() if isinstance(v, (int, float))):
            issues.append("Confidence below configured threshold")
        if payload.get("criteria") and ("excellent" in payload.get("summary", "").lower() or "no weaknesses" in payload.get("summary", "").lower()) and min(payload["criteria"].values()) <= 3:
            issues.append("Rule check found score/feedback contradiction")
        try:
            verdict = self.provider.consistency(payload)
            if not verdict.consistent:
                issues.append(verdict.reason)
            if verdict.confidence < self.threshold():
                issues.append("Consistency verdict confidence below threshold")
            method = "LLM" if self.provider.mode == "REAL" else "DEMO_RULES"
        except Exception:
            method = "FALLBACK_RULES"
            if payload.get("criteria") and ("excellent" in payload.get("summary", "").lower()) and min(payload["criteria"].values()) <= 3:
                issues.append("Rule fallback found score/feedback contradiction")
            if self.provider.mode == "REAL":
                issues.append("LLM consistency verification unavailable")
        package.issues = issues
        self.db.add(QualityCheck(package_id=package.id, verdict="HOLD" if issues else "VERIFY", issues=issues, threshold=self.threshold(), method=method))
        self.event(state, "Quality Manager", "verification", {"package_id": package.id, "issues": issues, "method": method, "threshold": self.threshold(), "confidence": confidence}, t)
        if issues:
            package.state = "HELD"
            self.event(state, "Quality Manager", "state", {"package_id": package.id, "state": "HELD", "issues": issues})
            self.db.add(Escalation(package_id=package.id, status="PENDING", reason="; ".join(issues)))
            self.event(state, "Quality Manager", "handoff", {"next_agent": "Human Instructor", "package_id": package.id})
            if state["workflow"] in ("writing", "speaking"):
                tags = {item.get("issue") for item in payload.get("comments", []) if item.get("issue")}
                recent = self.db.scalars(select(ResultPackage).where(ResultPackage.kind == state["workflow"], ResultPackage.created_at >= datetime.now(timezone.utc)-timedelta(days=7))).all()
                for tag in tags:
                    learners = {item.user_id for item in recent if any(comment.get("issue") == tag for comment in item.payload.get("comments", []))}
                    if len(learners) >= 5:
                        prior = self.db.scalars(select(AuditLog).where(AuditLog.action == "curriculum_gap_detected", AuditLog.created_at >= datetime.now(timezone.utc)-timedelta(days=7))).all()
                        if not any(row.detail.get("issue") == tag for row in prior):
                            self.db.add(AuditLog(user_id=None, action="curriculum_gap_detected", detail={"issue": tag, "learners": len(learners)}))
        else:
            package.state = "VERIFIED"
            self.event(state, "Quality Manager", "state", {"package_id": package.id, "state": "VERIFIED"})
        self.db.add(AuditLog(user_id=state["user_id"], action="quality_checked", detail={"package_id": package.id, "issues": issues, "method": method}))
        self.db.flush()
        return {"package_id": package.id, "issues": issues, "route": "hold" if issues else "release"}

    def release(self, state: FlowState) -> dict:
        package = self.db.get(ResultPackage, state["package_id"])
        if package.state != "VERIFIED":
            raise RuntimeError("Unverified result cannot be released")
        package.state = "RELEASED"
        self.event(state, "Quality Manager", "release", {"package_id": package.id, "verified": True, "result": {"summary": package.payload.get("summary"), "title": package.payload.get("title"), "estimated_overall": package.payload.get("estimated_overall")}})
        self.db.add(AuditLog(user_id=state["user_id"], action="result_released", detail={"package_id": package.id}))
        return {}

    def hold(self, state: FlowState) -> dict:
        self.event(state, "Human Instructor", "waiting", {"package_id": state["package_id"], "status": "durable database wait"})
        return {}

    def plan_graph(self):
        graph = StateGraph(FlowState)
        graph.add_node("request_insights", self.request_insights)
        graph.add_node("assessment_insights", self.assessment_insights)
        graph.add_node("coordinator", self.coordinator)
        graph.add_node("quality", self.quality)
        graph.add_node("release", self.release)
        graph.add_node("human_wait", self.hold)
        graph.add_conditional_edges(START, lambda s: "request_insights" if s["workflow"] == "adaptation" else "coordinator", {"request_insights": "request_insights", "coordinator": "coordinator"})
        graph.add_edge("request_insights", "assessment_insights")
        graph.add_edge("assessment_insights", "coordinator")
        graph.add_edge("coordinator", "quality")
        graph.add_conditional_edges("quality", lambda s: s["route"], {"release": "release", "hold": "human_wait"})
        graph.add_edge("release", END)
        graph.add_edge("human_wait", END)
        return graph.compile()

    def release_after_human(self, package: ResultPackage):
        if package.state not in ("APPROVED", "CORRECTED"):
            raise RuntimeError("Human decision required before release")
        package.state = "RELEASED"
        state: FlowState = {"user_id": package.user_id, "workflow": package.kind}
        self.event(state, "Quality Manager", "release", {"package_id": package.id, "verification": "human approval", "next_agent": "Learner", "result": {"summary": package.payload.get("summary"), "title": package.payload.get("title"), "estimated_overall": package.payload.get("estimated_overall")}})
        self.db.add(AuditLog(user_id=package.user_id, action="result_released", detail={"package_id": package.id, "by": "instructor"}))

    def practice_graph(self):
        graph = StateGraph(FlowState)
        graph.add_node("tutor", self.tutor)
        graph.add_node("assessment", self.assessment)
        graph.add_node("quality", self.quality)
        graph.add_node("release", self.release)
        graph.add_node("human_wait", self.hold)
        graph.add_edge(START, "tutor")
        graph.add_edge("tutor", "assessment")
        graph.add_edge("assessment", "quality")
        graph.add_conditional_edges("quality", lambda s: s["route"], {"release": "release", "hold": "human_wait"})
        graph.add_edge("release", END)
        graph.add_edge("human_wait", END)
        return graph.compile()

    def verify_output(self, user_id: int, workflow: str, output: dict) -> ResultPackage:
        state: FlowState = {"user_id": user_id, "workflow": workflow, "output": output, "source_mode": self.provider.mode}
        state.update(self.quality(state))
        if state["route"] == "release":
            self.release(state)
        else:
            self.hold(state)
        return self.db.get(ResultPackage, state["package_id"])
