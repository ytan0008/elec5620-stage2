"""Agents and executable StateGraphs, following the Stage 1 class diagram.

Agent (abstract) is specialised by LearningCoordinatorAgent, TutorAgent,
AssessmentAgent and OpsQualityManager. AgentRuntime is the central controller:
it owns one of each agent and wires them into LangGraph workflows.

All model access goes through the LLMService interface, realised by
LLMProviderAdapter, which runs in one of two modes:
  REAL  - a configured OpenAI-compatible chat model produces structured output.
  LOCAL - the built-in engine: curated exam content, rule-based language
          analysis and a scripted examiner. No network access is needed.
"""
import json
import random
import time
from abc import ABC
from datetime import datetime, timedelta, timezone
from typing import Callable, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.config import settings
from backend.models import AgentEvent, AuditLog, Escalation, MaterialInteraction, QualityCheck, ResultPackage, SystemSetting
from backend.llm_service import AgentStatus, IssueType, LLMService, ResultStatus
from backend.materials import MaterialLibrary, material_dto
from backend.schemas import (FeedbackOutput, PlanOutput, VerdictOutput, RecommendationOutput, ReportNarrative, OnboardingExtraction, PortraitOutput,
                             QuestionOutput, AgentChatReply, ExaminerTurn, ListeningGen, ReadingGen, SpeakingGen, WordInfo, CoachOutput)
from backend.onboarding import parse_demo_message
from backend import content as bank
from backend import local_tutor
from backend import adaptation
from backend import analytics
from backend import agent_core
from backend.agent_core import Toolkit
from backend.scoring import analyse_response, validate_test


class MockUnavailable(Exception):
    """UC5 3a: the mock examination could not be prepared."""


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
    regen_attempts: int
    can_regenerate: bool
    generation_failed: bool


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


