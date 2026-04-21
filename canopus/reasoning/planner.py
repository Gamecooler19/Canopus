"""Intent classifier and execution plan builder.

The :class:`Planner` is responsible for understanding *what* the user wants
before any model token is consumed. It uses deterministic keyword heuristics
for classification — lightweight, fast, and fully testable without an LLM.

**Capability routing** is performed first: if the request matches a known
capability pattern the planner emits a plan step with ``capability_name`` set
so the executor bypasses the model provider entirely.

When a real local classifier model becomes available (Phase 4+), this module
is the natural extension point: replace :meth:`Planner._classify` with an
embedding-based or zero-shot classifier while keeping the public interface
identical.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from canopus.reasoning.types import IntentCategory, Plan, PlanStep

# ---------------------------------------------------------------------------
# Keyword sets used for lightweight intent classification
# ---------------------------------------------------------------------------

_ACTION_KEYWORDS: frozenset[str] = frozenset(
    {
        "run", "execute", "create", "delete", "move", "copy", "send", "write",
        "open", "close", "install", "remove", "set", "update", "save",
        "download", "upload", "start", "stop", "enable", "disable",
        "rename", "fetch", "build", "deploy", "schedule", "cancel", "edit",
        "add", "launch", "kill", "compress", "unzip", "backup", "restore",
    }
)

_INFORMATIONAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "what", "how", "why", "when", "where", "who", "which",
        "explain", "describe", "list", "show", "tell", "define",
        "summarize", "summarise", "search", "find", "lookup",
        "is", "are", "was", "were", "does", "do", "did",
        "compare", "difference", "meaning", "history", "overview",
    }
)

# Requests this short with no other signal are almost always conversational
_CONVERSATIONAL_WORD_THRESHOLD = 5

# ---------------------------------------------------------------------------
# Capability routing patterns
#
# Each entry is (compiled_pattern, capability_name, input_extractor).
# The input extractor receives the re.Match object and returns the inputs dict
# to pass to the capability handler.
# Patterns are evaluated in order — first match wins.
# ---------------------------------------------------------------------------

def _no_inputs(_m: re.Match[str]) -> dict[str, str]:
    return {}


def _path_from_group1(m: re.Match[str]) -> dict[str, str]:
    return {"path": m.group(1).strip()}


_CapExtractor = Callable[[re.Match[str]], dict[str, str]]

_CAPABILITY_PATTERNS: list[
    tuple[re.Pattern[str], str, _CapExtractor]
] = [
    # ── system.now ──────────────────────────────────────────────────────────
    (
        re.compile(
            r"\b(what(?:'s| is)(?: the)? (?:current )?(?:time|date|day)|"
            r"current (?:time|date|day)|"
            r"what time is it|"
            r"what day is (?:it|today)|"
            r"what(?:'s| is) today(?:'s date)?)\b",
            re.IGNORECASE,
        ),
        "system.now",
        _no_inputs,
    ),
    # ── filesystem.read_text ────────────────────────────────────────────────
    (
        re.compile(
            r"\b(?:read|open|show|cat|print|display)(?: (?:the )?(?:file|contents? of|text of))?"
            r"\s+([^\s].+?)\s*$",
            re.IGNORECASE,
        ),
        "filesystem.read_text",
        _path_from_group1,
    ),
    # ── filesystem.list_dir ─────────────────────────────────────────────────
    (
        re.compile(
            r"\b(?:list|ls|dir|show)(?: (?:the )?(?:files?(?: in)?|directory(?: contents? of)?|"
            r"contents? of|folder(?: contents? of)?))?"
            r"\s+([^\s].+?)\s*$",
            re.IGNORECASE,
        ),
        "filesystem.list_dir",
        _path_from_group1,
    ),
]


class Planner:
    """Classifies user requests and produces structured execution plans.

    The planner does not call a model. Its outputs are deterministic given
    the same input, which makes them cheap to compute and easy to test.

    Usage::

        planner = Planner()
        plan = planner.plan("what is the capital of France?")
        assert plan.intent == IntentCategory.INFORMATIONAL
    """

    def plan(self, request: str) -> Plan:
        """Classify *request* and return a structured :class:`~canopus.reasoning.types.Plan`.

        Capability routing is attempted first. If a capability matches, the
        returned plan has a single step with ``capability_name`` set and
        ``requires_capabilities=True``. Otherwise the generic intent classifier
        runs and produces a model-execution plan.

        Args:
            request: Raw user input string.

        Returns:
            A :class:`~canopus.reasoning.types.Plan` with intent, confidence,
            steps, and metadata.
        """
        cap_step = self._match_capability(request)
        if cap_step is not None:
            return Plan(
                intent=IntentCategory.ACTION_ORIENTED,
                intent_confidence=0.95,
                summary=f"Capability dispatch: {cap_step.capability_name!r}",
                steps=[cap_step],
                requires_capabilities=True,
                system_prompt_key="action_oriented",
            )

        intent, confidence = self._classify(request)
        steps = self._build_steps(intent)

        return Plan(
            intent=intent,
            intent_confidence=confidence,
            summary=self._summarize(intent, request),
            steps=steps,
            requires_capabilities=(intent == IntentCategory.ACTION_ORIENTED),
            system_prompt_key=intent.value,
        )

    # ------------------------------------------------------------------
    # Capability routing
    # ------------------------------------------------------------------

    @staticmethod
    def _match_capability(request: str) -> PlanStep | None:
        """Return a PlanStep with capability routing if *request* matches.

        Returns ``None`` when no capability pattern matches.
        """
        for pattern, cap_name, extractor in _CAPABILITY_PATTERNS:
            m = pattern.search(request)
            if m:
                inputs = extractor(m)
                return PlanStep(
                    index=0,
                    description=f"Execute capability {cap_name!r}",
                    capability_name=cap_name,
                    capability_inputs=inputs,
                )
        return None

    # ------------------------------------------------------------------
    # Generic intent classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(request: str) -> tuple[IntentCategory, float]:
        """Return (intent, confidence) for *request* using keyword heuristics."""
        words = set(re.findall(r"\b\w+\b", request.lower()))

        action_hits = len(words & _ACTION_KEYWORDS)
        info_hits = len(words & _INFORMATIONAL_KEYWORDS)

        # Very short requests with no other signals → conversational
        words_in_request = len(request.split())
        no_signal = action_hits == 0 and info_hits == 0
        if words_in_request <= _CONVERSATIONAL_WORD_THRESHOLD and no_signal:
            return IntentCategory.CONVERSATIONAL, 0.8

        if action_hits > info_hits:
            confidence = min(0.5 + action_hits * 0.1, 0.95)
            return IntentCategory.ACTION_ORIENTED, confidence

        if info_hits > 0:
            confidence = min(0.5 + info_hits * 0.1, 0.95)
            return IntentCategory.INFORMATIONAL, confidence

        # Default: treat as conversational with low confidence
        return IntentCategory.CONVERSATIONAL, 0.6

    @staticmethod
    def _build_steps(intent: IntentCategory) -> list[PlanStep]:
        """Return an ordered list of plan steps appropriate for *intent*."""
        if intent == IntentCategory.CONVERSATIONAL:
            return [
                PlanStep(index=0, description="Generate conversational response"),
            ]
        if intent == IntentCategory.INFORMATIONAL:
            return [
                PlanStep(index=0, description="Retrieve relevant context"),
                PlanStep(index=1, description="Generate informative response"),
            ]
        # ACTION_ORIENTED
        return [
            PlanStep(index=0, description="Identify required capabilities"),
            PlanStep(index=1, description="Validate permissions"),
            PlanStep(index=2, description="Execute action"),
            PlanStep(index=3, description="Report outcome"),
        ]

    @staticmethod
    def _summarize(intent: IntentCategory, request: str) -> str:
        """Return a short one-line plan summary suitable for trace storage."""
        prefix = {
            IntentCategory.CONVERSATIONAL: "Conversational exchange",
            IntentCategory.INFORMATIONAL: "Information retrieval",
            IntentCategory.ACTION_ORIENTED: "Action execution",
        }[intent]
        snippet = request[:60] + ("…" if len(request) > 60 else "")
        return f"{prefix}: {snippet!r}"
