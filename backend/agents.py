"""Executable StateGraphs. All model access goes through ProviderAdapter."""
import time
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.config import settings
from backend.models import AgentEvent, AuditLog, Escalation, QualityCheck, ResultPackage, SystemSetting
from backend.schemas import FeedbackOutput, PlanOutput, VerdictOutput, RecommendationOutput, ReportNarrative, OnboardingExtraction, PortraitOutput, QuestionOutput, AgentChatReply
from backend.onboarding import parse_demo_message


class FlowState(TypedDict, total=False):
    user_id: int
    workflow: str
    profile: dict
    progress: dict
    skill: str
    text: str
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


class ProviderAdapter:
    def __init__(self):
        self.config = settings()
        self.mode = "DEMO" if self.config.demo_mode else "REAL"
        if not self.config.demo_mode and not self.config.openai_api_key:
            raise RuntimeError("REAL AI MODE requires OPENAI_API_KEY")
        self.llm = None if self.config.demo_mode else ChatOpenAI(model=self.config.llm_model, api_key=self.config.openai_api_key, timeout=30, max_retries=1)

    def structured(self, schema, system: str, user: dict, demo: dict):
        if self.config.demo_mode:
            return schema.model_validate(demo)
        # Caller passes only exam goals, learning text and scores; account identity is excluded.
        import json
        chain = self.llm.with_structured_output(schema)
        messages = [("system", system), ("human", json.dumps(user, ensure_ascii=False))]
        try:
            return chain.invoke(messages)
        except Exception:
            return chain.invoke(messages)  # One bounded retry before the caller holds the result.

    def extract_onboarding(self, message: str, draft: dict) -> OnboardingExtraction:
        demo = parse_demo_message(message, draft)
        return self.structured(
            OnboardingExtraction,
            "Extract only explicitly stated IELTS/TOEFL learner goals from the latest message. "
            "Do not invent missing values. Dates must be YYYY-MM-DD. Skills must be writing, speaking, reading or listening. "
            "Return null for fields not supplied in the latest message.",
            {"latest_message": message, "current_draft": draft}, demo,
        )

    def chat(self, context: str, message: str, profile: dict, plan: dict | None, history: list[dict]) -> AgentChatReply:
        """Instructional conversation; formal scores and plans use the verified workflows."""
        skill = context if context in ("speaking", "writing", "reading", "listening") else None
        lower = message.lower()
        if skill == "speaking":
            if any(word in lower for word in ("hello", "start", "question", "practice")):
                reply = "Let's practise speaking. Tell me about a skill you learned recently. What was difficult at first, and how did you improve? Record your answer with the microphone, then I can ask a follow-up."
            elif len(message.split()) < 8:
                reply = "Can you add one concrete example? Describe what happened and why it mattered. You can answer aloud using the microphone."
            else:
                reply = "Thanks. What would you do differently if you had to learn that skill again? Give one reason and an example. For assessed feedback, submit your recorded practice response."
        elif skill:
            tips = {"writing": "State a clear position, then support each paragraph with a reason and example.", "reading": "Find the sentence in the passage that supports your answer before choosing it.", "listening": "Listen for corrections and signposts, then write down the final detail."}
            reply = f"For {skill} practice, {tips[skill]} Tell me which part is difficult, or submit a task for quality-checked feedback."
        else:
            priorities = ", ".join(profile.get("priority_skills", [])) or "your chosen skills"
            if "plan" in lower or "schedule" in lower:
                reply = f"Your current focus is {priorities}. You have {profile.get('weekly_hours', 0)} study hours per week. Use the Learning plan page to create or request a verified plan change."
            elif "profile" in lower or "goal" in lower:
                reply = f"Your stated goal is {profile.get('exam')} {profile.get('target_score')} by {profile.get('exam_date')}. Your self-reported level is {profile.get('proficiency')}. You can edit these details on My profile."
            else:
                reply = f"I can help you understand your {profile.get('exam')} goal, profile and learning plan. Your stated priorities are {priorities}. What would you like to work on?"
        if self.config.demo_mode:
            return AgentChatReply(reply="DEMO assistant: " + reply)
        return self.structured(
            AgentChatReply,
            f"You are the {'AI Tutor' if skill else 'Learning Coordinator'} in a learner-facing conversation about {context}. "
            "Be concise, warm and ask at most one follow-up. Do not claim an official IELTS/TOEFL score, calibrated confidence, "
            "verified plan or pronunciation analysis. Formal evaluations and recommendations require a separate quality-checked workflow. "
            "Never ask for passwords or personal identity details.",
            {"message": message, "profile": profile, "active_plan": plan, "recent_messages": history[-8:]},
            {"reply": reply},
        )

    def portrait(self, profile: dict) -> PortraitOutput:
        priorities = profile["priority_skills"]
        demo = {
            "summary": f"Demo starting portrait for a {profile['proficiency']} {profile['exam']} learner. This reflects stated goals, not measured ability.",
            "goal": f"Reach an estimated {profile['target_score']} by {profile['exam_date']}.",
            "focus_areas": priorities,
            "starting_point": f"Self-reported {profile['proficiency']} level; confirm with practice results.",
            "study_rhythm": f"{profile['weekly_hours']} hours per week available.",
            "next_steps": [f"Complete a {skill} diagnostic practice" for skill in priorities[:2]],
            "confidence": {"portrait": .84},
        }
        return self.structured(
            PortraitOutput,
            "You are the Learning Coordinator. Create a concise learning portrait from stated goals only. "
            "Never claim a measured strength without verified performance. Give a self-reported heuristic confidence.",
            {"profile": profile}, demo,
        )

    def generate_question(self, exam: str, skill: str, topic: str) -> QuestionOutput:
        demo = {
            "title": f"{topic.title()} — {skill} practice",
            "prompt": (f"Some people think {topic} should receive greater public support, while others disagree. "
                       "Discuss both views and give your own opinion with examples." if skill == "writing" else
                       f"Describe an experience connected with {topic}. Explain what happened, who was involved, "
                       "and why this experience was memorable."),
            "task_type": "Academic Task 2" if skill == "writing" else "Part 2 cue card",
            "confidence": {"task": .84},
        }
        return self.structured(
            QuestionOutput,
            "Create one ORIGINAL IELTS-style task, never reproduce an official or memorised question. "
            "Use Academic Writing Task 2 or Speaking Part 2 format as requested. "
            "Do not call it an official IELTS question. Return a self-reported task confidence.",
            {"exam": exam, "skill": skill, "topic": topic}, demo,
        )

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
        activities = [{"skill": skill, "title": f"{skill.title()} practice", "minutes_per_week": round(total_minutes * (.4 if index == 0 else .2)), "reason": "Priority from learner goals, change request or recent performance"} for index, skill in enumerate(priorities)]
        demo = {"title": f"{profile['exam']} {'adapted' if adaptation else 'revised' if change_request else 'starter'} plan", "rationale": f"Focus on {', '.join(priorities[:2])} within {profile['weekly_hours']} study hours each week before {profile['exam_date']}." + (f" Learner requested: {change_request}." if change_request else ""), "priorities": priorities, "activities": activities, "changes": (["Increase practice on recent weak skills"] if adaptation else []) + ([f"Consider learner request: {change_request}"] if change_request else []), "confidence": {"plan": .87}}
        return self.structured(PlanOutput, "You are the Learning Coordinator. Propose actionable IELTS or TOEFL study activities. Return confidence as a self-reported heuristic, not a calibrated probability.", {"profile": profile, "progress": progress, "adaptation": adaptation}, demo)

    def prompt(self, exam: str, skill: str, proficiency: str = "intermediate") -> dict:
        prompts = {
            "writing": "Some employers allow remote work. Discuss benefits and drawbacks and support your position with examples." if exam == "IELTS" else "In an academic discussion, explain whether flexible work improves productivity and support your view with an example.",
            "speaking": "Describe a professional skill you learned. Explain how you learned it and why it matters." if exam == "IELTS" else "Do you prefer working alone or in a team? Give reasons and an example.",
            "reading": "Passage: Flexible working can reduce commuting time, but research also identifies communication challenges. Teams that set clear routines often report stronger collaboration. Question: What can help teams collaborate?",
            "listening": "Transcript for demo listening: The seminar starts at nine, but the workshop has moved to ten. Bring your notes to the workshop. Question: When is the workshop?",
        }
        guidance = ("Start with one clear reason and example." if proficiency == "beginner" else "Include a counterargument or more nuanced example." if proficiency == "advanced" else "Support your answer with a specific example.") if skill in ("writing", "speaking") else ""
        if self.config.demo_mode:
            return {"title": f"{exam} {skill.title()} practice", "text": prompts[skill] + " " + guidance, "answer_key": "clear routines" if skill == "reading" else "ten" if skill == "listening" else None, "mode": "DEMO", "duration_seconds": 120 if skill == "speaking" else 2400 if skill == "writing" else 600}
        # The LLM generates only task text; deterministic answers are kept for objective prototype tasks.
        if skill in ("reading", "listening"):
            return {"title": f"{exam} {skill.title()} practice", "text": prompts[skill] + " " + guidance, "answer_key": "clear routines" if skill == "reading" else "ten", "mode": "REAL", "duration_seconds": 600}
        response = self.llm.invoke([("system", f"Write one original {exam} {skill} practice task. Return only the task text."), ("human", f"Level: {proficiency}")])
        return {"title": f"{exam} {skill.title()} practice", "text": response.content, "answer_key": None, "mode": "REAL", "duration_seconds": 120 if skill == "speaking" else 2400}

    def feedback(self, exam: str, skill: str, text: str, scenario: str) -> FeedbackOutput:
        words = text.split()
        if exam == "IELTS":
            labels = ["task_response", "coherence", "lexical_resource", "grammar"] if skill == "writing" else ["fluency", "lexical_resource", "grammar", "pronunciation"]
            base = 6.0 if len(words) >= 20 else 5.5
            scores = {label: base for label in labels}
        else:
            labels = ["task_fulfillment", "organisation", "language_use"] if skill == "writing" else ["delivery", "language_use", "topic_development"]
            base = 4.0 if len(words) >= 20 else 3.5
            scores = {label: base for label in labels}
        if skill == "speaking":
            scores.pop("pronunciation" if exam == "IELTS" else "delivery")  # Audio delivery cannot be inferred from text.
        demo = {"summary": "Demo heuristic feedback: the response addresses the task; add more specific evidence and clearer transitions.", "criteria": scores, "comments": [{"sentence": text.split(".")[0][:160], "issue": "Develop the supporting example", "suggestion": "Add one concrete example and explain how it supports your claim."}], "improvements": ["Use a specific example", "Check paragraph transitions"], "confidence": {label: (.42 if scenario == "low_confidence" else .84) for label in scores}, "pronunciation_available": False, "pronunciation_note": "Audio pronunciation/delivery assessment is unavailable. Transcript-based fluency is approximate; timing and acoustics are not assessed." if skill == "speaking" else None}
        if scenario == "contradiction":
            first = next(iter(scores))
            demo["summary"] = f"Excellent {first.replace('_', ' ')} with no weaknesses."
            demo["criteria"][first] = 2.0
        if scenario == "invalid":
            demo["confidence"] = {}
        system = f"You are an exam practice tutor and assessor. Use distinct {exam} {skill} criteria. Return exactly these criterion keys: {', '.join(scores)}. TOEFL 2026 uses 1-6 section scale; IELTS uses 0-9 bands. Never infer pronunciation or audio delivery from text. For speaking mark pronunciation_available false and explain the missing audio assessment. Provide sentence-specific feedback and self-reported confidence for every criterion. These are unofficial estimates."
        return self.structured(FeedbackOutput, system, {"exam": exam, "skill": skill, "response": text[:12000]}, demo)

    def consistency(self, payload: dict) -> VerdictOutput:
        scores = payload.get("criteria", {})
        summary = payload.get("summary", "").lower()
        issues = bool(scores) and ("excellent" in summary or "no weaknesses" in summary) and min(scores.values()) <= 3
        demo = {"consistent": not issues, "reason": "Praise conflicts with a very low criterion score" if issues else "No obvious score and feedback contradiction", "confidence": .85}
        return self.structured(VerdictOutput, "Check whether feedback statements contradict criterion scores. Be conservative and return a short reason.", {"summary": payload.get("summary"), "criteria": scores, "comments": payload.get("comments", [])}, demo)

    def recommendations(self, catalog: list[dict], priorities: list[str]) -> RecommendationOutput:
        ranked = sorted(catalog, key=lambda item: item["skill"] not in priorities)[:4]
        demo = {"items": [{"id": item["id"], "title": item["title"], "skill": item["skill"], "reason": "Targets a priority or recent weak skill", "confidence": .84} for item in ranked], "summary": "Ranked study material suggestions", "confidence": {str(item["id"]): .84 for item in ranked}}
        return self.structured(RecommendationOutput, "You are the Learning Coordinator. Rank only catalog IDs provided, explain each match and return self-reported confidence per item.", {"catalog": catalog, "priorities": priorities}, demo)

    def report(self, progress: dict) -> ReportNarrative:
        demo = {"summary": "Demo estimate from verified practice results. Continue work on the lowest-scoring skills.", "recommendations": [f"Practise {skill} twice this week" for skill in progress.get("weaknesses", [])] or ["Collect more practice results"], "confidence": {"report": .81}}
        return self.structured(ReportNarrative, "You are the Assessment and Analytics agent. Explain observed scores conservatively; readiness is an estimate and never an official score. Return self-reported confidence.", progress, demo)


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
            result = self.provider.feedback(state["profile"]["exam"], state["skill"], state["text"], state.get("scenario", "normal")).model_dump()
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