class LLMProviderAdapter(LLMService):
    def __init__(self):
        self.config = settings()
        self.mode = self.config.ai_mode
        self.llm = self.scorer = None
        if self.mode == "REAL":
            self.llm = self._client(self.config.llm_reasoning_effort)
            self.scorer = self._client(self.config.llm_scoring_effort) if self.config.llm_scoring_effort != self.config.llm_reasoning_effort else self.llm

    def _client(self, effort: str) -> ChatOpenAI:
        options = {"model": self.config.llm_model, "api_key": self.config.openai_api_key, "base_url": self.config.openai_base_url or None, "timeout": 90, "max_retries": 1}
        if self.config.llm_use_responses_api:
            options["use_responses_api"] = True
        if effort:
            options["reasoning"] = {"effort": effort}
        return ChatOpenAI(**options)

    @property
    def local(self) -> bool:
        return self.mode == "LOCAL"

    def structured(self, schema, system: str, user: dict, local: dict, toolkit: Toolkit | None = None, scoring: bool = False):
        """Structured output from the cloud model. With a toolkit the agent sees its memory, may call its tools,
        and then submits the answer through a final tool shaped like the schema."""
        if self.local:
            return schema.model_validate(local)
        llm = self.scorer if scoring else self.llm
        # Callers pass only exam goals, learning text and scores; account identity is excluded.
        if toolkit:
            user = {**user, "your_memory": agent_core.recall(toolkit.db, toolkit.agent, toolkit.user_id, 8, include_cohort=True)}
            system += (" You are one of four cooperating agents. 'your_memory' holds your own notes from earlier sessions. "
                       "Call your tools when you need facts you were not given; then call submit_result exactly once with the final answer.")
        messages = [SystemMessage(system), HumanMessage(json.dumps(user, ensure_ascii=False, default=str))]
        if toolkit:
            try:
                return self._agent_loop(llm, schema, messages, toolkit)
            except Exception:
                pass  # Fall back to a plain structured call with the tool results gathered so far.
        chain = llm.with_structured_output(schema)
        try:
            return chain.invoke(messages)
        except Exception:
            return chain.invoke(messages)  # One bounded retry before the caller holds the result.

    def _agent_loop(self, llm, schema, messages: list, toolkit: Toolkit):
        tools = {item.name: item for item in toolkit.tools()}
        final = {"type": "function", "function": {"name": "submit_result", "description": "Submit the final structured answer.", "parameters": schema.model_json_schema()}}
        for round_ in range(self.config.agent_tool_rounds + 1):
            last = round_ == self.config.agent_tool_rounds
            bound = llm.bind_tools([final] if last else [*tools.values(), final], tool_choice="submit_result" if last else "required")
            reply = bound.invoke(messages)
            messages.append(reply)
            submitted = next((call for call in reply.tool_calls if call["name"] == "submit_result"), None)
            if submitted:
                return schema.model_validate(submitted["args"])
            for call in reply.tool_calls:
                result = tools[call["name"]].invoke(call["args"]) if call["name"] in tools else {"error": "unknown tool"}
                messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False, default=str)[:6000], tool_call_id=call["id"]))
        raise RuntimeError("Agent did not submit a result")

    def extract_onboarding(self, message: str, draft: dict) -> OnboardingExtraction:
        return self.structured(
            OnboardingExtraction,
            "Extract only explicitly stated IELTS/TOEFL learner goals from the latest message. "
            "Do not invent missing values. Dates must be YYYY-MM-DD. Skills must be writing, speaking, reading or listening. "
            "Return null for fields not supplied in the latest message.",
            {"latest_message": message, "current_draft": draft, "today": datetime.now(timezone.utc).date().isoformat()}, parse_demo_message(message, draft),
        )

    def chat(self, context: str, message: str, profile: dict, plan: dict | None, history: list[dict], persona: str = "witch",
             memory: list[str] | None = None, notebook: dict | None = None, actions: list[str] | None = None, toolkit: Toolkit | None = None) -> AgentChatReply:
        """Instructional conversation with long-term memory; formal scores and plans use the verified workflows."""
        memory, notebook, actions = memory or [], notebook or {}, actions or []
        local = local_tutor.reply(context, message, profile, plan, history, persona, memory, notebook, actions)
        if self.local:
            return AgentChatReply(reply=local)
        skill = context if context in ("speaking", "writing", "reading", "listening") else None
        role = "AI Tutor" if skill or context in ("tutor", "notebook") else "Learning Coordinator"
        speaking_rules = ("This is a spoken conversation practice: reply in 1-3 short natural sentences (under 70 words) that will be read aloud. "
                          "React to what the learner said, gently correct at most one clear grammar or vocabulary mistake by recasting it, then ask one follow-up question. "
                          "Use IELTS Speaking Part 1/3 style topics. No markdown, lists or emojis.") if skill == "speaking" else                          "Be concise (under 170 words), practical and warm; guide step by step and ask at most one follow-up. Plain text only, no markdown tables."
        return self.structured(
            AgentChatReply,
            f"{PERSONA_STYLE.get(persona, PERSONA_STYLE['witch'])} You act as the {role} of an IELTS/TOEFL preparation platform; the current page is '{context}'. "
            f"{speaking_rules} You have long-term memory: 'memory' lists what you know about this learner from earlier sessions, and 'notebook' summarises their "
            "mistake book (wrong answers by question type), grammar book (repeated grammar errors), word book (unknown words, reviews due) and sentence book. "
            "Use them naturally to personalise guidance (e.g. refer to a repeated mistake type or a word they saved) but don't recite them. "
            "'actions' lists things the platform just did for the learner, such as saving a word with its definition; explain new words simply with one example. "
            "Put any NEW durable fact about the learner (background, goals, difficulties, preferences) in 'remember' as short third-person notes; leave it empty otherwise. "
            "Do not claim an official IELTS/TOEFL score or calibrated confidence. If the learner writes in Chinese or another language, answer mainly in simple English "
            "and add a brief translation. Never ask for passwords or identity details.",
            {"message": message, "profile": profile, "active_plan": plan, "memory": memory[:30], "notebook": notebook, "actions": actions, "recent_messages": history[-12:]},
            {"reply": local}, toolkit if skill != "speaking" else None,  # Spoken turns skip tools to keep the voice reply fast.
        )

    def word_info(self, word: str, context: str, language: str, dictionary: dict) -> dict:
        """Learner-friendly entry for the word book. The cloud model adds a translation and a context-specific sense."""
        if self.local:
            return dictionary
        info = self.structured(WordInfo, f"You write learner dictionary entries for IELTS/TOEFL students. Give the IPA, part of speech and a simple English definition of the sense used "
                               f"in the context sentence (if any), a short {language} translation, one natural example sentence, up to 4 synonyms and up to 3 useful collocations.",
                               {"word": word, "context": context, "dictionary": dictionary}, {}).model_dump()
        meanings = [{"pos": info["part_of_speech"], "definition": info["definition"], "example": info["example"]}] + [m for m in dictionary.get("meanings", []) if m.get("definition") != info["definition"]][:2]
        return {"phonetic": info["phonetic"] or dictionary.get("phonetic", ""), "meanings": meanings, "translation": info["translation"],
                "synonyms": info["synonyms"] or dictionary.get("synonyms", []), "collocations": info["collocations"], "dictionary": "cloud AI"}

    def coach(self, points: list[str], profile: dict, memory: list[str], notebook: dict, persona: str, toolkit: Toolkit | None = None) -> str:
        name = "Kai" if persona == "boy" else "Luna"
        local = f"Here's your coaching plan for today from {name}:\n" + "\n".join(f"{i + 1}. {point}" for i, point in enumerate(points))
        if self.local:
            return local
        return self.structured(CoachOutput, f"{PERSONA_STYLE.get(persona, PERSONA_STYLE['witch'])} Write today's personalised coaching message for this IELTS/TOEFL learner: "
                               "3-5 numbered, concrete steps that use their notebook statistics (most frequent mistake types, repeated grammar errors, words due) and what you remember about them. "
                               "Each step names a specific action in the app (Mistake book, Word book, Grammar book, a practice skill or the mock exam) and why. Plain text, under 220 words.",
                               {"profile": profile, "memory": memory[:30], "notebook": notebook, "starting_points": points}, {"message": local}, toolkit).message

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

    def portrait(self, profile: dict, toolkit: Toolkit | None = None) -> PortraitOutput:
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
            {"profile": profile}, local, toolkit,
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
    def plan(self, profile: dict, progress: dict, adaptation: bool, toolkit: Toolkit | None = None) -> PlanOutput:
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
                               "learner's weekly hours. Use the learner's earlier plan decisions and notebook patterns when they help. Return confidence as a self-reported heuristic, not a calibrated probability. "
                               "When adaptation is true, compare progress.current_plan with progress.skill_scores and progress.target_score, and return change_details: one {skill, reason} for each skill whose "
                               "priority or weekly minutes you changed, with a reason that cites the learner's verified scores.",
                               {"profile": profile, "progress": progress, "adaptation": adaptation}, local, toolkit, scoring=True)

    def prompt(self, exam: str, skill: str, avoid: set[str] | None = None) -> dict:
        """Pick an item from the curated bank, preferring ones the learner has not seen."""
        item = bank.pick(exam, skill, avoid)
        return practice_prompt(item, "ORIGINAL")

    def feedback(self, exam: str, skill: str, text: str, scenario: str, prompt: str = "", task: str = "task2", metrics: dict | None = None, toolkit: Toolkit | None = None) -> FeedbackOutput:
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
                  "Provide self-reported confidence (0-1) for every criterion. These are unofficial estimates. "
                  "If the learner had earlier feedback on this skill, say in the summary which earlier problems are fixed and which remain.")
        output = self.structured(FeedbackOutput, system, {"exam": exam, "skill": skill, "task": task, "question": prompt[:3000], "response": text[:12000],
                                                          "measured_features": local["analysis"], "delivery_metrics": metrics or {}}, local, toolkit, scoring=True)
        if not self.local:
            output.analysis = local["analysis"]
            if skill != "speaking":
                output.pronunciation_note = None
        return output

    def check_consistency(self, payload: dict, toolkit: Toolkit | None = None) -> VerdictOutput:
        scores = payload.get("criteria", {})
        summary = payload.get("summary", "").lower()
        issues = bool(scores) and ("excellent" in summary or "no weaknesses" in summary) and min(scores.values()) <= 3
        local = {"consistent": not issues, "reason": "Praise conflicts with a very low criterion score" if issues else "No obvious score and feedback contradiction", "confidence": .85}
        return self.structured(VerdictOutput, "You are the Operations & Quality Manager. Check whether feedback statements contradict criterion scores. Be conservative and return a short reason. "
                               "Learn from earlier instructor decisions: if the instructor approved similar results you held, do not repeat that false alarm.",
                               {"summary": payload.get("summary"), "criteria": scores, "comments": payload.get("comments", [])}, local, toolkit, scoring=True)

    def rank_and_explain(self, weaknesses: list[str], candidates: list[dict], toolkit: Toolkit | None = None) -> RecommendationOutput:
        ranked = sorted(candidates, key=lambda item: item["skill"] not in weaknesses)[:5]
        local = {"items": [{"id": item["id"], "title": item["title"], "skill": item["skill"], "reason": f"Targets your {'priority' if item['skill'] in weaknesses else 'supporting'} skill: {item['skill']}", "confidence": .84} for item in ranked],
                 "summary": "Ranked study material suggestions", "confidence": {str(item["id"]): .84 for item in ranked}}
        return self.structured(RecommendationOutput, "You are the Learning Coordinator. Rank only the candidate IDs provided, return at most 5, explain each match in one line "
                               "and return self-reported confidence per item.", {"candidates": candidates, "weaknesses": weaknesses}, local, toolkit)

    def generate_exercise(self, exam: str, skill: str, level: str) -> dict:
        local = {"title": f"{skill.title()} quick exercise", "task_type": f"{exam} {skill} exercise", "confidence": {"exercise": .8},
                 "prompt": {"writing": "Write three sentences that each give a clear opinion and one reason, using 'because', 'since' and 'as a result'. Then underline the reason in each.",
                            "speaking": "Talk for one minute about a place you like. Say where it is, what you do there and why it matters to you. Record yourself and listen for pauses.",
                            "reading": "Read any short news article. For each paragraph, write one line saying its main idea, then check the headline matches your lines.",
                            "listening": "Listen to a two-minute talk. Write down every number and name you hear, then listen again and check your spelling."}[skill]}
        return self.structured(QuestionOutput, f"Write one short ORIGINAL {exam} {skill} exercise for a {level} learner (10 minutes, plain instructions). Return a self-reported confidence.",
                               {"exam": exam, "skill": skill, "level": level}, local).model_dump()

    def report(self, progress: dict, toolkit: Toolkit | None = None) -> ReportNarrative:
        scores = progress.get("skill_scores", {})
        best = max(scores, key=scores.get) if scores else None
        local = {"summary": (f"Across {progress.get('sample_count', 0)} verified results, your strongest skill is {best} ({scores[best]}). " if best else "")
                 + (f"Focus next on {', '.join(progress.get('weaknesses', []))}." if progress.get("weaknesses") else "Collect more practice results for a clearer picture."),
                 "recommendations": [f"Practise {skill} twice this week and review every feedback comment" for skill in progress.get("weaknesses", [])] or ["Collect more practice results"],
                 "confidence": {"report": .81}}
        return self.structured(ReportNarrative, "You are the Assessment and Analytics agent. Explain observed scores conservatively; readiness is an estimate and never an official score. Return self-reported confidence.", progress, local, toolkit, scoring=True)


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




