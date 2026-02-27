"""Worker CLI commands.

Provides the async entry point for starting the worker process,
handling login, registration, and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import socket

from rich.console import Console

from .client import ServerClient, ServerError
from .config import WorkerConfig
from .runner import WorkerRunner

console = Console()
logger = logging.getLogger(__name__)


async def start_worker(server_url: str, username: str, password: str = "") -> None:
    """Start the worker process.

    Authenticates with the server, registers the worker, and begins
    polling for tasks. Handles Ctrl+C for graceful shutdown.

    Args:
        server_url: Base URL of the Kira server (e.g., http://localhost:8000).
        username: Username to authenticate as.
        password: Password for CentAuth mode (optional, prompted if needed).
    """
    config = WorkerConfig.load()
    config.server_url = server_url

    server = ServerClient(config.server_url, token="")

    console.print(f"[cyan]Connecting to {server_url}...[/cyan]")

    # Check auth mode to determine what credentials are needed
    try:
        auth_config = await server.get_auth_config()
    except ServerError:
        auth_config = {"auth_mode": "mock"}

    is_centauth = auth_config.get("auth_mode") == "centauth"

    # Prompt for username if not provided via CLI or env
    if not username:
        username = input("Username: ")

    if is_centauth:
        # Use password from: CLI arg > env var > prompt
        if not password:
            password = config.password
        if not password:
            import getpass

            password = getpass.getpass("Password: ")

    # Authenticate
    try:
        auth = await server.login(username, password)
    except ServerError as e:
        console.print(f"[red]Login failed:[/red] {e.message}")
        await server.close()
        return

    server.set_token(auth["token"])
    user_display = auth.get("user", {}).get("username", username)
    console.print(f"[green]v[/green] Logged in as {user_display}")

    # Create and start runner
    runner = WorkerRunner(config, server)

    try:
        # Register (this happens inside runner.start(), but we want to show
        # the success message before the poll loop begins)
        from .runner import WORKER_VERSION

        reg_result = await server.register_worker(
            hostname=socket.gethostname(),
            version=WORKER_VERSION,
            capabilities=["agent", "jira"],
        )
        runner.worker_id = reg_result["worker_id"]

        # Apply server-side config overrides
        if "poll_interval_seconds" in reg_result:
            config.poll_interval = float(reg_result["poll_interval_seconds"])
        if "max_concurrent_tasks" in reg_result:
            config.max_concurrent_tasks = int(reg_result["max_concurrent_tasks"])

        console.print(f"[green]v[/green] Worker registered ({socket.gethostname()})")
        console.print(f"[dim]Polling for tasks every {config.poll_interval}s...[/dim]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        # Run the poll and heartbeat loops (already registered, so go straight
        # to the loops instead of calling runner.start() which re-registers)
        await asyncio.gather(
            runner._poll_loop(),
            runner._heartbeat_loop(),
        )

    except ServerError as e:
        console.print(f"[red]Registration failed:[/red] {e.message}")
    except KeyboardInterrupt:
        console.print("\n[dim]Shutting down worker...[/dim]")
        await runner.stop()
        console.print("[dim]Worker stopped.[/dim]")
    except asyncio.CancelledError:
        console.print("\n[dim]Worker cancelled.[/dim]")
        await runner.stop()
    finally:
        await server.close()
