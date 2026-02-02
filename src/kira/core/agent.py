"""Unified autonomous agent with deep reasoning and self-correction."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

from .config import Config
from .client import KiraClient
from .verifier import Verifier

if TYPE_CHECKING:
    from ..correction.loop import SelfCorrector
    from ..correction.models import CorrectionResult
    from ..memory.execution import ExecutionMemory, ExecutionRecord
    from ..thinking.models import RefinedPlan, ThinkingResult
    from ..thinking.reasoning import DeepReasoning


@dataclass
class AgentResult:
    """Result of an autonomous agent execution."""

    task: str
    success: bool
    output: str
    thinking_result: ThinkingResult | None = None
    correction_result: CorrectionResult | None = None
    files_modified: list[str] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    attempts: int = 1
    learnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Get a summary of the execution."""
        status = "SUCCESS" if self.success else "FAILED"
        lines = [
            f"Status: {status}",
            f"Attempts: {self.attempts}",
            f"Duration: {self.total_duration_seconds:.1f}s",
        ]
        if self.files_modified:
            lines.append(f"Files modified: {len(self.files_modified)}")
        if self.learnings:
            lines.append("Learnings:")
            for learning in self.learnings[:3]:
                lines.append(f"  - {learning}")
        return "\n".join(lines)


class KiraAgent:
    """Unified autonomous agent with deep reasoning and self-correction.

    This agent combines:
    - Deep 6-phase reasoning for complex task analysis
    - Execution memory for learning from past attempts
    - Self-correction loop for automatic error recovery
    - Verification layer for validating results

    Usage:
        agent = KiraAgent()
        result = await agent.run("implement user authentication")
    """

    def __init__(
        self,
        config: Config | None = None,
        client: KiraClient | None = None,
        console: Console | None = None,
        working_dir: Path | None = None,
    ):
        """Initialize the autonomous agent.

        Args:
            config: Configuration (loads default if not provided).
            client: KiraClient instance (creates one if not provided).
            console: Rich console for output.
            working_dir: Working directory for operations.
        """
        self.config = config or Config.load()
        self.console = console or Console()
        self.working_dir = working_dir or Path.cwd()

        # Initialize client
        if client:
            self.client = client
        else:
            self.client = KiraClient(
                model=self.config.kira.model,
                trust_all_tools=self.config.kira.trust_all_tools,
                working_dir=self.working_dir,
                timeout=self.config.kira.timeout,
            )

        # Initialize components (lazy loaded)
        self._reasoning: DeepReasoning | None = None
        self._corrector: SelfCorrector | None = None
        self._verifier: Verifier | None = None
        self._memory: ExecutionMemory | None = None

    @property
    def reasoning(self) -> DeepReasoning:
        """Get or create the deep reasoning component."""
        if self._reasoning is None:
            from ..thinking.reasoning import DeepReasoning
            self._reasoning = DeepReasoning(
                client=self.client,
                console=self.console,
            )
        return self._reasoning

    @property
    def corrector(self) -> SelfCorrector:
        """Get or create the self-correction component."""
        if self._corrector is None:
            from ..correction.loop import SelfCorrector
            self._corrector = SelfCorrector(
                client=self.client,
                max_retries=self.config.autonomous.max_retries,
                use_deep_analysis=self.config.autonomous.deep_analysis,
                console=self.console,
            )
        return self._corrector

    @property
    def verifier(self) -> Verifier:
        """Get or create the verification component."""
        if self._verifier is None:
            self._verifier = Verifier(
                client=self.client,
                working_dir=self.working_dir,
            )
        return self._verifier

    @property
    def memory(self) -> ExecutionMemory:
        """Get or create the execution memory component."""
        if self._memory is None:
            from ..memory.execution import ExecutionMemory
            self._memory = ExecutionMemory()
        return self._memory

    async def run(
        self,
        task: str,
        deep_reasoning: bool | None = None,
        max_retries: int | None = None,
        verify: bool | None = None,
        learn: bool | None = None,
    ) -> AgentResult:
        """Run the agent on a task.

        Args:
            task: Task description.
            deep_reasoning: Override config for deep reasoning.
            max_retries: Override config for max retries.
            verify: Override config for verification.
            learn: Override config for learning.

        Returns:
            Result of the execution.
        """
        start_time = time.time()

        # Apply overrides
        use_reasoning = deep_reasoning if deep_reasoning is not None else self.config.autonomous.deep_reasoning
        retries = max_retries if max_retries is not None else self.config.autonomous.max_retries
        use_verify = verify if verify is not None else self.config.autonomous.verification_enabled
        use_learn = learn if learn is not None else self.config.autonomous.learning_enabled

        self._log_header(f"Task: {task[:100]}...")

        # Step 1: Check execution memory for similar tasks
        history: list[ExecutionRecord] = []
        if use_learn:
            history = self.memory.get_relevant_history(task, limit=3)
            if history:
                self._log_info(f"Found {len(history)} relevant past executions")
                self._show_history_summary(history)

        # Step 2: Deep reasoning (if enabled)
        thinking_result: ThinkingResult | None = None
        plan: RefinedPlan | None = None

        if use_reasoning:
            self._log_phase("Phase 1: Deep Reasoning")
            context = self._format_history_as_context(history) if history else ""
            thinking_result = await self.reasoning.think(task, context=context)
            plan = thinking_result.refined_plan

            if plan:
                self._log_success(f"Plan created with {len(plan.final_steps)} steps")
                if self.config.autonomous.verbose:
                    self.console.print(Panel(plan.to_context(), title="Execution Plan"))
        else:
            self._log_info("Skipping deep reasoning (disabled)")

        # Step 3: Execute with self-correction
        self._log_phase("Phase 2: Execution")
        correction_result: CorrectionResult | None = None
        output = ""
        files_modified: list[str] = []

        if plan:
            # Execute with plan
            from ..correction.loop import SelfCorrector
            corrector = SelfCorrector(
                client=self.client,
                max_retries=retries,
                use_deep_analysis=self.config.autonomous.deep_analysis,
                console=self.console,
            )
            correction_result = await corrector.execute_with_retry(plan, task)
            output = correction_result.final_output
        else:
            # Direct execution without plan
            output = await self._execute_direct(task, history)

        # Step 4: Verification (if enabled)
        verification_passed = True
        if use_verify and correction_result:
            self._log_phase("Phase 3: Verification")
            verification = await self.verifier.verify(
                task=task,
                output=output,
                files_modified=files_modified,
                run_tests=self.config.autonomous.run_tests,
                check_types=self.config.autonomous.check_types,
            )
            verification_passed = verification.overall_passed

            if verification_passed:
                self._log_success("Verification passed")
            else:
                self._log_warning(f"Verification issues: {', '.join(verification.issues)}")

                # Try one more time with verification feedback
                if correction_result and not correction_result.success:
                    self._log_info("Retrying with verification feedback...")
                    # Could add another correction loop here

        # Step 5: Record outcome for learning
        success = (correction_result.success if correction_result else True) and verification_passed
        learnings: list[str] = []

        if use_learn:
            learnings = self._extract_learnings(thinking_result, correction_result)
            if success:
                self.memory.record_success(
                    task=task,
                    approach=plan.final_summary if plan else "direct execution",
                    learnings=learnings,
                    duration_seconds=time.time() - start_time,
                    attempts=correction_result.attempt_count if correction_result else 1,
                )
            else:
                error_type = "unknown"
                error_message = "Execution failed"
                if correction_result and correction_result.analyses:
                    last_analysis = correction_result.analyses[-1]
                    error_type = last_analysis.failure_type.value
                    error_message = last_analysis.root_cause
                self.memory.record_failure(
                    task=task,
                    approach=plan.final_summary if plan else "direct execution",
                    error_type=error_type,
                    error_message=error_message,
                    learnings=learnings,
                    duration_seconds=time.time() - start_time,
                    attempts=correction_result.attempt_count if correction_result else 1,
                )

        # Build result
        return AgentResult(
            task=task,
            success=success,
            output=output,
            thinking_result=thinking_result,
            correction_result=correction_result,
            files_modified=files_modified,
            total_duration_seconds=time.time() - start_time,
            attempts=correction_result.attempt_count if correction_result else 1,
            learnings=learnings,
        )

    async def run_streaming(
        self,
        task: str,
        deep_reasoning: bool = True,
    ) -> AsyncIterator[str]:
        """Run the agent with streaming output.

        Args:
            task: Task description.
            deep_reasoning: Whether to use deep reasoning.

        Yields:
            Output chunks as they are generated.
        """
        # Check history
        history = self.memory.get_relevant_history(task, limit=3)

        # Run reasoning if enabled
        if deep_reasoning:
            context = self._format_history_as_context(history) if history else ""
            thinking_result = await self.reasoning.think(task, context=context)
            plan = thinking_result.refined_plan

            if plan:
                yield f"\n**Plan:** {plan.final_summary}\n\n"
                yield "**Executing...**\n\n"

                # Build execution prompt
                prompt = self._build_execution_prompt(task, plan, history)
            else:
                prompt = task
        else:
            prompt = task

        # Stream execution
        async for chunk in self.client.run(prompt):
            yield chunk

    async def _execute_direct(
        self,
        task: str,
        history: list[ExecutionRecord] | None = None,
    ) -> str:
        """Execute task directly without a plan.

        Args:
            task: Task description.
            history: Relevant execution history.

        Returns:
            Execution output.
        """
        prompt = task
        if history:
            prompt = self._inject_history_context(task, history)

        output_parts: list[str] = []
        async for chunk in self.client.run(prompt):
            self.console.print(chunk, end="")
            output_parts.append(chunk)

        self.console.print()
        return "".join(output_parts)

    def _build_execution_prompt(
        self,
        task: str,
        plan: RefinedPlan,
        history: list[ExecutionRecord] | None = None,
    ) -> str:
        """Build the execution prompt with plan and history context."""
        parts = [
            f"TASK: {task}",
            "",
            "EXECUTION PLAN:",
            plan.to_context(),
        ]

        if history:
            parts.extend([
                "",
                "RELEVANT PAST EXPERIENCE:",
            ])
            for record in history[:2]:
                parts.append(record.to_context())

        parts.extend([
            "",
            "Execute the plan step by step. Show your work clearly.",
        ])

        return "\n".join(parts)

    def _inject_history_context(
        self,
        task: str,
        history: list[ExecutionRecord],
    ) -> str:
        """Inject history context into task prompt."""
        parts = [task, "", "RELEVANT PAST EXPERIENCE:"]
        for record in history[:2]:
            parts.append(record.to_context())
        parts.append("")
        parts.append("Apply these learnings to the current task.")
        return "\n".join(parts)

    def _format_history_as_context(self, history: list[ExecutionRecord]) -> str:
        """Format execution history as context string for reasoning."""
        if not history:
            return ""
        parts = ["RELEVANT PAST EXPERIENCE:"]
        for record in history[:3]:
            parts.append(record.to_context())
        return "\n".join(parts)

    def _extract_learnings(
        self,
        thinking: ThinkingResult | None,
        correction: CorrectionResult | None,
    ) -> list[str]:
        """Extract learnings from execution."""
        learnings: list[str] = []

        if thinking and thinking.critique:
            for weakness in thinking.critique.weaknesses[:2]:
                learnings.append(f"Watch for: {weakness}")

        if correction:
            if correction.was_corrected:
                learnings.append(f"Required {correction.attempt_count} attempts to succeed")
            for analysis in correction.analyses:
                learnings.append(f"Encountered: {analysis.failure_type.value}")
                if analysis.suggested_fixes:
                    learnings.append(f"Fixed by: {analysis.suggested_fixes[0]}")

        return learnings

    def _show_history_summary(self, history: list[ExecutionRecord]) -> None:
        """Show summary of relevant history."""
        for record in history[:2]:
            status = "[green]OK[/green]" if record.success else "[red]FAIL[/red]"
            self.console.print(f"  {status} {record.task_summary[:60]}...")

    def _log_header(self, message: str) -> None:
        """Log a header message."""
        self.console.print()
        self.console.print(Panel(message, style="bold cyan"))

    def _log_phase(self, message: str) -> None:
        """Log a phase message."""
        self.console.print()
        self.console.print(f"[bold blue]{message}[/bold blue]")

    def _log_info(self, message: str) -> None:
        """Log an info message."""
        self.console.print(f"[dim]{message}[/dim]")

    def _log_success(self, message: str) -> None:
        """Log a success message."""
        self.console.print(f"[green]{message}[/green]")

    def _log_warning(self, message: str) -> None:
        """Log a warning message."""
        self.console.print(f"[yellow]{message}[/yellow]")


async def run_autonomous(
    task: str,
    config: Config | None = None,
    working_dir: Path | None = None,
    deep_reasoning: bool = True,
    max_retries: int = 3,
    verify: bool = True,
    learn: bool = True,
) -> AgentResult:
    """Convenience function for running autonomous agent.

    Args:
        task: Task description.
        config: Configuration.
        working_dir: Working directory.
        deep_reasoning: Use deep 6-phase reasoning.
        max_retries: Maximum correction attempts.
        verify: Run verification checks.
        learn: Learn from execution.

    Returns:
        Agent execution result.
    """
    agent = KiraAgent(config=config, working_dir=working_dir)
    return await agent.run(
        task=task,
        deep_reasoning=deep_reasoning,
        max_retries=max_retries,
        verify=verify,
        learn=learn,
    )
