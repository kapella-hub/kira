"""Skills management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ...skills.manager import SkillManager
from ..output import console, print_error, print_info, print_skill_table, print_success

app = typer.Typer(help="Manage skills")


def get_manager() -> SkillManager:
    """Get the skill manager instance."""
    return SkillManager()


@app.command("list")
def list_skills(
    tags: Annotated[
        Optional[list[str]],
        typer.Option("--tags", "-t", help="Filter by tags"),
    ] = None,
):
    """List all available skills."""
    manager = get_manager()
    skills = manager.list_all(tags=tags)

    if not skills:
        print_info("No skills found")
        return

    print_skill_table(skills)


@app.command("show")
def show_skill(
    name: Annotated[str, typer.Argument(help="Skill name")],
):
    """Show details of a skill."""
    manager = get_manager()
    skill = manager.get(name)

    if not skill:
        print_error(f"Skill not found: {name}")
        raise typer.Exit(1)

    console.print(f"[cyan]Name:[/cyan] {skill.name}")
    console.print(f"[cyan]Description:[/cyan] {skill.description}")
    console.print(f"[cyan]Tags:[/cyan] {', '.join(skill.tags) if skill.tags else '-'}")
    if skill.path:
        console.print(f"[cyan]Path:[/cyan] {skill.path}")
    console.print(f"\n[cyan]Prompt:[/cyan]\n{skill.prompt}")


@app.command("add")
def add_skill(
    name: Annotated[str, typer.Argument(help="Skill name")],
    description: Annotated[
        Optional[str],
        typer.Option("--description", "-d", help="Skill description"),
    ] = None,
    prompt: Annotated[
        Optional[str],
        typer.Option("--prompt", "-p", help="Skill prompt text"),
    ] = None,
    from_file: Annotated[
        Optional[Path],
        typer.Option("--from", "-f", help="Import from YAML file"),
    ] = None,
    tags: Annotated[
        Optional[list[str]],
        typer.Option("--tags", "-t", help="Tags for this skill"),
    ] = None,
    local: Annotated[
        bool,
        typer.Option("--local", "-l", help="Save to project instead of user dir"),
    ] = False,
):
    """Add a new skill."""
    manager = get_manager()

    if from_file:
        # Import from YAML file
        if not from_file.exists():
            print_error(f"File not found: {from_file}")
            raise typer.Exit(1)

        from ...skills.manager import Skill
        try:
            skill = Skill.from_yaml(from_file)
            # Override name if provided
            if name != skill.name:
                skill.name = name
            # Add to appropriate directory
            directory = (Path.cwd() / ".kira" / "skills") if local else manager.USER_DIR
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{skill.name}.yaml"
            skill.save(path)
            manager.reload()
            print_success(f"Imported skill: {skill.name}")
        except Exception as e:
            print_error(f"Failed to import skill: {e}")
            raise typer.Exit(1)
        return

    # Create new skill
    if not description:
        print_error("--description is required when creating a new skill")
        raise typer.Exit(1)

    if not prompt:
        # Read prompt from stdin or editor
        console.print("Enter skill prompt (Ctrl+D when done):")
        import sys
        prompt = sys.stdin.read().strip()

    if not prompt:
        print_error("Prompt cannot be empty")
        raise typer.Exit(1)

    try:
        skill = manager.add(
            name=name,
            description=description,
            prompt=prompt,
            tags=tags,
            local=local,
        )
        print_success(f"Created skill: {skill.name}")
        if skill.path:
            print_info(f"Saved to: {skill.path}")
    except Exception as e:
        print_error(f"Failed to create skill: {e}")
        raise typer.Exit(1)


@app.command("remove")
def remove_skill(
    name: Annotated[str, typer.Argument(help="Skill name to remove")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Remove a user-defined skill."""
    manager = get_manager()

    skill = manager.get(name)
    if not skill:
        print_error(f"Skill not found: {name}")
        raise typer.Exit(1)

    if manager.is_builtin(name):
        print_error(f"Cannot remove built-in skill: {name}")
        raise typer.Exit(1)

    if not force:
        console.print(f"About to remove skill: [cyan]{name}[/cyan]")
        console.print(f"Description: {skill.description}")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            raise typer.Abort()

    if manager.remove(name):
        print_success(f"Removed skill: {name}")
    else:
        print_error(f"Failed to remove skill: {name}")
        raise typer.Exit(1)


@app.command("reload")
def reload_skills():
    """Reload all skills from disk."""
    manager = get_manager()
    manager.reload()
    skills = manager.list_all()
    print_success(f"Reloaded {len(skills)} skills")
