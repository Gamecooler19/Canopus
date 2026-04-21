"""Reflector — validates execution results and determines final response.

The :class:`Reflector` is the last stage of the reasoning pipeline. It
evaluates the raw model output for obvious quality signals and decides:

- Is the response valid and ready for the user?
- Should the pipeline retry with the same or a different provider?
- Is the response completely unusable?

In Phase 2 the reflector applies lightweight structural checks (empty
response, minimum length). Future phases can extend it with semantic
validation, hallucination detection, and confidence scoring.
"""

from __future__ import annotations

from canopus.reasoning.types import ExecutionResult, ReflectionOutcome, ReflectionResult

# Minimum character length for a response to be considered non-trivial
_MIN_RESPONSE_CHARS = 10


class Reflector:
    """Evaluates an :class:`~canopus.reasoning.types.ExecutionResult` and
    produces a :class:`~canopus.reasoning.types.ReflectionResult`.

    The reflector does **not** call the model. All checks are deterministic
    and operate on the raw response text.

    Usage::

        reflector = Reflector()
        reflection = reflector.reflect(execution_result)
        print(reflection.final_response)
    """

    def reflect(
        self,
        result: ExecutionResult,
        *,
        retry_count: int = 0,
        max_retries: int = 0,
    ) -> ReflectionResult:
        """Evaluate *result* and return the final reflection.

        Args:
            result: The execution result to evaluate.
            retry_count: How many retries have already been attempted. Used
                to populate the returned :class:`~canopus.reasoning.types.ReflectionResult`.
            max_retries: Maximum retries allowed by the caller. When
                ``retry_count < max_retries`` and issues are found, the
                outcome is :attr:`~canopus.reasoning.types.ReflectionOutcome.NEEDS_RETRY`
                rather than :attr:`~canopus.reasoning.types.ReflectionOutcome.FAILED`.

        Returns:
            A :class:`~canopus.reasoning.types.ReflectionResult` with the
            determined outcome and the final response string.
        """
        issues = self._detect_issues(result.raw_response)

        if not issues:
            return ReflectionResult(
                execution=result,
                outcome=ReflectionOutcome.VALID,
                issues=[],
                final_response=result.raw_response.strip(),
                retry_count=retry_count,
            )

        # There are issues — decide between retry and failure
        if retry_count < max_retries:
            outcome = ReflectionOutcome.NEEDS_RETRY
        else:
            outcome = ReflectionOutcome.FAILED

        fallback = self._fallback_message(issues)
        return ReflectionResult(
            execution=result,
            outcome=outcome,
            issues=issues,
            final_response=fallback,
            retry_count=retry_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_issues(text: str) -> list[str]:
        """Return a list of issue descriptions for *text*, or empty if clean."""
        issues: list[str] = []
        stripped = text.strip()

        if not stripped:
            issues.append("Response is empty")
            return issues

        if len(stripped) < _MIN_RESPONSE_CHARS:
            issues.append(
                f"Response is too short ({len(stripped)} chars, "
                f"minimum {_MIN_RESPONSE_CHARS})"
            )

        return issues

    @staticmethod
    def _fallback_message(issues: list[str]) -> str:
        """Build a user-visible fallback message describing the detected issues."""
        issue_text = "; ".join(issues)
        return (
            f"The assistant could not generate a useful response ({issue_text}). "
            "Please try rephrasing your request."
        )
