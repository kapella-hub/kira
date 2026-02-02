"""WorkflowOrchestrator - Orchestrates multi-stage workflow execution."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, AsyncIterator

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Stage, StageResult, StageStatus, Workflow, WorkflowExecution

if TYPE_CHECKING:
    from ..agents.spawner import AgentSpawner
    from ..core.session import SessionManager


class WorkflowOrchestrator:
    """Orchestrates multi-stage workflow execution.

    Runs through workflow stages sequentially, injecting
    outputs from previous stages into subsequent ones.
    """

    def __init__(
        self,
        agent_spawner: "AgentSpawner",
        session_manager: "SessionManager",
        console: Console | None = None,
    ):
        self.spawner = agent_spawner
        self.session = session_manager
        self.console = console or Console()

    async def run(
        self,
        workflow: Workflow,
        prompt: str,
        skip_stages: list[str] | None = None,
        interactive: bool = True,
    ) -> AsyncIterator[tuple[str, str]]:
        """Run a workflow, yielding (stage_name, output_chunk) tuples.

        Args:
            workflow: The workflow to execute
            prompt: The original user prompt
            skip_stages: Stages to skip
            interactive: Whether to prompt for optional stage confirmation

        Yields:
            (stage_name, output_chunk) tuples
        """
        skip_stages = skip_stages or []
        execution = WorkflowExecution(
            workflow_name=workflow.name,
            original_prompt=prompt,
            started_at=datetime.utcnow(),
        )

        # Stage outputs for template substitution
        outputs: dict[str, str] = {"original_prompt": prompt}

        # Show workflow header
        self.console.print(
            Panel(
                f"[bold]{workflow.description}[/bold]\n\nStages: {', '.join(s.name for s in workflow.stages)}",
                title=f"Workflow: {workflow.name}",
                border_style="cyan",
            )
        )

        for stage in workflow.stages:
            # Check if should skip
            if stage.name in skip_stages:
                if stage.required:
                    raise ValueError(f"Cannot skip required stage: {stage.name}")

                execution.stages[stage.name] = StageResult(
                    stage_name=stage.name,
                    status=StageStatus.SKIPPED,
                    output="",
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                )
                self.console.print(f"[dim]Skipped: {stage.name}[/dim]")
                continue

            # Check dependencies
            for dep in stage.depends_on:
                dep_result = execution.stages.get(dep)
                if not dep_result or dep_result.status not in (
                    StageStatus.COMPLETED,
                    StageStatus.SKIPPED,
                ):
                    raise ValueError(
                        f"Stage {stage.name} requires {dep} to complete first"
                    )

            # Interactive confirmation for optional stages
            if interactive and not stage.required:
                self.console.print(f"\n[cyan]Optional stage: {stage.name}[/cyan]")
                self.console.print(f"  {stage.description}")
                if not typer.confirm("Run this stage?", default=True):
                    execution.stages[stage.name] = StageResult(
                        stage_name=stage.name,
                        status=StageStatus.SKIPPED,
                        output="",
                        started_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                    )
                    continue

            # Run stage
            execution.current_stage = stage.name
            started = datetime.utcnow()

            self.console.print(f"\n[bold cyan]Stage: {stage.name}[/bold cyan]")
            self.console.print(f"[dim]{stage.description}[/dim]")
            self.console.print(f"[dim]Agent: {stage.agent}[/dim]\n")

            # Build prompt from template
            try:
                stage_prompt = stage.prompt_template.format(**outputs)
            except KeyError as e:
                raise ValueError(
                    f"Stage {stage.name} requires output from: {e}"
                ) from e

            # Run agent
            collected: list[str] = []
            try:
                async for chunk in self.spawner.spawn(
                    stage.agent,
                    stage_prompt,
                    execution.get_context(),
                ):
                    collected.append(chunk)
                    yield (stage.name, chunk)

                output = "".join(collected)
                outputs[stage.output_key] = output

                # Store stage result
                execution.stages[stage.name] = StageResult(
                    stage_name=stage.name,
                    status=StageStatus.COMPLETED,
                    output=output,
                    started_at=started,
                    completed_at=datetime.utcnow(),
                    memories_saved=self.session.save_memories(output),
                )

                # Store as memory
                self.session.add_memory(
                    key=f"workflow:{workflow.name}:{stage.name}",
                    content=output[:2000],  # Truncate for memory
                    tags=["workflow", workflow.name, stage.name],
                    importance=7,
                )

            except Exception as e:
                execution.stages[stage.name] = StageResult(
                    stage_name=stage.name,
                    status=StageStatus.FAILED,
                    output=str(e),
                    started_at=started,
                    completed_at=datetime.utcnow(),
                )
                execution.status = "failed"
                raise

        execution.status = "completed"

        # Yield summary
        yield ("summary", self._format_summary(execution))

    def _format_summary(self, execution: WorkflowExecution) -> str:
        """Format workflow execution summary."""
        lines = [
            "",
            f"[bold green]Workflow Complete: {execution.workflow_name}[/bold green]",
            "",
        ]

        # Create summary table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Time")

        for stage_name, result in execution.stages.items():
            status_text = {
                StageStatus.COMPLETED: "[green]OK[/green]",
                StageStatus.SKIPPED: "[yellow]SKIP[/yellow]",
                StageStatus.FAILED: "[red]FAIL[/red]",
            }.get(result.status, str(result.status))

            table.add_row(
                stage_name,
                status_text,
                f"{result.duration_seconds:.1f}s",
            )

        # Render table to string
        from io import StringIO
        from rich.console import Console as RichConsole

        buffer = StringIO()
        temp_console = RichConsole(file=buffer, force_terminal=True)
        temp_console.print(table)

        lines.append(buffer.getvalue())
        lines.append(f"Total time: {execution.duration_seconds:.1f}s")

        return "\n".join(lines)
