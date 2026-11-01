"""LLM Integration package from the Stage 1 class diagram.

Agents depend on the LLMService interface, never on a concrete provider, so a
second provider (another cloud API or a local model) is a new class that
realises this interface. LLMProviderAdapter in agents.py is the current one.
"""
from abc import ABC, abstractmethod
from enum import StrEnum


class ResultStatus(StrEnum):
    """States of a ResultPackage (UC9 state machine). Stored as plain strings."""
    SUBMITTED = "SUBMITTED"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    REGENERATING = "REGENERATING"
    CHECKING = "CHECKING"
    HELD = "HELD"
    VERIFIED = "VERIFIED"
    RELEASED = "RELEASED"
    # UC8 extends UC9: the instructor's review of a held result.
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    CORRECTED = "CORRECTED"


class IssueType(StrEnum):
    INCOMPLETE = "INCOMPLETE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONTRADICTION = "CONTRADICTION"
    UNCHECKED = "UNCHECKED"


class AgentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    UNAVAILABLE = "UNAVAILABLE"


class LLMService(ABC):
    """«interface» LLMService. `mode` is REAL (cloud model) or LOCAL (built-in engine)."""
    mode: str

    @abstractmethod
    def structured(self, schema, system: str, user: dict, local: dict, toolkit=None, scoring: bool = False):
        """generate(): one structured model call, validated against `schema`."""

    @abstractmethod
    def check_consistency(self, payload: dict, toolkit=None):
        """Return a Verdict (consistent, reason, confidence) for feedback against its scores.
        One attempt; the Quality Manager owns the single retry (UC9 4a)."""

    @abstractmethod
    def rank_and_explain(self, weaknesses: list[str], candidates: list[dict], toolkit=None):
        """Rank candidate materials for the weaknesses and give a one-line reason for each."""

    @abstractmethod
    def generate_exercise(self, exam: str, skill: str, level: str) -> dict:
        """Write a short targeted exercise when the library has nothing for a weakness."""
