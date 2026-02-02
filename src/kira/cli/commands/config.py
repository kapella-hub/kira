"""Configuration commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...core.config import Config
from ...core import defaults as D
from ..output import console, print_error, print_info, print_success

app = typer.Typer(help="Manage configuration")


@app.command("show")
def show_config(
    section: Annotated[
        str | None,
        typer.Argument(help="Section to show (defaults, kira, memory, thinking, workflow, autonomous, personality)"),
    ] = None,
):
    """Show current configuration."""
    config = Config.load()

    def show_defaults():
        console.print("[bold]Defaults:[/bold]")
        console.print(f"  agent: {config.default_agent}")
        console.print(f"  trust_all_tools: {config.kira.trust_all_tools}")
        if config.default_skills:
            console.print(f"  skills: {', '.join(config.default_skills)}")

    def show_kira():
        console.print("[bold]Kira:[/bold]")
        console.print(f"  model: {config.kira.model or '(default)'}")
        console.print(f"  timeout: {config.kira.timeout}s")

    def show_memory():
        console.print("[bold]Memory:[/bold]")
        console.print(f"  enabled: {config.memory.enabled}")
        console.print(f"  max_context_tokens: {config.memory.max_context_tokens}")
        console.print(f"  min_importance: {config.memory.min_importance}")
        console.print(f"  auto_extract: {config.memory.auto_extract}")

    def show_thinking():
        console.print("[bold]Thinking:[/bold]")
        console.print(f"  enabled: {config.thinking.enabled}")
        console.print(f"  planning_model: {config.thinking.planning_model or '(same as main)'}")
        console.print(f"  show_plan: {config.thinking.show_plan}")
        console.print(f"  save_plans: {config.thinking.save_plans}")

    def show_workflow():
        console.print("[bold]Workflow:[/bold]")
        console.print(f"  auto_detect: {config.workflow.auto_detect}")
        console.print(f"  detection_threshold: {config.workflow.detection_threshold}")
        console.print(f"  default_skip_stages: {config.workflow.default_skip_stages or '[]'}")
        console.print(f"  interactive: {config.workflow.interactive}")

    def show_autonomous():
        console.print("[bold]Autonomous:[/bold]")
        console.print(f"  enabled: {config.autonomous.enabled}")
        console.print(f"  max_retries: {config.autonomous.max_retries}")
        console.print(f"  verification_enabled: {config.autonomous.verification_enabled}")
        console.print(f"  run_tests: {config.autonomous.run_tests}")
        console.print(f"  check_types: {config.autonomous.check_types}")
        console.print(f"  learning_enabled: {config.autonomous.learning_enabled}")
        console.print(f"  deep_analysis: {config.autonomous.deep_analysis}")
        console.print(f"  deep_reasoning: {config.autonomous.deep_reasoning}")
        console.print(f"  verbose: {config.autonomous.verbose}")

    def show_personality():
        console.print("[bold]Personality:[/bold]")
        console.print(f"  enabled: {config.personality.enabled}")
        console.print(f"  name: {config.personality.name}")
        if config.personality.custom_instructions:
            console.print(f"  custom_instructions: {config.personality.custom_instructions[:50]}...")

    sections = {
        "defaults": show_defaults,
        "kira": show_kira,
        "memory": show_memory,
        "thinking": show_thinking,
        "workflow": show_workflow,
        "autonomous": show_autonomous,
        "personality": show_personality,
    }

    console.print("[cyan]Current Configuration[/cyan]\n")

    if section:
        if section.lower() in sections:
            sections[section.lower()]()
        else:
            print_error(f"Unknown section: {section}")
            console.print(f"Available: {', '.join(sections.keys())}")
            raise typer.Exit(1)
    else:
        for name, show_fn in sections.items():
            show_fn()
            console.print()

        console.print("[bold]Paths:[/bold]")
        console.print(f"  user config: {Config.USER_CONFIG_FILE}")
        console.print(f"  project config: {Config.PROJECT_CONFIG_FILE}")

        if Config.USER_CONFIG_FILE.exists():
            print_info("\nUser config file exists")
        else:
            print_info("\nNo user config file (using defaults)")


@app.command("set")
def set_config(
    key: Annotated[str, typer.Argument(help="Config key (e.g., 'agent', 'model')")],
    value: Annotated[str, typer.Argument(help="Config value")],
):
    """Set a configuration value.

    Available keys:
    - agent: Default agent name
    - model: Default model name
    - trust: Trust all tools (true/false)
    - timeout: Kira timeout in seconds
    - memory: Enable memory (true/false)
    - memory.tokens: Max memory context tokens
    - memory.importance: Minimum importance threshold
    - memory.extract: Auto-extract memories (true/false)
    - thinking: Enable thinking mode (true/false)
    - thinking.model: Planning model
    - thinking.show_plan: Show plan before execution (true/false)
    - autonomous: Enable autonomous mode (true/false)
    - autonomous.retries: Max self-correction attempts
    - autonomous.verify: Enable verification (true/false)
    - autonomous.tests: Run tests (true/false)
    - autonomous.learn: Enable learning (true/false)
    - personality: Enable personality (true/false)
    - personality.name: Agent name
    """
    config = Config.load()

    key_lower = key.lower()

    def parse_bool(v: str) -> bool:
        return v.lower() in ("true", "1", "yes", "on")

    def parse_int(v: str) -> int:
        try:
            return int(v)
        except ValueError:
            print_error(f"Invalid integer: {v}")
            raise typer.Exit(1)

    def parse_float(v: str) -> float:
        try:
            return float(v)
        except ValueError:
            print_error(f"Invalid number: {v}")
            raise typer.Exit(1)

    # Defaults
    if key_lower == "agent":
        config.default_agent = value
    elif key_lower == "model":
        config.kira.model = value if value.lower() != "none" else None
    elif key_lower == "trust":
        config.kira.trust_all_tools = parse_bool(value)
    elif key_lower == "timeout":
        config.kira.timeout = parse_int(value)
    # Memory
    elif key_lower == "memory":
        config.memory.enabled = parse_bool(value)
    elif key_lower == "memory.tokens":
        config.memory.max_context_tokens = parse_int(value)
    elif key_lower == "memory.importance":
        config.memory.min_importance = parse_int(value)
    elif key_lower == "memory.extract":
        config.memory.auto_extract = parse_bool(value)
    # Thinking
    elif key_lower == "thinking":
        config.thinking.enabled = parse_bool(value)
    elif key_lower == "thinking.model":
        config.thinking.planning_model = value if value.lower() != "none" else None
    elif key_lower == "thinking.show_plan":
        config.thinking.show_plan = parse_bool(value)
    elif key_lower == "thinking.save_plans":
        config.thinking.save_plans = parse_bool(value)
    # Workflow
    elif key_lower == "workflow.detect":
        config.workflow.auto_detect = parse_bool(value)
    elif key_lower == "workflow.threshold":
        config.workflow.detection_threshold = parse_float(value)
    elif key_lower == "workflow.interactive":
        config.workflow.interactive = parse_bool(value)
    # Autonomous
    elif key_lower == "autonomous":
        config.autonomous.enabled = parse_bool(value)
    elif key_lower == "autonomous.retries":
        config.autonomous.max_retries = parse_int(value)
    elif key_lower == "autonomous.verify":
        config.autonomous.verification_enabled = parse_bool(value)
    elif key_lower == "autonomous.tests":
        config.autonomous.run_tests = parse_bool(value)
    elif key_lower == "autonomous.types":
        config.autonomous.check_types = parse_bool(value)
    elif key_lower == "autonomous.learn":
        config.autonomous.learning_enabled = parse_bool(value)
    elif key_lower == "autonomous.deep_analysis":
        config.autonomous.deep_analysis = parse_bool(value)
    elif key_lower == "autonomous.deep_reasoning":
        config.autonomous.deep_reasoning = parse_bool(value)
    elif key_lower == "autonomous.verbose":
        config.autonomous.verbose = parse_bool(value)
    # Personality
    elif key_lower == "personality":
        config.personality.enabled = parse_bool(value)
    elif key_lower == "personality.name":
        config.personality.name = value
    else:
        print_error(f"Unknown config key: {key}")
        console.print("\nRun 'kira config set --help' for available keys")
        raise typer.Exit(1)

    config.save_user_config()
    print_success(f"Set {key} = {value}")


@app.command("init")
def init_config(
    user: Annotated[
        bool,
        typer.Option("--user", "-u", help="Initialize user config instead of project"),
    ] = False,
    full: Annotated[
        bool,
        typer.Option("--full", "-f", help="Generate full config with all options"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing config"),
    ] = False,
):
    """Initialize configuration file.

    By default, creates a project config (.kira/agent.yaml).
    Use --user to create user config (~/.kira/agent/config.yaml).
    Use --full to include all available options with documentation.
    """
    if user:
        config_path = Config.USER_CONFIG_FILE
        config_type = "user"
    else:
        config_path = Path.cwd() / ".kira.yaml"
        config_type = "project"

    if config_path.exists() and not force:
        print_error(f"{config_type.title()} config already exists: {config_path}")
        console.print("Use --force to overwrite")
        raise typer.Exit(1)

    config_path.parent.mkdir(parents=True, exist_ok=True)

    if full:
        content = D.get_default_config_yaml()
    else:
        content = D.get_minimal_config_yaml()

    with open(config_path, "w") as f:
        f.write(content)

    print_success(f"Created {config_type} config: {config_path}")
    if full:
        print_info("All options included with documentation")
    else:
        print_info("Use --full for all available options")


@app.command("edit")
def edit_config(
    user: Annotated[
        bool,
        typer.Option("--user", "-u", help="Edit user config instead of project"),
    ] = False,
):
    """Open configuration file in editor."""
    import os
    import subprocess

    if user:
        config_path = Config.USER_CONFIG_FILE
        config_type = "user"
    else:
        config_path = Path.cwd() / ".kira.yaml"
        config_type = "project"

    if not config_path.exists():
        print_error(f"{config_type.title()} config not found: {config_path}")
        console.print(f"Run 'kira config init {'--user' if user else ''}' to create it")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
    try:
        subprocess.run([editor, str(config_path)], check=True)
    except FileNotFoundError:
        print_error(f"Editor not found: {editor}")
        console.print("Set EDITOR environment variable to your preferred editor")
        raise typer.Exit(1)


@app.command("reset")
def reset_config(
    user: Annotated[
        bool,
        typer.Option("--user", "-u", help="Reset user config instead of project"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Reset configuration to defaults."""
    if user:
        config_path = Config.USER_CONFIG_FILE
        config_type = "user"
    else:
        config_path = Path.cwd() / ".kira.yaml"
        config_type = "project"

    if not config_path.exists():
        print_info(f"No {config_type} config file to reset")
        return

    if not force:
        console.print(f"About to delete: {config_path}")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            raise typer.Abort()

    config_path.unlink()
    print_success(f"Reset {config_type} configuration to defaults")


@app.command("path")
def show_paths():
    """Show configuration file paths."""
    console.print("[cyan]Configuration Paths[/cyan]\n")

    console.print(f"[bold]User config:[/bold] {Config.USER_CONFIG_FILE}")
    if Config.USER_CONFIG_FILE.exists():
        console.print("  [green]✓ exists[/green]")
    else:
        console.print("  [dim]not created[/dim]")

    console.print()

    project_config = Path.cwd() / ".kira.yaml"
    console.print(f"[bold]Project config:[/bold] {project_config}")
    if project_config.exists():
        console.print("  [green]✓ exists[/green]")
    else:
        console.print("  [dim]not created[/dim]")

    console.print()
    console.print(f"[bold]Data directory:[/bold] {Config.USER_DATA_DIR}")
    if Config.USER_DATA_DIR.exists():
        console.print("  [green]✓ exists[/green]")
    else:
        console.print("  [dim]not created[/dim]")
