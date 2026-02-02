"""Run log commands."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from ...logs import RunLogStore
from ...logs.models import RunMode
from ..output import console, print_error, print_info, print_success

app = typer.Typer(help="View run logs and history")


def get_store() -> RunLogStore:
    """Get the run log store instance."""
    return RunLogStore()


@app.command("list")
def list_runs(
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", "-m", help="Filter by mode (repl, chat, thinking, autonomous, workflow)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum runs to show"),
    ] = 20,
):
    """List recent runs."""
    store = get_store()

    run_mode = RunMode(mode) if mode else None
    runs = store.list_runs(mode=run_mode, limit=limit)

    if not runs:
        print_info("No runs found")
        return

    table = Table(title="Run History", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Mode", width=10)
    table.add_column("Messages", justify="right", width=8)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Model", width=15)
    table.add_column("Started", style="dim", width=18)

    for run in runs:
        started = run.started_at.strftime("%Y-%m-%d %H:%M")
        model = run.model or "-"
        if len(model) > 15:
            model = model[:12] + "..."

        table.add_row(
            str(run.id),
            run.mode_display,
            str(run.entry_count),
            run.duration_display,
            model,
            started,
        )

    console.print(table)

    total = store.count_runs(run_mode)
    if total > limit:
        print_info(f"Showing {limit} of {total} runs")


@app.command("show")
def show_run(
    run_id: Annotated[int, typer.Argument(help="Run ID to show")],
    full: Annotated[
        bool,
        typer.Option("--full", "-f", help="Show full prompts and responses"),
    ] = False,
):
    """Show details of a specific run."""
    store = get_store()
    run = store.get_run(run_id, include_entries=True)

    if not run:
        print_error(f"Run not found: {run_id}")
        raise typer.Exit(1)

    # Header
    console.print(f"\n[bold cyan]Run #{run.id}[/bold cyan]")
    console.print(f"[dim]Mode:[/dim] {run.mode_display}")
    console.print(f"[dim]Model:[/dim] {run.model or '-'}")
    console.print(f"[dim]Started:[/dim] {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if run.ended_at:
        console.print(f"[dim]Ended:[/dim] {run.ended_at.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"[dim]Duration:[/dim] {run.duration_display}")
    console.print(f"[dim]Messages:[/dim] {run.entry_count}")
    if run.working_dir:
        console.print(f"[dim]Directory:[/dim] {run.working_dir}")
    if run.skills:
        console.print(f"[dim]Skills:[/dim] {', '.join(run.skills)}")
    console.print()

    # Entries
    if not run.entries:
        print_info("No messages in this run")
        return

    for i, entry in enumerate(run.entries, 1):
        console.print(f"[bold yellow]Message {i}[/bold yellow] ", end="")
        console.print(f"[dim]({entry.duration_seconds:.1f}s)[/dim]")

        if full:
            console.print(Panel(entry.prompt, title="Prompt", border_style="blue"))
            if entry.response:
                # Truncate very long responses
                response = entry.response
                if len(response) > 2000:
                    response = response[:2000] + "\n\n[dim]... (truncated)[/dim]"
                console.print(Panel(response, title="Response", border_style="green"))
        else:
            prompt_preview = entry.prompt.replace("\n", " ")[:100]
            if len(entry.prompt) > 100:
                prompt_preview += "..."
            console.print(f"[blue]>[/blue] {prompt_preview}")

            if entry.response:
                response_preview = entry.response.replace("\n", " ")[:100]
                if len(entry.response) > 100:
                    response_preview += "..."
                console.print(f"[green]<[/green] {response_preview}")

        console.print()


@app.command("search")
def search_runs(
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum results"),
    ] = 20,
):
    """Search run history by prompt/response content."""
    store = get_store()
    results = store.search_entries(query, limit=limit)

    if not results:
        print_info(f"No matches for '{query}'")
        return

    table = Table(title=f"Search: {query}", show_header=True, header_style="bold cyan")
    table.add_column("Run", style="dim", width=5)
    table.add_column("Mode", width=8)
    table.add_column("Preview", width=60)
    table.add_column("Date", style="dim", width=12)

    for run, entry in results:
        preview = entry.preview(60)
        date = entry.created_at.strftime("%Y-%m-%d")

        table.add_row(
            str(run.id),
            run.mode_display,
            preview,
            date,
        )

    console.print(table)
    print_info(f"Use 'kira logs show <id>' to view full run")


@app.command("stats")
def log_stats():
    """Show run log statistics."""
    store = get_store()
    stats = store.get_stats()

    console.print("[cyan]Run Log Statistics[/cyan]\n")
    console.print(f"[dim]Total runs:[/dim] {stats['total_runs']}")
    console.print(f"[dim]Total messages:[/dim] {stats['total_entries']}")

    # Total duration
    total_mins = int(stats['total_duration'] // 60)
    total_secs = int(stats['total_duration'] % 60)
    console.print(f"[dim]Total duration:[/dim] {total_mins}m {total_secs}s")

    if stats['by_mode']:
        console.print("\n[dim]By mode:[/dim]")
        for mode, count in stats['by_mode'].items():
            console.print(f"  {mode}: {count}")


@app.command("clear")
def clear_logs(
    days: Annotated[
        Optional[int],
        typer.Option("--older-than", "-d", help="Clear runs older than N days"),
    ] = None,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", "-m", help="Only clear runs of this mode"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Clear run logs."""
    store = get_store()

    before = None
    if days:
        before = datetime.utcnow() - timedelta(days=days)

    run_mode = RunMode(mode) if mode else None

    # Get count before clearing
    if before or run_mode:
        # Estimate count (not exact but gives user an idea)
        if run_mode:
            count = store.count_runs(run_mode)
        else:
            count = store.count_runs()
    else:
        count = store.count_runs()

    if count == 0:
        print_info("No logs to clear")
        return

    # Build description
    desc_parts = []
    if days:
        desc_parts.append(f"older than {days} days")
    if mode:
        desc_parts.append(f"mode: {mode}")

    if desc_parts:
        desc = f"About to clear runs matching: {', '.join(desc_parts)}"
    else:
        desc = f"About to clear ALL {count} runs"

    if not force:
        console.print(desc)
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            raise typer.Abort()

    deleted = store.clear(before=before, mode=run_mode)
    print_success(f"Cleared {deleted} runs")


@app.command("last")
def show_last_run(
    full: Annotated[
        bool,
        typer.Option("--full", "-f", help="Show full prompts and responses"),
    ] = False,
):
    """Show the most recent run."""
    store = get_store()
    run = store.get_latest_run()

    if not run:
        print_info("No runs found")
        return

    # Delegate to show command
    show_run(run.id, full=full)
