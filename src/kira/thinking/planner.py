"""ThinkingPlanner - Phase 1 of two-phase execution."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .models import Complexity, ThinkingPlan

if TYPE_CHECKING:
    from ..core.client import KiraClient


class ThinkingPlanner:
    """Phase 1: Analyze task and create execution plan.

    Sends the task to kiro-cli with planning instructions,
    then parses the structured output into a ThinkingPlan.
    """

    PLANNING_PROMPT = """Analyze this task and create an execution plan.

Think through the task carefully before providing your plan.

Output your analysis in this EXACT format (use these markers):

[PLAN:summary] One sentence summary of what needs to be done
[PLAN:complexity] simple OR moderate OR complex
[PLAN:effort] quick OR medium OR significant
[PLAN:steps]
1. First step to take
2. Second step to take
3. Third step (add more as needed)
[PLAN:considerations]
- Important consideration 1
- Important consideration 2
[PLAN:end]

Now analyze this task:
"""

    def __init__(self, kiro_client: "KiraClient"):
        self.client = kiro_client

    async def analyze(self, prompt: str, context: str = "") -> ThinkingPlan:
        """Run Phase 1: Generate execution plan.

        Args:
            prompt: The user's task/prompt
            context: Optional context (e.g., memory) to include

        Returns:
            Structured ThinkingPlan
        """
        # Build planning prompt
        planning_prompt = self.PLANNING_PROMPT
        if context:
            planning_prompt = f"## Context\n\n{context}\n\n---\n\n{planning_prompt}"
        planning_prompt += f"\n{prompt}"

        # Execute via kiro-cli
        result = await self.client.run_batch(planning_prompt)

        # Parse the structured output
        return self._parse_plan(result.output, prompt)

    def _parse_plan(self, output: str, original_prompt: str) -> ThinkingPlan:
        """Parse structured plan from LLM output."""
        # Extract summary
        summary_match = re.search(r"\[PLAN:summary\]\s*(.+?)(?=\[PLAN:|$)", output, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else original_prompt[:100]

        # Extract complexity
        complexity_match = re.search(r"\[PLAN:complexity\]\s*(\w+)", output, re.IGNORECASE)
        complexity = Complexity.MODERATE
        if complexity_match:
            complexity = Complexity.from_string(complexity_match.group(1))

        # Extract effort
        effort_match = re.search(r"\[PLAN:effort\]\s*(\w+)", output, re.IGNORECASE)
        effort = effort_match.group(1).strip() if effort_match else "medium"

        # Extract steps
        steps: list[str] = []
        steps_match = re.search(
            r"\[PLAN:steps\]\s*(.+?)(?=\[PLAN:|$)", output, re.DOTALL | re.IGNORECASE
        )
        if steps_match:
            steps_text = steps_match.group(1)
            # Parse numbered list
            step_matches = re.findall(r"^\d+\.\s*(.+)$", steps_text, re.MULTILINE)
            steps = [s.strip() for s in step_matches if s.strip()]

        # Extract considerations
        considerations: list[str] = []
        considerations_match = re.search(
            r"\[PLAN:considerations\]\s*(.+?)(?=\[PLAN:|$)", output, re.DOTALL | re.IGNORECASE
        )
        if considerations_match:
            considerations_text = considerations_match.group(1)
            # Parse bullet list
            consideration_matches = re.findall(r"^[-*]\s*(.+)$", considerations_text, re.MULTILINE)
            considerations = [c.strip() for c in consideration_matches if c.strip()]

        return ThinkingPlan(
            task_summary=summary,
            complexity=complexity,
            steps=steps,
            considerations=considerations,
            estimated_effort=effort,
            raw_output=output,
        )
