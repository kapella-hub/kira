"""ThinkingExecutor - Phase 2 of two-phase execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from .models import ThinkingPlan

if TYPE_CHECKING:
    from ..core.client import KiraClient
    from ..core.session import SessionManager


class ThinkingExecutor:
    """Phase 2: Execute with plan context injected.

    Takes the plan from Phase 1 and executes the task
    with the plan injected as context.
    """

    def __init__(
        self,
        kiro_client: "KiraClient",
        session_manager: "SessionManager | None" = None,
    ):
        self.client = kiro_client
        self.session = session_manager

    async def execute(
        self,
        prompt: str,
        plan: ThinkingPlan,
        additional_context: str = "",
    ) -> AsyncIterator[str]:
        """Execute task with plan injected as context.

        Args:
            prompt: The original user prompt
            plan: The thinking plan from Phase 1
            additional_context: Extra context (e.g., memory)

        Yields:
            Output chunks from kiro-cli
        """
        # Build execution prompt
        execution_prompt = self._build_execution_prompt(prompt, plan, additional_context)

        # Stream output
        async for chunk in self.client.run(execution_prompt):
            yield chunk

    async def execute_batch(
        self,
        prompt: str,
        plan: ThinkingPlan,
        additional_context: str = "",
    ) -> str:
        """Execute and return complete result (non-streaming)."""
        execution_prompt = self._build_execution_prompt(prompt, plan, additional_context)
        result = await self.client.run_batch(execution_prompt)
        return result.output

    def _build_execution_prompt(
        self,
        prompt: str,
        plan: ThinkingPlan,
        additional_context: str = "",
    ) -> str:
        """Build the execution prompt with plan context."""
        parts: list[str] = []

        # Add additional context if provided
        if additional_context:
            parts.append("## Context")
            parts.append("")
            parts.append(additional_context)
            parts.append("")
            parts.append("---")
            parts.append("")

        # Add the execution plan
        parts.append("## Execution Plan (from analysis phase)")
        parts.append("")
        parts.append(plan.to_context())
        parts.append("")
        parts.append("---")
        parts.append("")

        # Add instructions
        parts.append("## Instructions")
        parts.append("")
        parts.append("Follow the execution plan above to complete this task.")
        parts.append("Work through each step systematically.")
        parts.append("")
        parts.append("---")
        parts.append("")

        # Add the original task
        parts.append("## Task")
        parts.append("")
        parts.append(prompt)

        return "\n".join(parts)