ProviderAdapter = LLMProviderAdapter  # Earlier name, kept so existing imports still work.


# ---------------------------------------------------------------- agents (Stage 1 class diagram)
class Agent(ABC):
    """Abstract agent: perceives through its toolkit and memory, decides, then acts through the LLMService."""
    name = ""
    memory_key = ""

    def __init__(self, runtime: "AgentRuntime"):
        self.runtime = runtime
        self.db = runtime.db
        self.llm: LLMService = runtime.provider

    def get_status(self) -> AgentStatus:
        return AgentStatus.ACTIVE

    def event(self, state: FlowState, phase: str, detail: dict, started: float | None = None):
        self.runtime.event(state, self.name, phase, detail, started)

    def toolkit(self, user_id: int, exam: str = "IELTS") -> Toolkit:
        return Toolkit(self.db, self.memory_key, user_id, exam)


class LearningCoordinatorAgent(Agent):
    name, memory_key = "Learning Coordinator", "coordinator"
    MAX_RECOMMENDATIONS = 5

    def create_plan(self, state: FlowState) -> dict:
        t = time.perf_counter()
        self.event(state, "perception", {"exam": state["profile"]["exam"], "priorities": state["profile"]["priority_skills"]})
        kit = self.toolkit(state["user_id"], state["profile"]["exam"])
        adapting = state["workflow"] == "adaptation"
        output = None
        for attempt in range(2 if adapting else 1):  # UC7 4a: when the model does not respond, retry once
            try:
                output = self.llm.plan(state["profile"], state.get("progress", {}), adapting, kit).model_dump()
                break
            except Exception as exc:
                error = type(exc).__name__
                self.event(state, "decision", {"decision": "plan generation failed", "attempt": attempt + 1, "error": error})
        kit.log(state["workflow"], self.llm.mode)
        if output is None:
            if adapting and not state.get("package_id"):  # 4a: nothing to check or release; the existing plan stays active
                self.event(state, "handoff", {"decision": "keep existing plan", "reason": "adaptation could not be generated", "next_agent": "Learner"}, t)
                return {"generation_failed": True}
            output = {"summary": "Plan generation failed structured validation", "confidence": {}, "error_type": error}
        if output.get("priorities"):
            profile, progress = state["profile"], state.get("progress", {})
            if adapting:  # UC7 step 3 and 4: which priorities should change, and why
                derived = adaptation.describe_changes(progress.get("current_plan", {}), output, progress, progress.get("target_score"))
                output["change_details"] = adaptation.merge_reasons(derived, output.get("change_details", []))
                output["changes"] = adaptation.change_summaries(output["change_details"])
                output["trigger"] = progress.get("trigger")
            output["resources"] = adaptation.select_resources(self.db, state["user_id"], profile["exam"], output["priorities"], profile.get("proficiency"))  # step 5 / 5a
            request = progress.get("change_request")
            agent_core.remember(self.db, self.memory_key, state["user_id"], f"Proposed {state['workflow']} plan '{output.get('title')}' with priorities {', '.join(output['priorities'][:4])}"
                                + (f" after the learner asked: {request}" if request else "") + ".", data={"priorities": output["priorities"]})
        self.event(state, "handoff", {"decision": "submit proposed plan", "next_agent": "Quality Manager", "tool": "LLM adapter"}, t)
        return {"output": output, "source_mode": self.llm.mode}

    def request_insights(self, state: FlowState) -> dict:
        self.event(state, "handoff", {"decision": "request performance analysis", "next_agent": "Assessment & Analytics"})
        return {}

    # UC10 Access Recommended Materials
    def request_recommendations(self, user_id: int, profile: dict, progress: dict) -> ResultPackage:
        t = time.perf_counter()
        state: FlowState = {"user_id": user_id, "workflow": "recommendations"}
        library = MaterialLibrary(self.db)
        dismissed = library.dismissed_ids(user_id)
        weaknesses = progress.get("weaknesses", [])
        new_learner = not progress.get("sample_count")
        self.event(state, "perception", {"weaknesses": weaknesses, "plan_priorities": profile["priority_skills"], "new_learner": new_learner, "dismissed": sorted(dismissed)})
        if new_learner:
            produce = lambda: self._starter_list(profile, library, dismissed)  # 2a
        else:
            targets = weaknesses or profile["priority_skills"]
            produce = lambda: self._personalised_list(user_id, profile, targets, library, dismissed)
        try:
            output = produce()
        except Exception as exc:
            output = {"items": [], "summary": "Recommendation generation failed", "confidence": {}, "error_type": type(exc).__name__}
        self.event(state, "handoff", {"decision": f"submit {output.get('basis', 'ranked')} recommendation list", "next_agent": "Quality Manager",
                                      "items": len(output.get("items", []))}, t)
        return self.runtime.quality_manager.verify(user_id, "recommendations", output, regenerate=produce)

    def last_verified_list(self, user_id: int, before_id: int | None = None) -> dict | None:
        """6a: while a new list is held, the learner keeps the last list that passed UC9."""
        query = select(ResultPackage).where(ResultPackage.user_id == user_id, ResultPackage.kind == "recommendations", ResultPackage.state == ResultStatus.RELEASED)
        if before_id:
            query = query.where(ResultPackage.id < before_id)
        package = self.db.scalar(query.order_by(ResultPackage.id.desc()))
        return package.payload if package else None

    def open_material(self, user_id: int, material_id: int, relevant: bool | None = None) -> MaterialInteraction:
        """8: record the access and let the Coordinator see it."""
        item = self._interaction(user_id, material_id)
        item.viewed = True
        if relevant is not None:
            item.relevant = relevant
        self.event({"user_id": user_id, "workflow": "recommendations"}, "perception", {"material_id": material_id, "opened": True, "relevant": relevant})
        if relevant:
            agent_core.remember(self.db, self.memory_key, user_id, f"Learner found material #{material_id} relevant.", data={"material_id": material_id})
        return item

    def dismiss(self, user_id: int, material_id: int) -> MaterialInteraction:
        """8a: a "Not relevant" item is left out of future rankings."""
        item = self.open_material(user_id, material_id, relevant=False)
        agent_core.remember(self.db, self.memory_key, user_id, f"Learner marked material #{material_id} not relevant; leave it out of future recommendations.",
                            data={"material_id": material_id})
        return item

    def _interaction(self, user_id: int, material_id: int) -> MaterialInteraction:
        item = self.db.scalar(select(MaterialInteraction).where(MaterialInteraction.user_id == user_id, MaterialInteraction.material_id == material_id))
        if not item:
            item = MaterialInteraction(user_id=user_id, material_id=material_id)
            self.db.add(item)
        return item

    def _starter_list(self, profile: dict, library: MaterialLibrary, dismissed: set[int]) -> dict:
        starters = library.get_starter_materials(profile["proficiency"], profile["exam"], dismissed)[:self.MAX_RECOMMENDATIONS]
        items = [{**material_dto(m), "reason": f"Starter {m.skill} material for {m.level} learners"} for m in starters]
        return {"summary": f"General materials for {profile['proficiency']} {profile['exam']} learners. Complete a practice task to get a personalised list.",
                "items": self._label(items, "General"), "targets": [], "basis": "starter", "confidence": {"rules": 1.0}}

    def _personalised_list(self, user_id: int, profile: dict, targets: list[str], library: MaterialLibrary, dismissed: set[int]) -> dict:
        exam, level = profile["exam"], profile["proficiency"]
        candidates = [material_dto(m) for m in library.search(targets, exam, dismissed)]
        generated = []
        for skill in targets:
            if not any(c["skill"] == skill for c in candidates):  # 3a: nothing in the library for this weakness
                try:
                    exercise = self.llm.generate_exercise(exam, skill, level)
                except Exception:
                    continue
                generated.append({"id": f"ai-{skill}", "title": exercise["title"], "skill": skill, "level": level, "content": exercise["prompt"],
                                  "reason": f"No library item matches your {skill} weakness, so a short exercise was written for you",
                                  "confidence": min(exercise["confidence"].values(), default=0)})
        basis, error = "llm", None
        if candidates:
            kit = self.toolkit(user_id, exam)
            try:
                ranked = self.llm.rank_and_explain(targets, candidates, kit).model_dump()
                kit.log("recommendations", self.llm.mode)
                valid = {c["id"] for c in candidates}
                if any(item.get("id") not in valid for item in ranked["items"]):
                    ranked["confidence"], error = {}, "Unknown catalog ID"
            except Exception as exc:  # 4a: ranking service unavailable, so rank by weakness tags without reasons
                ranked = {"summary": "Ranked by your weak skills only, because the AI ranking service is unavailable.",
                          "items": self._rank_by_tags(candidates, targets), "confidence": {"rules": 1.0}}
                basis, error = "tags", type(exc).__name__
        else:
            ranked = {"summary": "No library item matched your weak skills.", "items": [], "confidence": {}}
        room = max(0, self.MAX_RECOMMENDATIONS - len(generated))
        output = {"summary": ranked["summary"], "items": ranked["items"][:room] + self._label(generated, "AI-generated"), "targets": targets, "basis": basis,
                  "confidence": {**ranked["confidence"], **{item["id"]: item["confidence"] for item in generated}}}
        if error:
            output["error_type"] = error
        return output

    @staticmethod
    def _label(items: list[dict], tag: str) -> list[dict]:
        return [{**item, "label": tag} for item in items]

    def _rank_by_tags(self, candidates: list[dict], weaknesses: list[str]) -> list[dict]:
        ranked = sorted(candidates, key=lambda item: weaknesses.index(item["skill"]) if item["skill"] in weaknesses else len(weaknesses))
        return [{"id": item["id"], "title": item["title"], "skill": item["skill"], "reason": ""} for item in ranked[:self.MAX_RECOMMENDATIONS]]


