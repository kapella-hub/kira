"""Agent CLI entry points."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from rich.console import Console

console = Console()


async def start_agent(port: int = 9820, grace_period: float = 3.0) -> None:
    """Start the agent daemon."""
    # Configure logging
    log_format = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)

    from .daemon import AgentDaemon

    daemon = AgentDaemon(port=port, grace_period=grace_period)
    await daemon.start()


def install_service() -> None:
    """Install agent as a system service."""
    from . import service

    try:
        result = service.install()
        console.print(f"[green]v[/green] {result}")
    except Exception as e:
        console.print(f"[red]Failed to install service:[/red] {e}")


def uninstall_service() -> None:
    """Remove agent system service."""
    from . import service

    try:
        result = service.uninstall()
        console.print(f"[green]v[/green] {result}")
    except Exception as e:
        console.print(f"[red]Failed to uninstall service:[/red] {e}")


def show_status() -> None:
    """Show agent status."""
    from . import service

    pidfile = Path.home() / ".kira" / "agent.pid"
    installed = service.is_installed()

    console.print("[bold]Kira Agent[/bold]")
    console.print()

    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            console.print("  Status:    [green]running[/green]")
            console.print(f"  PID:       {pid}")
        except (ProcessLookupError, ValueError):
            console.print("  Status:    [yellow]not running[/yellow] (stale PID file)")
    else:
        console.print("  Status:    [dim]not running[/dim]")

    status_label = "[green]installed[/green]" if installed else "[dim]not installed[/dim]"
    console.print(f"  Service:   {status_label}")
    console.print("  Port:      9820")
    console.print()

    if not installed:
        console.print("[dim]Install as service: kira agent install[/dim]")
