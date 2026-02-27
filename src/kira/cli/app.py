"""Main CLI application -- Kira Agent Kanban Board.

Provides commands for:
  - serve: Start the web server (FastAPI)
  - worker: Start a local worker that executes agent and Jira tasks
  - agent: Local agent daemon (browser-activated worker)
  - version: Show version information
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="kira",
    help="Kira Agent Kanban Board",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()


@app.command("serve")
def serve(
    host: Annotated[
        str,
        typer.Option("--host", "-H", help="Host to bind to"),
    ] = "0.0.0.0",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to listen on"),
    ] = 8000,
    reload: Annotated[
        bool,
        typer.Option("--reload", "-r", help="Enable auto-reload for development"),
    ] = False,
):
    """Start the Kanban board web server."""
    import uvicorn

    console.print("[cyan]Starting Kira Kanban Board[/cyan]")
    console.print(f"[dim]Server: http://{host}:{port}[/dim]")
    console.print(f"[dim]API docs: http://{host}:{port}/docs[/dim]\n")

    uvicorn.run(
        "kira.web.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@app.command("worker")
def worker(
    server_url: Annotated[
        str,
        typer.Option("--server", "-s", help="Kira server URL"),
    ] = "http://localhost:8000",
    username: Annotated[
        str,
        typer.Option("--user", "-u", help="Username to authenticate as"),
    ] = "",
    password: Annotated[
        str,
        typer.Option("--password", "-p", help="Password (for CentAuth mode)"),
    ] = "",
):
    """Start a local worker that executes agent and Jira tasks.

    The worker connects to the Kira server, polls for pending tasks,
    and executes them using local kiro-cli and Jira credentials.

    Examples:
        kira worker
        kira worker --server http://kira.internal:8000 --user alice
        kira worker --user alice --password secret
    """
    from kira.worker.cli import start_worker

    try:
        asyncio.run(start_worker(server_url, username, password))
    except KeyboardInterrupt:
        console.print("\n[dim]Worker stopped.[/dim]")


# --- Agent subcommand group ---

agent_app = typer.Typer(
    name="agent",
    help="Local agent daemon (browser-activated worker)",
    no_args_is_help=True,
)
app.add_typer(agent_app)


@agent_app.command("start")
def agent_start(
    port: Annotated[
        int,
        typer.Option("--port", help="WebSocket port to listen on"),
    ] = 9820,
    grace_period: Annotated[
        float,
        typer.Option(
            "--grace-period",
            help="Seconds to wait before deactivating after last tab closes",
        ),
    ] = 3.0,
):
    """Start the agent daemon (listens for browser activation)."""
    from kira.agent.cli import start_agent

    console.print("[cyan]Starting Kira Agent[/cyan]")
    console.print(f"[dim]WebSocket: ws://127.0.0.1:{port}[/dim]")
    console.print("[dim]Waiting for browser activation...[/dim]\n")

    try:
        asyncio.run(start_agent(port=port, grace_period=grace_period))
    except KeyboardInterrupt:
        console.print("\n[dim]Agent stopped.[/dim]")
    except SystemExit:
        pass


@agent_app.command("install")
def agent_install():
    """Install agent as a system service (auto-starts on login)."""
    from kira.agent.cli import install_service

    install_service()


@agent_app.command("uninstall")
def agent_uninstall():
    """Remove the agent system service."""
    from kira.agent.cli import uninstall_service

    uninstall_service()


@agent_app.command("status")
def agent_status():
    """Show agent daemon status."""
    from kira.agent.cli import show_status

    show_status()


@app.command("version")
def version():
    """Show version information."""
    from kira import __version__

    console.print(f"kira version: {__version__}")


if __name__ == "__main__":
    app()