class TutorAgent(Agent):
    name, memory_key = "AI Tutor", "tutor"

    def give_feedback(self, state: FlowState) -> dict:
        t = time.perf_counter()
        self.event(state, "perception", {"skill": state["skill"], "response_length": len(state["text"])})
        kit = self.toolkit(state["user_id"], state["profile"]["exam"])
        previous = kit.call("get_previous_feedback", skill=state["skill"])
        scenario = state.get("scenario", "normal")
        if scenario == "incomplete_once":  # Demo of UC9 2a: the first result is incomplete, the regenerated one is not.
            scenario = "normal" if state.get("regen_attempts") else "invalid"
        try:
            result = self.llm.feedback(state["profile"]["exam"], state["skill"], state["text"], scenario,
                                       state.get("prompt", ""), state.get("task") or "task2", state.get("metrics"), kit).model_dump()
        except Exception as exc:
            result = {"summary": "Feedback generation failed structured validation", "criteria": {}, "comments": [], "confidence": {}, "error_type": type(exc).__name__}
        kit.log(state["workflow"], self.llm.mode)
        if isinstance(previous, dict) and previous.get("criteria") and result.get("criteria"):
            before = {item["issue"] for item in previous.get("issues", []) if item.get("issue")}
            now = {item.get("issue") for item in result.get("comments", []) if item.get("issue")}
            result["since_last"] = {"date": previous["date"], "fixed": sorted(before - now)[:6], "remaining": sorted(before & now)[:6],
                                    "criteria_change": {k: round(v - previous["criteria"][k], 1) for k, v in result["criteria"].items()
                                                        if isinstance(v, (int, float)) and isinstance(previous["criteria"].get(k), (int, float))}}
        if result.get("comments"):
            issues = [c.get("issue") for c in result["comments"][:4] if c.get("issue")]
            agent_core.remember(self.db, self.memory_key, state["user_id"], f"Gave {state['skill']} ({state.get('task') or 'task'}) feedback; main issues: {'; '.join(issues) or 'none'}.",
                                data={"skill": state["skill"], "issues": issues})
        self.event(state, "handoff", {"decision": "generate feedback", "next_agent": "Assessment & Analytics", "tool": "LLM adapter"}, t)
        return {"output": result, "source_mode": self.llm.mode}


