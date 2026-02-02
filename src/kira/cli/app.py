"""Main CLI application using Typer (Claude Code-like interface)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer

from .commands import config, logs, memory, skills
from .output import console, print_error, print_info, print_success

app = typer.Typer(
    name="kira",
    help="Agentic CLI powered by kiro-cli with persistent memory and skills",
    no_args_is_help=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)

# Register command groups
app.add_typer(memory.app, name="memory")
app.add_typer(skills.app, name="skills")
app.add_typer(config.app, name="config")
app.add_typer(logs.app, name="logs")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    # Flags for default interactive mode
    continue_session: Annotated[
        bool,
        typer.Option("--continue", "-c", help="Continue the previous conversation"),
    ] = False,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Model to use (fast/smart/opus or model name)"),
    ] = None,
    skill: Annotated[
        Optional[list[str]],
        typer.Option("--skill", "-s", help="Activate skill(s)"),
    ] = None,
    trust: Annotated[
        bool,
        typer.Option("--trust", "-t", help="Trust all tools (no confirmations)"),
    ] = False,
    agent: Annotated[
        Optional[str],
        typer.Option("--agent", "-a", help="Kira agent to use"),
    ] = None,
    no_memory: Annotated[
        bool,
        typer.Option("--no-memory", help="Disable memory injection"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Verbose output"),
    ] = False,
):
    """Agentic CLI powered by kiro-cli.

    Start interactive mode:
        kira

    One-shot prompt:
        kira chat "explain this codebase"

    Print-only mode:
        kira chat -p "summarize this file"

    Continue previous conversation:
        kira -c

    Examples:
        kira                              # Interactive REPL
        kira chat "What does this do?"   # One-shot
        kira chat -m opus "Complex task" # With model
        kira -c                           # Resume in REPL
        kira memory list                  # Memory commands
        kira skills list                  # Skills commands
    """
    # If a subcommand was invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    # Default: start interactive REPL
    from .repl import start_repl

    start_repl(
        model=model,
        trust=trust,
        skills=skill,
        resume=continue_session,
        agent=agent,
        no_memory=no_memory,
        verbose=verbose,
    )


@app.command("chat")
def chat(
    prompt: Annotated[str, typer.Argument(help="Your prompt")],
    # Flags
    print_only: Annotated[
        bool,
        typer.Option("--print", "-p", help="Print response and exit (no follow-up)"),
    ] = False,
    continue_session: Annotated[
        bool,
        typer.Option("--continue", "-c", help="Continue the previous conversation"),
    ] = False,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Model to use (fast/smart/opus or model name)"),
    ] = None,
    skill: Annotated[
        Optional[list[str]],
        typer.Option("--skill", "-s", help="Activate skill(s)"),
    ] = None,
    trust: Annotated[
        bool,
        typer.Option("--trust", "-t", help="Trust all tools (no confirmations)"),
    ] = False,
    think: Annotated[
        bool,
        typer.Option("--think", "-T", help="Enable deep reasoning (6-phase thinking)"),
    ] = False,
    autonomous: Annotated[
        bool,
        typer.Option("--autonomous", "-A", help="Full autonomous mode (reasoning + self-correction + verification)"),
    ] = False,
    max_retries: Annotated[
        int,
        typer.Option("--max-retries", help="Max self-correction attempts (autonomous mode)"),
    ] = 3,
    no_verify: Annotated[
        bool,
        typer.Option("--no-verify", help="Skip verification (autonomous mode)"),
    ] = False,
    no_learn: Annotated[
        bool,
        typer.Option("--no-learn", help="Disable learning from execution (autonomous mode)"),
    ] = False,
    workflow: Annotated[
        Optional[str],
        typer.Option("--workflow", "-W", help="Run a workflow (e.g., 'coding')"),
    ] = None,
    auto_workflow: Annotated[
        bool,
        typer.Option("--auto-workflow", help="Auto-detect and run appropriate workflow"),
    ] = False,
    skip_stage: Annotated[
        Optional[list[str]],
        typer.Option("--skip", help="Skip workflow stages"),
    ] = None,
    agent: Annotated[
        Optional[str],
        typer.Option("--agent", "-a", help="Kira agent to use"),
    ] = None,
    no_memory: Annotated[
        bool,
        typer.Option("--no-memory", help="Disable memory injection"),
    ] = False,
    no_personality: Annotated[
        bool,
        typer.Option("--no-personality", help="Disable personality (plain responses)"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Verbose output"),
    ] = False,
):
    """Send a prompt to the agent.

    Kira is a witty, professional, and proactive coding assistant.
    Ready with ideas and suggestions to help you build great software.

    Examples:
        kira chat "Explain this codebase"
        kira chat -m opus "Complex analysis task"
        kira chat -s architect "Design a REST API"
        kira chat -T "Plan and implement this feature"
        kira chat -A "Implement user auth"       # Full autonomous
        kira chat -A --max-retries 5 "Fix bug"  # More retries
        kira chat -W coding "Build user authentication"
        kira chat -p "Just output, no interaction"
    """
    # Autonomous mode: reasoning + self-correction + verification
    if autonomous:
        asyncio.run(
            _run_autonomous(
                prompt=prompt,
                model=model,
                max_retries=max_retries,
                verify=not no_verify,
                learn=not no_learn,
                trust=trust,
                verbose=verbose,
            )
        )
    # Workflow mode
    elif workflow:
        asyncio.run(
            _run_workflow(
                prompt=prompt,
                workflow_name=workflow,
                skip_stages=skip_stage,
                model=model,
                no_memory=no_memory,
                trust=trust,
                interactive=not print_only,
            )
        )
    elif auto_workflow:
        asyncio.run(
            _run_auto_workflow(
                prompt=prompt,
                skip_stages=skip_stage,
                model=model,
                no_memory=no_memory,
                trust=trust,
                interactive=not print_only,
            )
        )
    elif think:
        asyncio.run(
            _run_thinking(
                prompt=prompt,
                skills=skill,
                model=model,
                agent=agent,
                no_memory=no_memory,
                trust=trust,
                verbose=verbose,
            )
        )
    else:
        asyncio.run(
            _run_one_shot(
                prompt=prompt,
                skills=skill,
                model=model,
                resume=continue_session,
                agent=agent,
                no_memory=no_memory,
                no_personality=no_personality,
                trust=trust,
                verbose=verbose,
            )
        )


async def _run_one_shot(
    prompt: str,
    skills: list[str] | None,
    model: str | None,
    resume: bool,
    agent: str | None,
    no_memory: bool,
    no_personality: bool,
    trust: bool,
    verbose: bool,
) -> None:
    """Execute a one-shot prompt."""
    import time

    from ..core.config import Config
    from ..core.client import KiraClient, KiraNotFoundError
    from ..core.models import resolve_model
    from ..core.session import SessionManager
    from ..logs import RunLogStore
    from ..logs.models import RunMode
    from ..memory.store import MemoryStore
    from ..skills.manager import SkillManager

    # Load configuration
    config = Config.load()

    # Initialize components
    memory_store = MemoryStore()
    skill_manager = SkillManager()
    session_manager = SessionManager(memory_store, skill_manager)
    log_store = RunLogStore()

    # Resolve model alias
    resolved_model = resolve_model(model) or config.kira.model

    # Start session with personality
    inject_personality = not no_personality and config.personality.enabled
    session = session_manager.start(
        working_dir=Path.cwd(),
        skills=skills,
        memory_tags=None,
        memory_enabled=not no_memory and config.memory.enabled,
        max_context_tokens=config.memory.max_context_tokens,
        min_importance=config.memory.min_importance,
        inject_personality=inject_personality,
    )

    # Start run log
    run_id = log_store.start_run(
        session_id=session.id,
        mode=RunMode.CHAT,
        model=resolved_model,
        working_dir=str(Path.cwd()),
        skills=skills,
    )

    # Show session info (verbose mode)
    if verbose:
        if session.memory_context:
            print_info(f"Loaded {len(session.memory_context.split(chr(10)))} memory entries")
        if skills:
            print_info(f"Active skills: {', '.join(skills)}")
        if model:
            print_info(f"Model: {resolved_model}")
        if inject_personality:
            print_info(f"Personality: {session.personality.name if session.personality else 'None'}")

    # Build full prompt with context (use brief personality for one-shot)
    full_prompt = session_manager.build_prompt(prompt, use_brief_personality=True)

    # Configure kiro-cli
    try:
        client = KiraClient(
            agent=agent or config.default_agent,
            model=resolved_model,
            trust_all_tools=trust or config.kira.trust_all_tools,
            working_dir=session.working_dir,
            timeout=config.kira.timeout,
        )
    except KiraNotFoundError as e:
        print_error(str(e))
        log_store.end_run(run_id)
        raise typer.Exit(1)

    # Stream output
    collected_output: list[str] = []
    start_time = time.time()

    # Log the entry
    entry_id = log_store.add_entry(
        run_id=run_id,
        prompt=prompt,
        model=resolved_model,
    )

    try:
        async for chunk in client.run(full_prompt, agent=agent, resume=resume):
            console.print(chunk, end="")
            collected_output.append(chunk)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
        duration = time.time() - start_time
        log_store.update_entry_response(entry_id, "".join(collected_output), duration)
        log_store.end_run(run_id)
        raise typer.Exit(130)

    console.print()  # Final newline

    # Update log entry with response
    duration = time.time() - start_time
    full_output = "".join(collected_output)
    log_store.update_entry_response(entry_id, full_output, duration)
    log_store.end_run(run_id)

    # Extract and save memories
    if not no_memory and config.memory.auto_extract:
        saved = session_manager.save_memories(full_output)
        if saved > 0 and verbose:
            print_success(f"Saved {saved} memory entries")


async def _run_thinking(
    prompt: str,
    skills: list[str] | None,
    model: str | None,
    agent: str | None,
    no_memory: bool,
    trust: bool,
    verbose: bool,
) -> None:
    """Execute with deep reasoning mode (6-phase thinking)."""
    from rich.panel import Panel

    from ..core.config import Config
    from ..core.client import KiraClient, KiraNotFoundError
    from ..core.models import resolve_model
    from ..core.session import SessionManager
    from ..memory.store import MemoryStore
    from ..skills.manager import SkillManager
    from ..thinking import DeepReasoning, ThinkingExecutor

    # Load configuration
    config = Config.load()

    # Initialize components
    memory_store = MemoryStore()
    skill_manager = SkillManager()
    session_manager = SessionManager(memory_store, skill_manager)

    # Resolve model alias
    resolved_model = resolve_model(model) or config.kira.model

    # Start session
    session = session_manager.start(
        working_dir=Path.cwd(),
        skills=skills,
        memory_tags=None,
        memory_enabled=not no_memory and config.memory.enabled,
        max_context_tokens=config.memory.max_context_tokens,
        min_importance=config.memory.min_importance,
    )

    # Show session info
    if verbose:
        if session.memory_context:
            print_info(f"Loaded {len(session.memory_context.split(chr(10)))} memory entries")
        if skills:
            print_info(f"Active skills: {', '.join(skills)}")
        if model:
            print_info(f"Model: {resolved_model}")

    # Configure kiro-cli
    try:
        client = KiraClient(
            agent=agent or config.default_agent,
            model=resolved_model,
            trust_all_tools=trust or config.kira.trust_all_tools,
            working_dir=session.working_dir,
            timeout=config.kira.timeout,
        )
    except KiraNotFoundError as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Run deep reasoning (6 phases)
    console.print("\n[bold magenta]Deep Reasoning Mode[/bold magenta]")
    console.print("[dim]Running 6-phase analysis: Understand → Explore → Analyze → Plan → Critique → Refine[/dim]\n")

    reasoning = DeepReasoning(client, console, verbose=True)

    try:
        result = await reasoning.think(prompt, session.memory_context)
    except KeyboardInterrupt:
        console.print("\n[dim]Reasoning interrupted[/dim]")
        raise typer.Exit(130)

    # Store result as memory
    session_manager.add_memory(
        key="thinking:last_result",
        content=result.to_memory(),
        tags=["thinking", "reasoning"],
        importance=7,
    )

    # Show summary
    console.print(f"\n[bold green]Reasoning Complete[/bold green]")
    console.print(f"[dim]Phases completed: {len(result.phases_completed)}[/dim]")
    console.print(f"[dim]Thinking time: {result.total_thinking_time:.1f}s[/dim]")

    if result.refined_plan:
        console.print(f"[dim]Confidence: {result.refined_plan.confidence_score:.0%}[/dim]")

    # Phase 7: Execute with the refined plan
    console.print("\n[bold cyan]Phase 7: Executing...[/bold cyan]\n")

    # Build execution prompt with full context
    execution_prompt = _build_execution_prompt(prompt, result)

    executor = ThinkingExecutor(client, session_manager)
    collected_output: list[str] = []

    try:
        async for chunk in client.run(execution_prompt):
            console.print(chunk, end="")
            collected_output.append(chunk)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
        raise typer.Exit(130)

    console.print()  # Final newline

    # Extract and save memories
    if not no_memory and config.memory.auto_extract:
        full_output = "".join(collected_output)
        saved = session_manager.save_memories(full_output)
        if saved > 0 and verbose:
            print_success(f"Saved {saved} memory entries")


async def _run_autonomous(
    prompt: str,
    model: str | None,
    max_retries: int,
    verify: bool,
    learn: bool,
    trust: bool,
    verbose: bool,
) -> None:
    """Execute in full autonomous mode with reasoning, self-correction, and verification."""
    from rich.panel import Panel

    from ..core.agent import KiraAgent
    from ..core.config import Config
    from ..core.client import KiraClient, KiraNotFoundError
    from ..core.models import resolve_model

    # Load configuration
    config = Config.load()

    # Resolve model alias
    resolved_model = resolve_model(model) or config.kira.model

    # Configure kiro-cli
    try:
        client = KiraClient(
            agent=config.default_agent,
            model=resolved_model,
            trust_all_tools=trust or config.kira.trust_all_tools,
            working_dir=Path.cwd(),
            timeout=config.kira.timeout,
        )
    except KiraNotFoundError as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Create autonomous agent
    agent = KiraAgent(
        config=config,
        client=client,
        console=console,
        working_dir=Path.cwd(),
    )

    # Show mode info
    console.print("\n[bold magenta]Autonomous Mode[/bold magenta]")
    console.print("[dim]Deep reasoning + self-correction + verification[/dim]\n")

    if verbose:
        console.print(f"[dim]Max retries: {max_retries}[/dim]")
        console.print(f"[dim]Verification: {'enabled' if verify else 'disabled'}[/dim]")
        console.print(f"[dim]Learning: {'enabled' if learn else 'disabled'}[/dim]")
        console.print()

    # Run autonomous agent
    try:
        result = await agent.run(
            task=prompt,
            deep_reasoning=True,
            max_retries=max_retries,
            verify=verify,
            learn=learn,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
        raise typer.Exit(130)

    # Show summary
    console.print()
    console.print(Panel(result.summary(), title="Execution Summary", style="bold"))

    if not result.success:
        raise typer.Exit(1)


def _build_execution_prompt(task: str, result: "ThinkingResult") -> str:
    """Build the execution prompt from thinking result."""
    from ..thinking import ThinkingResult

    parts = []

    # Add understanding context
    if result.understanding:
        parts.append("## Task Understanding")
        parts.append(f"Core Goal: {result.understanding.core_goal}")
        if result.understanding.success_criteria:
            parts.append(f"Success Criteria: {', '.join(result.understanding.success_criteria)}")
        parts.append("")

    # Add the refined plan
    if result.refined_plan:
        parts.append("## Execution Plan")
        parts.append(result.refined_plan.to_context())
        parts.append("")
    elif result.initial_plan:
        parts.append("## Execution Plan")
        parts.append(result.initial_plan.to_context())
        parts.append("")

    # Add analysis insights
    if result.analysis:
        parts.append("## Key Insights")
        parts.append(f"Approach: {result.analysis.chosen_approach}")
        if result.analysis.mitigations:
            parts.append(f"Mitigations: {', '.join(result.analysis.mitigations[:3])}")
        parts.append("")

    # Add instructions
    parts.append("## Instructions")
    parts.append("Execute the plan above step by step.")
    parts.append("Verify each step before proceeding to the next.")
    parts.append("Report any issues or deviations from the plan.")
    parts.append("")

    # Add the original task
    parts.append("## Original Task")
    parts.append(task)

    return "\n".join(parts)


async def _run_workflow(
    prompt: str,
    workflow_name: str,
    skip_stages: list[str] | None,
    model: str | None,
    no_memory: bool,
    trust: bool,
    interactive: bool,
) -> None:
    """Execute a multi-stage workflow."""
    from ..agents.registry import AgentRegistry
    from ..agents.spawner import AgentSpawner
    from ..core.config import Config
    from ..core.client import KiraClient, KiraNotFoundError
    from ..core.models import resolve_model
    from ..core.session import SessionManager
    from ..memory.store import MemoryStore
    from ..skills.manager import SkillManager
    from ..workflows.coding import get_workflow
    from ..workflows.orchestrator import WorkflowOrchestrator

    # Get the workflow
    workflow = get_workflow(workflow_name)
    if not workflow:
        print_error(f"Unknown workflow: {workflow_name}")
        print_info("Available: coding, quick-coding")
        raise typer.Exit(1)

    # Load configuration
    config = Config.load()

    # Initialize components
    memory_store = MemoryStore()
    skill_manager = SkillManager()
    session_manager = SessionManager(memory_store, skill_manager)

    # Resolve model alias
    resolved_model = resolve_model(model) or config.kira.model

    # Start session
    session = session_manager.start(
        working_dir=Path.cwd(),
        skills=None,
        memory_tags=None,
        memory_enabled=not no_memory and config.memory.enabled,
        max_context_tokens=config.memory.max_context_tokens,
        min_importance=config.memory.min_importance,
    )

    # Configure kiro-cli
    try:
        client = KiraClient(
            agent=config.default_agent,
            model=resolved_model,
            trust_all_tools=trust or config.kira.trust_all_tools,
            working_dir=session.working_dir,
            timeout=config.kira.timeout,
        )
    except KiraNotFoundError as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Create agent spawner and orchestrator
    registry = AgentRegistry()
    spawner = AgentSpawner(client, session_manager, registry)
    orchestrator = WorkflowOrchestrator(spawner, session_manager, console)

    # Run workflow
    try:
        async for stage_name, chunk in orchestrator.run(
            workflow=workflow,
            prompt=prompt,
            skip_stages=skip_stages,
            interactive=interactive,
        ):
            if stage_name != "summary":
                console.print(chunk, end="")
            else:
                console.print(chunk)
    except KeyboardInterrupt:
        console.print("\n[dim]Workflow interrupted[/dim]")
        raise typer.Exit(130)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


async def _run_auto_workflow(
    prompt: str,
    skip_stages: list[str] | None,
    model: str | None,
    no_memory: bool,
    trust: bool,
    interactive: bool,
) -> None:
    """Auto-detect task type and run appropriate workflow."""
    from ..workflows.detector import CodingTaskDetector

    detector = CodingTaskDetector()
    is_coding, confidence = detector.is_coding_task(prompt)

    if is_coding:
        workflow_name = detector.get_recommended_workflow(prompt) or "coding"
        print_info(f"Detected coding task (confidence: {confidence:.0%})")
        print_info(f"Running workflow: {workflow_name}")

        await _run_workflow(
            prompt=prompt,
            workflow_name=workflow_name,
            skip_stages=skip_stages,
            model=model,
            no_memory=no_memory,
            trust=trust,
            interactive=interactive,
        )
    else:
        print_info(f"Standard mode (coding confidence: {confidence:.0%})")
        await _run_one_shot(
            prompt=prompt,
            skills=None,
            model=model,
            resume=False,
            agent=None,
            no_memory=no_memory,
            trust=trust,
            verbose=False,
        )


@app.command("version")
def version():
    """Show version information."""
    from .. import __version__
    from ..core.client import KiraClient

    console.print(f"kira version: {__version__}")

    kiro_version = KiraClient.get_version()
    if kiro_version:
        console.print(f"kiro-cli version: {kiro_version}")
    else:
        print_info("kiro-cli: not found")


@app.command("update")
def update():
    """Update kira to the latest version."""
    import subprocess
    import sys

    from .. import __version__

    console.print(f"[dim]Current version: {__version__}[/dim]")
    console.print("Updating kira...")

    # Run pip upgrade
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            "--upgrade",
            "git+https://github.com/kapella-hub/kira.git",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        console.print("[green]✓[/green] Updated successfully")
        console.print("[dim]Restart your shell to use the new version[/dim]")
    else:
        console.print(f"[red]✗[/red] Update failed")
        if result.stderr:
            console.print(f"[dim]{result.stderr.strip()}[/dim]")
        raise typer.Exit(1)


@app.command("status")
def status():
    """Show system status."""
    from ..core.client import KiraClient
    from ..memory.store import MemoryStore
    from ..skills.manager import SkillManager

    console.print("[cyan]System Status[/cyan]\n")

    # Check kiro-cli
    if KiraClient.is_available():
        kiro_version = KiraClient.get_version()
        console.print(f"[green]✓[/green] kiro-cli: {kiro_version or 'available'}")
    else:
        console.print("[red]✗[/red] kiro-cli: not found")

    # Check memory
    try:
        store = MemoryStore()
        count = store.count()
        console.print(f"[green]✓[/green] Memory: {count} entries")
    except Exception as e:
        console.print(f"[red]✗[/red] Memory: {e}")

    # Check skills
    try:
        manager = SkillManager()
        skills_list = manager.list_all()
        console.print(f"[green]✓[/green] Skills: {len(skills_list)} available")
    except Exception as e:
        console.print(f"[red]✗[/red] Skills: {e}")


if __name__ == "__main__":
    app()
