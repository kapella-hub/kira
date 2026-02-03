"""Plan revision based on failure analysis."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .models import (
    CorrectionStrategy,
    ExecutionAttempt,
    FailureAnalysis,
    RevisionResult,
)

if TYPE_CHECKING:
    from ..core.client import KiraClient
    from ..thinking.models import ExecutionStep, RefinedPlan


class PlanReviser:
    """Revises execution plans based on failure analysis."""

    def __init__(self, client: KiraClient | None = None):
        """Initialize reviser.

        Args:
            client: Optional KiraClient for LLM-based revision.
        """
        self.client = client

    def revise_quick(
        self,
        step: ExecutionStep,
        analysis: FailureAnalysis,
    ) -> RevisionResult:
        """Quick plan revision without LLM call.

        Args:
            step: The step that failed.
            analysis: Analysis of the failure.

        Returns:
            Revised step.
        """
        strategy = analysis.recommended_strategy
        changes: list[str] = []

        revised_action = step.action
        revised_details = step.details

        if strategy == CorrectionStrategy.RETRY_SAME:
            # Minor fix - just add error handling note
            revised_details = f"{step.details}\nNote: Previous attempt failed with {analysis.failure_type.value}. Fix: {analysis.suggested_fixes[0] if analysis.suggested_fixes else 'Review carefully.'}"
            changes.append("Added note about previous failure")

        elif strategy == CorrectionStrategy.MODIFY_APPROACH:
            # Modify based on suggested fixes
            if analysis.suggested_fixes:
                revised_details = (
                    f"{step.details}\n\nIMPORTANT: {analysis.root_cause}\nApply fixes:\n"
                )
                for fix in analysis.suggested_fixes:
                    revised_details += f"- {fix}\n"
                changes.append("Added specific fixes to apply")
            else:
                revised_details = f"{step.details}\n\nAddress: {analysis.root_cause}"
                changes.append("Added root cause to address")

        elif strategy == CorrectionStrategy.ALTERNATIVE_APPROACH:
            # Suggest trying different approach
            revised_action = f"TRY ALTERNATIVE: {step.action}"
            revised_details = f"Previous approach failed repeatedly. Root cause: {analysis.root_cause}\n\nTry a different implementation strategy. Consider:\n"
            for factor in analysis.contributing_factors[:2]:
                revised_details += f"- Avoid: {factor}\n"
            changes.append("Switched to alternative approach")

        elif strategy == CorrectionStrategy.SIMPLIFY:
            # Break down into smaller steps
            revised_action = f"SIMPLIFIED: {step.action}"
            revised_details = f"Break this into smaller steps:\n1. First, verify prerequisites\n2. Then, implement core logic only\n3. Finally, add error handling\n\nOriginal: {step.details}"
            changes.append("Simplified step into smaller parts")

        elif strategy == CorrectionStrategy.SEEK_HELP:
            # Mark as needing help
            revised_action = f"NEEDS HELP: {step.action}"
            revised_details = f"This step requires human intervention.\nReason: {analysis.root_cause}\nAttempted fixes:\n"
            for fix in analysis.suggested_fixes:
                revised_details += f"- {fix}\n"
            changes.append("Marked as needing human help")

        return RevisionResult(
            original_step=step.action,
            revised_step=revised_action,
            revision_reasoning=f"Applied {strategy.value} strategy due to {analysis.failure_type.value}",
            strategy_used=strategy,
            changes_made=changes,
        )

    async def revise_deep(
        self,
        step: ExecutionStep,
        analysis: FailureAnalysis,
        task: str,
        attempts: list[ExecutionAttempt],
    ) -> RevisionResult:
        """Deep LLM-based plan revision.

        Args:
            step: The step that failed.
            analysis: Analysis of the failure.
            task: Original task description.
            attempts: Previous execution attempts.

        Returns:
            Revised step with LLM reasoning.
        """
        if not self.client:
            return self.revise_quick(step, analysis)

        attempts_context = "\n".join(a.to_context() for a in attempts[-3:])

        prompt = f"""Revise this execution step based on failure analysis.

ORIGINAL TASK: {task}

FAILED STEP:
Action: {step.action}
Details: {step.details}
Expected: {step.expected_outcome}

FAILURE ANALYSIS:
{analysis.to_context()}

PREVIOUS ATTEMPTS:
{attempts_context}

Provide a revised step that addresses the failure. Respond with:

[REVISED_ACTION:text]
The new action description.

[REVISED_DETAILS:text]
New detailed instructions that fix the issues.

[REASONING:text]
Why this revision should work.

[CHANGES:change1|change2|change3]
List of specific changes made.
"""

        output_parts: list[str] = []
        async for chunk in self.client.run(prompt):
            output_parts.append(chunk)
        raw_output = "".join(output_parts)

        return self._parse_revision(raw_output, step, analysis)

    def revise_plan(
        self,
        plan: RefinedPlan,
        failed_step_index: int,
        analysis: FailureAnalysis,
    ) -> RefinedPlan:
        """Revise an entire plan based on a failed step.

        Args:
            plan: The original plan.
            failed_step_index: Index of the step that failed.
            analysis: Analysis of the failure.

        Returns:
            New plan with revised steps.
        """
        from ..thinking.models import ExecutionStep, RefinedPlan

        new_steps: list[ExecutionStep] = []
        refinements = list(plan.refinements_made)

        for i, step in enumerate(plan.final_steps):
            if i < failed_step_index:
                # Steps before failure - keep as is
                new_steps.append(step)
            elif i == failed_step_index:
                # The failed step - revise it
                revision = self.revise_quick(step, analysis)
                new_step = ExecutionStep(
                    number=step.number,
                    action=revision.revised_step,
                    details=step.details,  # Keep original details
                    expected_outcome=step.expected_outcome,
                    verification=f"Verify fix for: {analysis.root_cause}",
                )
                new_steps.append(new_step)
                refinements.append(f"Revised step {step.number}: {revision.revision_reasoning}")
            else:
                # Steps after failure - may need adjustment
                new_steps.append(step)

        return RefinedPlan(
            original_plan=plan.original_plan,
            refinements_made=refinements,
            final_steps=new_steps,
            final_summary=plan.final_summary,
            confidence_score=max(0.3, plan.confidence_score - 0.1),  # Reduce confidence
            raw_output=plan.raw_output,
        )

    def _parse_revision(
        self,
        raw_output: str,
        step: ExecutionStep,
        analysis: FailureAnalysis,
    ) -> RevisionResult:
        """Parse LLM revision output."""
        action_match = re.search(r"\[REVISED_ACTION:([^\]]+)\]", raw_output)
        reasoning_match = re.search(r"\[REASONING:([^\]]+)\]", raw_output)
        changes_match = re.search(r"\[CHANGES:([^\]]+)\]", raw_output)

        revised_action = action_match.group(1).strip() if action_match else step.action
        reasoning = (
            reasoning_match.group(1).strip()
            if reasoning_match
            else f"Applied {analysis.recommended_strategy.value}"
        )
        changes = (
            [c.strip() for c in changes_match.group(1).split("|")]
            if changes_match
            else ["Revised based on failure analysis"]
        )

        return RevisionResult(
            original_step=step.action,
            revised_step=revised_action,
            revision_reasoning=reasoning,
            strategy_used=analysis.recommended_strategy,
            changes_made=changes,
        )