class AssessmentAgent(Agent):
    name, memory_key = "Assessment & Analytics", "assessment"
    ATTEMPTS = 2  # first try plus one retry (UC5 3a/5a, UC6 3a)

    # ---- UC5 Take Mock Examination
    def prepare_mock(self, user_id: int, exam: str, length: str) -> dict:
        """Step 3: assemble the four sections from the exam bank. 3a: retry once, then report the mock as unavailable."""
        state: FlowState = {"user_id": user_id, "workflow": "mock_exam"}
        for attempt in range(1, self.ATTEMPTS + 1):
            try:
                sections = bank.mock_sections(exam, length)
                self.event(state, "action", {"decision": "prepared mock examination", "exam": exam, "length": length, "attempt": attempt, "next_agent": "Learner"})
                return sections
            except Exception as exc:
                self.event(state, "decision", {"decision": "mock preparation failed", "attempt": attempt, "error_type": type(exc).__name__})
        raise MockUnavailable("The mock exam is temporarily unavailable. Please try again later.")

    def score_section(self, user_id: int, exam: str, skill: str, text: str, prompt: str = "", task: str = "task2", metrics: dict | None = None) -> FeedbackOutput | None:
        """Step 5: score a writing task or the speaking test against the rubric with the Assessment tools
        (band descriptors, score history, text measures). 5a: retry once; None means the section could not be scored."""
        state: FlowState = {"user_id": user_id, "workflow": "mock_exam"}
        kit = self.toolkit(user_id, exam)
        for attempt in range(1, self.ATTEMPTS + 1):
            started = time.perf_counter()
            try:
                result = self.llm.feedback(exam, skill, text, "normal", prompt, task, metrics, kit)
                kit.log("mock_exam", self.llm.mode)
                self.event(state, "action", {"decision": f"scored {skill} ({task}) against the {exam} rubric", "attempt": attempt, "criteria": result.criteria}, started)
                return result
            except Exception as exc:
                kit.log("mock_exam", self.llm.mode)
                self.event(state, "decision", {"decision": f"{skill} ({task}) could not be scored", "attempt": attempt, "error_type": type(exc).__name__}, started)
        return None

    def analyse_mock(self, user_id: int, scores: dict, overall: float, target: float | None, issues: list[str]) -> dict:
        """Steps 6-7: strengths and weaknesses, comparison with earlier assessments and readiness."""
        insights = analytics.mock_insights(self.db, user_id, scores, overall, target, issues)
        readiness = insights["readiness_detail"]
        self.event({"user_id": user_id, "workflow": "mock_exam"}, "decision", {"decision": "estimated readiness", "readiness": readiness["level"], "gap": readiness["gap"],
                   "weaknesses": [w["skill"] for w in insights["weaknesses"]], "compared_with": (insights["comparison"] or {}).get("against"), "next_agent": "Quality Manager"})
        agent_core.remember(self.db, self.memory_key, user_id, f"Mock estimate {overall}: {readiness['level']}" + (f", weakest {insights['weaknesses'][0]['skill']}" if insights["weaknesses"] else "") + ".",
                            data={"overall": overall, "readiness": readiness["level"]})
        return insights

    # ---- UC6 View Performance Report and Identify Weaknesses
    def analyse_progress(self, user_id: int) -> dict:
        """Steps 2-5: verified results across the four skills, strengths, weaknesses, repeated problems and trends.
        3a: retry the analysis once before giving up."""
        state: FlowState = {"user_id": user_id, "workflow": "report"}
        for attempt in range(1, self.ATTEMPTS + 1):
            started = time.perf_counter()
            try:
                progress = analytics.latest_progress(self.db, user_id)
                self.event(state, "perception", {"decision": "analysed verified results", "results": progress["sample_count"], "weaknesses": progress["weaknesses"],
                                                 "trends": {skill: t["direction"] for skill, t in progress["trends"].items()}, "attempt": attempt}, started)
                return progress
            except Exception as exc:
                self.db.rollback()
                if attempt == self.ATTEMPTS:
                    raise
                self.event(state, "decision", {"decision": "performance analysis failed; retrying", "attempt": attempt, "error_type": type(exc).__name__})

    def diagnose_sections(self, user_id: int, target: float | None, mock_payload: dict | None = None, texts: dict | None = None) -> dict:
        """Section by section: what went well, what to improve, missed question types and words, grammar by type."""
        sections = analytics.mock_section_report(mock_payload, texts or {}, target) if mock_payload else analytics.practice_section_report(self.db, user_id, target)
        self.event({"user_id": user_id, "workflow": "report"}, "decision", {"decision": "diagnosed each section", "sections": sorted(sections),
                   "source": "mock exam" if mock_payload else "latest practice"})
        return sections

    def write_report(self, user_id: int, exam: str, progress: dict) -> dict:
        """Step 6: the report narrative and recommendations. 6a: if they fail, keep the verified analysis without recommendations."""
        state: FlowState = {"user_id": user_id, "workflow": "report"}
        kit = self.toolkit(user_id, exam)
        data = dict(progress)
        try:
            data.update(self.llm.report(data, kit).model_dump())
            kit.log("report", self.llm.mode)
            self.event(state, "action", {"decision": "wrote performance report", "recommendations": len(data.get("recommendations", [])), "next_agent": "Quality Manager"})
        except Exception as exc:
            kit.log("report", self.llm.mode)
            scores = ", ".join(f"{skill} {score}" for skill, score in data["skill_scores"].items())
            data.update({"summary": f"Verified estimates: {scores}. {data['readiness_note']} {data['trend_note']}".strip(), "recommendations": [], "recommendations_unavailable": True,
                         "confidence": {"report": .8}})
            self.db.add(AuditLog(user_id=user_id, action="report_recommendations_failed", detail={"error_type": type(exc).__name__}))
            self.event(state, "decision", {"decision": "report saved without recommendations; retry later", "error_type": type(exc).__name__, "next_agent": "Quality Manager"})
        return data

    def provide_insights(self, state: FlowState) -> dict:
        self.event(state, "handoff", {"decision": "return verified progress insights", "weaknesses": state.get("progress", {}).get("weaknesses", []), "next_agent": "Learning Coordinator"})
        return {}

    def score(self, state: FlowState) -> dict:
        t = time.perf_counter()
        result = dict(state["output"])
        scores = result.get("criteria", {})
        result["estimated_overall"] = criterion_average.invoke({"scores": scores})
        result["score_scale"] = "IELTS 0-9 bands" if state["profile"]["exam"] == "IELTS" else "TOEFL 2026 1-6 sections"
        result["official"] = False
        kit = self.toolkit(state["user_id"], state["profile"]["exam"])
        history = kit.call("get_score_history", skill=state["workflow"])
        kit.log(state["workflow"], self.llm.mode)
        previous = next((h["estimate"] for h in history if isinstance(h.get("estimate"), (int, float))), None) if isinstance(history, list) else None
        if previous is not None and scores:
            result["trend"] = {"previous": previous, "change": round(result["estimated_overall"] - previous, 1)}
        if scores:
            agent_core.remember(self.db, self.memory_key, state["user_id"], f"{state['workflow'].title()} estimate {result['estimated_overall']}"
                                + (f" (previous {previous}, change {result['trend']['change']:+})" if previous is not None else " (first estimate)") + ".",
                                data={"skill": state["workflow"], "estimate": result["estimated_overall"]})
        self.event(state, "handoff", {"decision": "calculate indicative criterion mean and trend", "next_agent": "Quality Manager", "tool": "criterion_average, get_score_history"}, t)
        return {"output": result}


