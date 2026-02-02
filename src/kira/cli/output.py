"""Rich console output helpers."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

# Shared console instance
console = Console()
error_console = Console(stderr=True)


def print_error(message: str) -> None:
    """Print an error message."""
    error_console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]{message}[/green]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[dim]{message}[/dim]")


def create_table(title: str, columns: list[tuple[str, str]]) -> Table:
    """Create a styled table.

    Args:
        title: Table title
        columns: List of (name, style) tuples
    """
    table = Table(title=title, show_header=True, header_style="bold")
    for name, style in columns:
        table.add_column(name, style=style)
    return table


def print_memory_table(
    memories: list,
    title: str = "Memories",
    show_decay: bool = False,
) -> None:
    """Print a table of memories."""
    from ..memory.models import Memory

    columns = [
        ("Key", "cyan"),
        ("Content", ""),
        ("Type", "magenta"),
        ("Importance", "yellow"),
    ]

    if show_decay:
        columns.append(("Decayed", "yellow"))

    columns.extend([
        ("Tags", "green"),
        ("Updated", "dim"),
    ])

    table = create_table(title, columns)

    for mem in memories:
        if isinstance(mem, Memory):
            content = mem.content[:50] + "..." if len(mem.content) > 50 else mem.content
            tags = ", ".join(mem.tags) if mem.tags else "-"
            updated = mem.updated_at.strftime("%Y-%m-%d %H:%M")
            mem_type = mem.memory_type.value[:4]  # Abbreviate type

            row = [
                mem.key,
                content,
                mem_type,
                str(mem.importance),
            ]

            if show_decay:
                row.append(f"{mem.decayed_importance:.1f}")

            row.extend([tags, updated])
            table.add_row(*row)

    console.print(table)


def print_skill_table(skills: list, title: str = "Skills") -> None:
    """Print a table of skills."""
    from ..skills.manager import Skill

    table = create_table(
        title,
        [
            ("Name", "cyan"),
            ("Description", ""),
            ("Tags", "green"),
            ("Location", "dim"),
        ],
    )

    for skill in skills:
        if isinstance(skill, Skill):
            tags = ", ".join(skill.tags) if skill.tags else "-"
            location = "builtin" if "builtin" in str(skill.path) else "user"
            table.add_row(
                skill.name,
                skill.description[:50] + "..." if len(skill.description) > 50 else skill.description,
                tags,
                location,
            )

    console.print(table)


def print_panel(content: str, title: str | None = None) -> None:
    """Print content in a panel."""
    console.print(Panel(content, title=title))
