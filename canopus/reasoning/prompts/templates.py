"""Prompt template management for the Canopus reasoning pipeline.

All prompt strings live here. Callers should never inline literal prompt text
in business logic. Instead, use :func:`get_system_prompt` and
:func:`build_prompt` to construct requests.

Adding or adjusting prompts for different intents, personas, or profile modes
should require a change only in this module.
"""

from __future__ import annotations

from canopus.reasoning.types import IntentCategory, Plan

# ---------------------------------------------------------------------------
# System prompt registry
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS: dict[IntentCategory, str] = {
    IntentCategory.CONVERSATIONAL: (
        "You are Canopus, a CLI-native AI assistant. "
        "Respond in a concise, helpful, and natural way. "
        "Keep responses brief and suitable for a terminal — no markdown headers, "
        "no bullet overload. Plain conversational text only."
    ),
    IntentCategory.INFORMATIONAL: (
        "You are Canopus, a CLI-native AI assistant. "
        "Provide accurate, well-structured information. "
        "Be concise. Prefer plain text with minimal formatting, "
        "suitable for a terminal display. Cite sources when you know them."
    ),
    IntentCategory.ACTION_ORIENTED: (
        "You are Canopus, a CLI-native AI assistant. "
        "The user wants to perform a specific action or task. "
        "Describe clearly what you will do or have done. "
        "If the action requires capabilities not yet available, say so explicitly "
        "and suggest what the user can configure to enable it."
    ),
}

_DEFAULT_SYSTEM = (
    "You are Canopus, a CLI-native AI assistant. "
    "Respond helpfully, concisely, and accurately."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_system_prompt(intent: IntentCategory) -> str:
    """Return the system prompt for the given intent category.

    Args:
        intent: The classified intent of the user's request.

    Returns:
        A system prompt string appropriate for the intent.
    """
    return _SYSTEM_PROMPTS.get(intent, _DEFAULT_SYSTEM)


def build_prompt(
    plan: Plan,
    original_request: str,
    *,
    memory_block: str = "",
) -> tuple[str, str]:
    """Build a (system_prompt, user_prompt) pair for the model request.

    The user prompt embeds the original request alongside the plan's steps so
    that a model — when one is configured — can ground its response in the
    planner's intent and structure.

    Args:
        plan: The :class:`~canopus.reasoning.types.Plan` produced by the planner.
        original_request: The verbatim user input string.
        memory_block: Optional pre-formatted memory context block to prepend
            to the user prompt. Produced by
            :meth:`~canopus.memory.models.MemoryContext.as_prompt_block`.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple, both plain strings.
    """
    system_prompt = get_system_prompt(plan.intent)

    step_lines = "\n".join(
        f"  {step.index + 1}. {step.description}" for step in plan.steps
    )

    memory_section = f"{memory_block}\n\n" if memory_block else ""
    user_prompt = (
        f"{memory_section}"
        f"Request: {original_request}\n\n"
        f"Planned approach:\n{step_lines}\n\n"
        "Please respond to the request."
    )

    return system_prompt, user_prompt