class OpsQualityManager(Agent):
    """UC9 Check Agent Output Quality. Nothing reaches the learner unless it passes here or a human approves it."""
    name, memory_key = "Quality Manager", "quality"
    MAX_REGENERATIONS = 1

    def threshold(self) -> float:
        row = self.db.get(SystemSetting, "quality_threshold")
        return float(row.value) if row else settings().quality_threshold

    def submit_result(self, state: FlowState) -> dict:
        """Graph node. Routes to release, hold, or (once, for an incomplete result) back to the producing agent."""
        t = time.perf_counter()
        payload = state["output"]
        package = self._package(state, payload)
        self._set_state(state, package, ResultStatus.VALIDATING)
        issues = self.validate(state, payload)
        types = {IssueType.INCOMPLETE} if issues else set()
        attempts = state.get("regen_attempts", 0)
        if issues and state.get("can_regenerate", True) and attempts < self.MAX_REGENERATIONS:  # 2a: ask the agent once to regenerate
            self._set_state(state, package, ResultStatus.REGENERATING)
            self.event(state, "handoff", {"package_id": package.id, "issues": issues, "decision": "regenerate incomplete result", "attempt": attempts + 1}, t)
            return {"package_id": package.id, "issues": issues, "route": "regenerate", "regen_attempts": attempts + 1}
        self._set_state(state, package, ResultStatus.CHECKING)
        if low := self.check_confidence(package.confidence):
            issues += low
            types.add(IssueType.LOW_CONFIDENCE)
        if contradictions := self.rule_based_check(payload):
            issues += contradictions
            types.add(IssueType.CONTRADICTION)
        verdict_issues, method, unchecked = self._llm_verdict(state, payload)
        issues += verdict_issues
        if verdict_issues:
            types.add(IssueType.UNCHECKED if unchecked else IssueType.CONTRADICTION)
        package.issues = issues
        self.db.add(QualityCheck(package_id=package.id, verdict="HOLD" if issues else "VERIFY", issues=issues, threshold=self.threshold(), method=method))
        self.event(state, "verification", {"package_id": package.id, "issues": issues, "issue_types": sorted(types), "method": method,
                                           "threshold": self.threshold(), "confidence": package.confidence}, t)
        if issues:
            self.hold(state, package, issues)
        else:
            self.mark_verified(state, package)
        self.db.add(AuditLog(user_id=state["user_id"], action="quality_checked", detail={"package_id": package.id, "issues": issues, "issue_types": sorted(types), "method": method}))
        self.db.flush()
        return {"package_id": package.id, "issues": issues, "route": "hold" if issues else "release"}

    def verify(self, user_id: int, workflow: str, output: dict, regenerate: Callable[[], dict] | None = None) -> ResultPackage:
        """UC9 for results produced outside a graph (reports, mocks, recommendations)."""
        state: FlowState = {"user_id": user_id, "workflow": workflow, "output": output, "source_mode": self.llm.mode, "can_regenerate": regenerate is not None}
        state.update(self.submit_result(state))
        if state["route"] == "regenerate":
            try:
                state["output"] = regenerate()
            except Exception as exc:
                state["output"] = {"items": [], "summary": "Regeneration failed", "confidence": {}, "error_type": type(exc).__name__}
            state.update(self.submit_result(state))
        if state["route"] == "release":
            self.release(state)
        else:
            self.wait_for_instructor(state)
        return self.db.get(ResultPackage, state["package_id"])

    def validate(self, state: FlowState, payload: dict) -> list[str]:
        """Structure and completeness checks (IssueType.INCOMPLETE)."""
        issues = []
        workflow = state["workflow"]
        confidence = payload.get("confidence") or {}
        if not payload or not confidence or any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in confidence.values()):
            issues.append("Missing or invalid structured output/confidence")
        if workflow in ("writing", "speaking"):
            if not payload.get("summary") or not payload.get("criteria") or not payload.get("comments"):
                issues.append("Required feedback fields missing")
            criteria = payload.get("criteria", {})
            exam = state.get("profile", {}).get("exam")
            expected = ({"task_response", "coherence", "lexical_resource", "grammar"} if workflow == "writing" else {"fluency", "lexical_resource", "grammar"}) if exam == "IELTS" else ({"task_fulfillment", "organisation", "language_use"} if workflow == "writing" else {"language_use", "topic_development"})
            if set(criteria) != expected:
                issues.append("Criteria do not match the selected exam rubric")
            if workflow == "speaking" and (payload.get("pronunciation_available") is not False or not payload.get("pronunciation_note")):
                issues.append("Speaking feedback must disclose unavailable audio assessment")
            if set(criteria) != set(confidence):
                issues.append("Every criterion requires its own confidence value")
            max_score = 9 if exam == "IELTS" else 6
            if any(not isinstance(v, (int, float)) or v < 0 or v > max_score for v in criteria.values()):
                issues.append("Criterion score outside exam scale")
        if workflow in ("plan", "adaptation") and (not payload.get("priorities") or not payload.get("activities") or not payload.get("rationale")):
            issues.append("Plan is incomplete")
        if workflow == "adaptation" and any(not str(item.get("reason", "")).strip() for item in payload.get("change_details", []) if isinstance(item, dict)):
            issues.append("Plan is incomplete: a major change has no rationale")
        # Items ranked by tags only (UC10 4a) deliberately carry no reason.
        if workflow == "recommendations" and (not payload.get("items") or any(not item.get("reason") and payload.get("basis") != "tags" for item in payload.get("items", []))):
            issues.append("Recommendation list is incomplete")
        if workflow == "mock_exam" and (set(payload.get("section_scores", {})) != {"reading", "writing", "speaking", "listening"}):
            issues.append("Mock exam requires four section scores")
        if workflow == "mock_exam" and (any(not isinstance(v, (int, float)) or v < 0 or v > (9 if payload.get("score_scale", "").startswith("IELTS") else 6) for v in payload.get("section_scores", {}).values())):
            issues.append("Mock section score outside exam scale")
        if workflow == "portrait" and (not payload.get("summary") or not payload.get("focus_areas") or not payload.get("next_steps")):
            issues.append("Learner portrait is incomplete")
        if workflow == "question" and (not payload.get("title") or not payload.get("prompt") or not payload.get("task_type")):
            issues.append("Generated question is incomplete")
        if workflow == "question" and isinstance(payload.get("content"), dict) and payload["content"].get("kind") in ("listening", "reading"):
            issues.extend(validate_test(payload["content"]))
        if workflow == "question" and "official ielts" in (str(payload.get("title", "")) + " " + str(payload.get("prompt", ""))).lower():
            issues.append("Generated question must not claim to be official IELTS content")
        return issues

    def check_confidence(self, confidence: dict) -> list[str]:
        if any(v < self.threshold() for v in confidence.values() if isinstance(v, (int, float))):
            return ["Confidence below configured threshold"]
        return []

    def rule_based_check(self, payload: dict) -> list[str]:
        """Deterministic contradiction checks. They always run, so they are also the fallback when the LLM is down."""
        issues = []
        scores = [v for v in (payload.get("criteria") or {}).values() if isinstance(v, (int, float))]
        summary = str(payload.get("summary", "")).lower()
        if scores and ("excellent" in summary or "no weaknesses" in summary) and min(scores) <= 3:
            issues.append("Rule check found score/feedback contradiction")
        if scores and isinstance(payload.get("estimated_overall"), (int, float)) and abs(payload["estimated_overall"] - criterion_average.invoke({"scores": payload["criteria"]})) > 0.5:
            issues.append("Overall estimate conflicts with criterion scores")
        targets = payload.get("targets") or []
        if targets and any(item.get("skill") not in targets for item in payload.get("items", [])):
            issues.append("Recommendation does not match the learner's assessed weaknesses")
        return issues

    def _llm_verdict(self, state: FlowState, payload: dict) -> tuple[list[str], str, bool]:
        """Ask the LLM for a structured consistency verdict. Returns (issues, method, unchecked)."""
        if payload.get("basis") in ("tags", "starter"):
            return [], "RULES", False  # No AI-written text to check; the rule checks above cover it.
        kit = Toolkit(self.db, self.memory_key, state["user_id"], (state.get("profile") or {}).get("exam", "IELTS"))
        issues = []
        try:
            verdict = self.llm.check_consistency(payload, kit)
            if not verdict.consistent:
                issues.append(verdict.reason)
            if verdict.confidence < self.threshold():
                issues.append("Consistency verdict confidence below threshold")
            method = "LLM" if self.llm.mode == "REAL" else "DEMO_RULES"
            unchecked = False
        except Exception:
            method, unchecked = "FALLBACK_RULES", True
            if self.llm.mode == "REAL":
                issues.append("LLM consistency verification unavailable")
        kit.log(state["workflow"], self.llm.mode)
        return issues, method, unchecked

    def hold(self, state: FlowState, package: ResultPackage, issues: list[str]):
        agent_core.remember(self.db, self.memory_key, state["user_id"], f"Held {state['workflow']} result #{package.id}: {'; '.join(issues)[:300]}.", data={"package_id": package.id})
        self._set_state(state, package, ResultStatus.HELD, issues=issues)
        self.notify_escalation(state, package, issues)
        self.record_issue(state, package.payload)

    def notify_escalation(self, state: FlowState, package: ResultPackage, issues: list[str]):
        """UC8 extends UC9 at "issue detected"."""
        self.db.add(Escalation(package_id=package.id, status="PENDING", reason="; ".join(issues)))
        self.event(state, "handoff", {"next_agent": "Human Instructor", "package_id": package.id})

    def record_issue(self, state: FlowState, payload: dict):
        """7a: the same issue for 5+ learners in 7 days suggests a curriculum gap."""
        if state["workflow"] not in ("writing", "speaking"):
            return
        tags = {item.get("issue") for item in payload.get("comments", []) if item.get("issue")}
        recent = self.db.scalars(select(ResultPackage).where(ResultPackage.kind == state["workflow"], ResultPackage.created_at >= datetime.now(timezone.utc)-timedelta(days=7))).all()
        for tag in tags:
            learners = {item.user_id for item in recent if any(comment.get("issue") == tag for comment in item.payload.get("comments", []))}
            if len(learners) >= 5:
                prior = self.db.scalars(select(AuditLog).where(AuditLog.action == "curriculum_gap_detected", AuditLog.created_at >= datetime.now(timezone.utc)-timedelta(days=7))).all()
                if not any(row.detail.get("issue") == tag for row in prior):
                    self.db.add(AuditLog(user_id=None, action="curriculum_gap_detected", detail={"issue": tag, "learners": len(learners)}))

    def mark_verified(self, state: FlowState, package: ResultPackage):
        self._set_state(state, package, ResultStatus.VERIFIED)

    def release(self, state: FlowState) -> dict:
        package = self.db.get(ResultPackage, state["package_id"])
        if package.state != ResultStatus.VERIFIED:
            raise RuntimeError("Unverified result cannot be released")
        package.state = ResultStatus.RELEASED
        self.event(state, "release", {"package_id": package.id, "verified": True, "result": {"summary": package.payload.get("summary"), "title": package.payload.get("title"), "estimated_overall": package.payload.get("estimated_overall")}})
        self.db.add(AuditLog(user_id=state["user_id"], action="result_released", detail={"package_id": package.id}))
        return {}

    def wait_for_instructor(self, state: FlowState) -> dict:
        self.runtime.event(state, "Human Instructor", "waiting", {"package_id": state["package_id"], "status": "durable database wait"})
        return {}

    def release_after_human(self, package: ResultPackage):
        if package.state not in (ResultStatus.APPROVED, ResultStatus.CORRECTED):
            raise RuntimeError("Human decision required before release")
        package.state = ResultStatus.RELEASED
        state: FlowState = {"user_id": package.user_id, "workflow": package.kind}
        self.event(state, "release", {"package_id": package.id, "verification": "human approval", "next_agent": "Learner", "result": {"summary": package.payload.get("summary"), "title": package.payload.get("title"), "estimated_overall": package.payload.get("estimated_overall")}})
        self.db.add(AuditLog(user_id=package.user_id, action="result_released", detail={"package_id": package.id, "by": "instructor"}))

    def _package(self, state: FlowState, payload: dict) -> ResultPackage:
        """A regenerated result keeps the same package (ResultPackage.regenAttempts in the class diagram)."""
        if state.get("package_id") and state.get("route") == "regenerate":
            package = self.db.get(ResultPackage, state["package_id"])
            package.payload, package.confidence = payload, payload.get("confidence") or {}
            return package
        package = ResultPackage(user_id=state["user_id"], kind=state["workflow"], state=ResultStatus.SUBMITTED, payload=payload, confidence=payload.get("confidence") or {},
                                source_mode=state.get("source_mode", self.llm.mode), issues=[])
        self.db.add(package)
        self.db.flush()
        self.event(state, "state", {"package_id": package.id, "state": ResultStatus.SUBMITTED})
        return package

    def _set_state(self, state: FlowState, package: ResultPackage, status: ResultStatus, **detail):
        package.state = status
        self.event(state, "state", {"package_id": package.id, "state": status, **detail})


