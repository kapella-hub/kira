"""Self-correction loop for autonomous execution."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.console import Console

from .analyzer import FailureAnalyzer
from .models import (
    CorrectionResult,
    CorrectionStrategy,
    ExecutionAttempt,
    FailureAnalysis,
)
from .reviser import PlanReviser

if TYPE_CHECKING:
    from ..core.client import KiraClient
    from ..thinking.models import ExecutionStep, RefinedPlan


class SelfCorrector:
    """Executes plans with automatic self-correction on failure."""

    def __init__(
        self,
        client: KiraClient,
        max_retries: int = 3,
        use_deep_analysis: bool = True,
        console: Console | None = None,
    ):
        """Initialize self-corrector.

        Args:
            client: KiraClient for execution and analysis.
            max_retries: Maximum number of retry attempts.
            use_deep_analysis: Whether to use LLM for failure analysis.
            console: Rich console for output.
        """
        self.client = client
        self.max_retries = max_retries
        self.use_deep_analysis = use_deep_analysis
        self.console = console or Console()

        self.analyzer = FailureAnalyzer(client if use_deep_analysis else None)
        self.reviser = PlanReviser(client if use_deep_analysis else None)

    async def execute_with_retry(
        self,
        plan: RefinedPlan,
        task: str,
        on_attempt: Callable[[ExecutionAttempt], None] | None = None,
        on_analysis: Callable[[FailureAnalysis], None] | None = None,
    ) -> CorrectionResult:
        """Execute a plan with automatic retry on failure.

        Args:
            plan: The plan to execute.
            task: Original task description.
            on_attempt: Callback after each attempt.
            on_analysis: Callback after failure analysis.

        Returns:
            Result of the execution with all attempts.
        """
        attempts: list[ExecutionAttempt] = []
        analyses: list[FailureAnalysis] = []
        current_plan = plan
        start_time = time.time()

        for attempt_num in range(self.max_retries + 1):
            # Execute current plan
            attempt = await self._execute_plan(current_plan, task, attempt_num, attempts)
            attempts.append(attempt)

            if on_attempt:
                on_attempt(attempt)

            if attempt.success:
                # Success - return result
                return CorrectionResult(
                    success=True,
                    final_output=attempt.result,
                    attempts=attempts,
                    analyses=analyses,
                    total_duration_seconds=time.time() - start_time,
                )

            # Failure - analyze and potentially retry
            if attempt_num >= self.max_retries:
                self._log_warning(f"Max retries ({self.max_retries}) exceeded")
                break

            # Analyze failure
            self._log_info(f"Analyzing failure (attempt {attempt_num + 1})...")

            if self.use_deep_analysis:
                analysis = await self.analyzer.analyze_deep(attempt, task, attempts[:-1])
            else:
                analysis = self.analyzer.analyze_quick(attempt)

            analyses.append(analysis)

            if on_analysis:
                on_analysis(analysis)

            # Check if we should give up
            if analysis.recommended_strategy == CorrectionStrategy.SEEK_HELP:
                self._log_warning("Strategy suggests seeking human help")
                break

            # Revise plan for next attempt
            self._log_info(f"Revising plan using {analysis.recommended_strategy.value} strategy...")
            current_plan = self._revise_plan_for_retry(current_plan, analysis, attempt_num)

        # All retries exhausted
        return CorrectionResult(
            success=False,
            final_output=attempts[-1].result if attempts else "",
            attempts=attempts,
            analyses=analyses,
            total_duration_seconds=time.time() - start_time,
        )

    async def execute_step_with_retry(
        self,
        step: ExecutionStep,
        task: str,
        context: str = "",
    ) -> tuple[bool, str, list[ExecutionAttempt]]:
        """Execute a single step with retry.

        Args:
            step: The step to execute.
            task: Original task description.
            context: Additional context from previous steps.

        Returns:
            Tuple of (success, output, attempts).
        """
        attempts: list[ExecutionAttempt] = []
        current_step = step

        for attempt_num in range(self.max_retries + 1):
            # Build execution prompt
            prompt = self._build_step_prompt(current_step, task, context, attempts)

            # Execute
            start = time.time()
            output_parts: list[str] = []
            error: str | None = None

            try:
                async for chunk in self.client.run(prompt):
                    output_parts.append(chunk)
            except Exception as e:
                error = str(e)

            output = "".join(output_parts)
            duration = time.time() - start

            # Check for success
            success = self._check_step_success(output, error)

            attempt = ExecutionAttempt(
                attempt_number=attempt_num,
                action_taken=current_step.action,
                result=output,
                success=success,
                error=error,
                error_type=self.analyzer.detect_failure_type(error or "", output)
                if not success
                else None,
                duration_seconds=duration,
            )
            attempts.append(attempt)

            if success:
                return True, output, attempts

            if attempt_num >= self.max_retries:
                break

            # Analyze and revise
            analysis = self.analyzer.analyze_quick(attempt)
            revision = self.reviser.revise_quick(current_step, analysis)

            # Update step for next attempt
            from ..thinking.models import ExecutionStep

            current_step = ExecutionStep(
                number=step.number,
                action=revision.revised_step,
                details=step.details,
                expected_outcome=step.expected_outcome,
                verification=step.verification,
            )

        return False, attempts[-1].result if attempts else "", attempts

    async def _execute_plan(
        self,
        plan: RefinedPlan,
        task: str,
        attempt_num: int,
        previous_attempts: list[ExecutionAttempt],
    ) -> ExecutionAttempt:
        """Execute a plan and return the attempt result."""
        # Build execution prompt with plan context
        prompt = self._build_execution_prompt(plan, task, attempt_num, previous_attempts)

        start = time.time()
        output_parts: list[str] = []
        error: str | None = None

        try:
            async for chunk in self.client.run(prompt):
                output_parts.append(chunk)
                # Stream to console
                self.console.print(chunk, end="")
        except Exception as e:
            error = str(e)

        self.console.print()  # Newline after streaming

        output = "".join(output_parts)
        duration = time.time() - start

        # Determine success
        success = self._check_success(output, error, plan)

        return ExecutionAttempt(
            attempt_number=attempt_num,
            action_taken=f"Execute plan: {plan.final_summary[:50]}...",
            result=output,
            success=success,
            error=error,
            error_type=self.analyzer.detect_failure_type(error or "", output)
            if not success
            else None,
            duration_seconds=duration,
        )

    def _build_execution_prompt(
        self,
        plan: RefinedPlan,
        task: str,
        attempt_num: int,
        previous_attempts: list[ExecutionAttempt],
    ) -> str:
        """Build the execution prompt with plan context."""
        prompt_parts = [
            f"TASK: {task}",
            "",
            "EXECUTION PLAN:",
            plan.to_context(),
        ]

        if previous_attempts:
            prompt_parts.extend(
                [
                    "",
                    "PREVIOUS ATTEMPTS (learn from these failures):",
                ]
            )
            for attempt in previous_attempts[-2:]:  # Last 2 attempts
                prompt_parts.append(attempt.to_context())

        if attempt_num > 0:
            prompt_parts.extend(
                [
                    "",
                    f"This is attempt #{attempt_num + 1}. Address the issues from previous attempts.",
                    "Be especially careful about:",
                ]
            )
            # Add specific guidance based on previous errors
            for attempt in previous_attempts[-1:]:
                if attempt.error_type:
                    prompt_parts.append(f"- Avoiding {attempt.error_type.value}")

        prompt_parts.extend(
            [
                "",
                "Execute the plan step by step. For each step:",
                "1. Clearly state what you're doing",
                "2. Show the code or command",
                "3. Verify it works before moving on",
                "",
                "Begin execution:",
            ]
        )

        return "\n".join(prompt_parts)

    def _build_step_prompt(
        self,
        step: ExecutionStep,
        task: str,
        context: str,
        previous_attempts: list[ExecutionAttempt],
    ) -> str:
        """Build prompt for executing a single step."""
        prompt_parts = [
            f"TASK: {task}",
            "",
            f"CURRENT STEP: {step.action}",
        ]

        if step.details:
            prompt_parts.append(f"Details: {step.details}")

        if step.expected_outcome:
            prompt_parts.append(f"Expected outcome: {step.expected_outcome}")

        if context:
            prompt_parts.extend(["", "CONTEXT FROM PREVIOUS STEPS:", context])

        if previous_attempts:
            prompt_parts.extend(
                [
                    "",
                    "PREVIOUS ATTEMPTS AT THIS STEP:",
                ]
            )
            for attempt in previous_attempts:
                prompt_parts.append(attempt.to_context())
            prompt_parts.append("")
            prompt_parts.append("Learn from these failures and try a different approach.")

        prompt_parts.extend(
            [
                "",
                "Execute this step and show your work:",
            ]
        )

        return "\n".join(prompt_parts)

    def _check_success(self, output: str, error: str | None, plan: RefinedPlan) -> bool:
        """Check if execution was successful."""
        if error:
            return False

        # Check for common error indicators
        error_indicators = [
            "error:",
            "exception:",
            "traceback",
            "failed",
            "syntax error",
            "import error",
            "not found",
        ]

        output_lower = output.lower()
        for indicator in error_indicators:
            if indicator in output_lower:
                # Check if it's discussing errors vs having errors
                if "fixed" in output_lower or "resolved" in output_lower:
                    continue
                return False

        # Check for success indicators
        success_indicators = [
            "successfully",
            "completed",
            "done",
            "✓",
            "passed",
        ]

        for indicator in success_indicators:
            if indicator in output_lower:
                return True

        # Default to success if no clear failure
        return True

    def _check_step_success(self, output: str, error: str | None) -> bool:
        """Check if a single step execution was successful."""
        if error:
            return False

        output_lower = output.lower()

        # Strong failure indicators
        failures = ["error:", "exception:", "traceback (most recent"]
        for f in failures:
            if f in output_lower:
                return False

        return True

    def _revise_plan_for_retry(
        self,
        plan: RefinedPlan,
        analysis: FailureAnalysis,
        attempt_num: int,
    ) -> RefinedPlan:
        """Revise plan based on failure analysis."""
        # Use reviser to update the plan
        # For now, we'll update the summary to include failure context
        from ..thinking.models import RefinedPlan as RP

        additional_context = (
            f"\n\nPREVIOUS FAILURE (attempt {attempt_num + 1}):\n{analysis.to_context()}"
        )

        return RP(
            original_plan=plan.original_plan,
            refinements_made=plan.refinements_made
            + [f"Addressing {analysis.failure_type.value}: {analysis.root_cause}"],
            final_steps=plan.final_steps,
            final_summary=plan.final_summary + additional_context,
            confidence_score=max(0.3, plan.confidence_score - 0.15),
            raw_output=plan.raw_output,
        )

    def _log_info(self, message: str) -> None:
        """Log info message."""
        self.console.print(f"[dim]{message}[/dim]")

    def _log_warning(self, message: str) -> None:
        """Log warning message."""
        self.console.print(f"[yellow]{message}[/yellow]")


async def execute_with_correction(
    client: KiraClient,
    plan: RefinedPlan,
    task: str,
    max_retries: int = 3,
    console: Console | None = None,
) -> CorrectionResult:
    """Convenience function for executing with self-correction.

    Args:
        client: KiraClient for execution.
        plan: Plan to execute.
        task: Original task.
        max_retries: Maximum retry attempts.
        console: Rich console for output.

    Returns:
        Execution result with all attempts.
    """
    corrector = SelfCorrector(
        client=client,
        max_retries=max_retries,
        console=console,
    )
    return await corrector.execute_with_retry(plan, task)