# ---------------------------------------------------------------- central controller
class AgentRuntime:
    """Owns one of each agent and wires them into workflows (separate control from function, centralise control)."""

    def __init__(self, db: Session, provider: LLMService | None = None):
        self.db = db
        self.provider: LLMService = provider or LLMProviderAdapter()
        self.coordinator = LearningCoordinatorAgent(self)
        self.tutor = TutorAgent(self)
        self.assessment = AssessmentAgent(self)
        self.quality_manager = OpsQualityManager(self)

    def threshold(self) -> float:
        return self.quality_manager.threshold()

    def event(self, state: FlowState, agent: str, phase: str, detail: dict, started: float | None = None):
        self.db.add(AgentEvent(user_id=state["user_id"], workflow=state["workflow"], agent=agent, phase=phase, detail=detail, mode=self.provider.mode, duration_ms=int((time.perf_counter()-started)*1000) if started else 0))
        self.db.flush()

    def plan_graph(self):
        graph = StateGraph(FlowState)
        graph.add_node("request_insights", self.coordinator.request_insights)
        graph.add_node("assessment_insights", self.assessment.provide_insights)
        graph.add_node("coordinator", self.coordinator.create_plan)
        graph.add_node("quality", self.quality_manager.submit_result)
        graph.add_node("release", self.quality_manager.release)
        graph.add_node("human_wait", self.quality_manager.wait_for_instructor)
        graph.add_conditional_edges(START, lambda s: "request_insights" if s["workflow"] == "adaptation" else "coordinator", {"request_insights": "request_insights", "coordinator": "coordinator"})
        graph.add_edge("request_insights", "assessment_insights")
        graph.add_edge("assessment_insights", "coordinator")
        graph.add_conditional_edges("coordinator", lambda s: "failed" if s.get("generation_failed") else "quality", {"failed": END, "quality": "quality"})
        graph.add_conditional_edges("quality", lambda s: s["route"], {"release": "release", "hold": "human_wait", "regenerate": "coordinator"})
        graph.add_edge("release", END)
        graph.add_edge("human_wait", END)
        return graph.compile()

    def practice_graph(self):
        graph = StateGraph(FlowState)
        graph.add_node("tutor", self.tutor.give_feedback)
        graph.add_node("assessment", self.assessment.score)
        graph.add_node("quality", self.quality_manager.submit_result)
        graph.add_node("release", self.quality_manager.release)
        graph.add_node("human_wait", self.quality_manager.wait_for_instructor)
        graph.add_edge(START, "tutor")
        graph.add_edge("tutor", "assessment")
        graph.add_edge("assessment", "quality")
        graph.add_conditional_edges("quality", lambda s: s["route"], {"release": "release", "hold": "human_wait", "regenerate": "tutor"})
        graph.add_edge("release", END)
        graph.add_edge("human_wait", END)
        return graph.compile()

    def release_after_human(self, package: ResultPackage):
        self.quality_manager.release_after_human(package)

    def verify_output(self, user_id: int, workflow: str, output: dict, regenerate: Callable[[], dict] | None = None) -> ResultPackage:
        return self.quality_manager.verify(user_id, workflow, output, regenerate)
