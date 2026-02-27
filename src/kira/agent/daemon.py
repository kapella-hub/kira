"""Local agent daemon -- WebSocket server that bridges browser to WorkerRunner."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import json
import logging
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import websockets
from websockets.asyncio.server import ServerConnection

from kira.worker.client import ServerClient
from kira.worker.config import WorkerConfig
from kira.worker.runner import WORKER_VERSION, WorkerRunner

logger = logging.getLogger(__name__)

# Valid origins that can connect to the agent
ALLOWED_ORIGIN_PREFIXES = ("http://localhost", "http://127.0.0.1", "https://")


class AgentDaemon:
    """Local WebSocket daemon that activates the worker on browser login."""

    def __init__(self, port: int = 9820, grace_period: float = 3.0):
        self.port = port
        self.grace_period = grace_period
        self.state = "dormant"

        # Session tracking (session_id -> websocket)
        self.sessions: dict[str, ServerConnection] = {}
        self._ws_to_session: dict[int, str] = {}

        # Worker state
        self.runner: WorkerRunner | None = None
        self.server_client: ServerClient | None = None
        self._runner_task: asyncio.Task | None = None
        self._active_server_url: str | None = None
        self._activated_at: float | None = None

        # Grace period
        self._grace_task: asyncio.Task | None = None

        # PID file
        self._pidfile = Path.home() / ".kira" / "agent.pid"

    @staticmethod
    def _is_kira_process(pid: int) -> bool:
        """Check if the given PID belongs to a kira process."""
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "kira" in result.stdout.lower()
        except (subprocess.TimeoutExpired, OSError):
            # If we can't verify, assume it's kira to be safe
            return True

    async def _check_server_version(self, server_url: str) -> None:
        """Check the server for version updates and notify connected sessions."""
        try:
            local_version = importlib.metadata.version("kira")
        except importlib.metadata.PackageNotFoundError:
            logger.debug("Cannot determine local kira version, skipping version check")
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{server_url}/api/agent/version")
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.debug("Version check failed: %s", e)
            return

        server_version = data.get("version", "")
        if not server_version or server_version == local_version:
            return

        install_url = data.get("install_url", server_url)
        msg = json.dumps(
            {
                "type": "upgrade_available",
                "current_version": local_version,
                "server_version": server_version,
                "install_url": f"{install_url}/api/agent/install.sh",
            }
        )
        for ws in list(self.sessions.values()):
            with contextlib.suppress(websockets.ConnectionClosed):
                await ws.send(msg)

        logger.info(
            "Upgrade available: %s -> %s",
            local_version,
            server_version,
        )

    async def start(self) -> None:
        """Start the WebSocket server and block until shutdown."""
        self._pidfile.parent.mkdir(parents=True, exist_ok=True)

        # Check for existing instance
        if self._pidfile.exists():
            try:
                old_pid = int(self._pidfile.read_text().strip())
                os.kill(old_pid, 0)
                # PID exists -- verify it's actually a kira agent, not a recycled PID
                if self._is_kira_process(old_pid):
                    logger.error("Agent already running (PID %d)", old_pid)
                    raise SystemExit(1)
                else:
                    logger.warning(
                        "PID %d exists but is not a kira process, removing stale PID file",
                        old_pid,
                    )
            except (ProcessLookupError, ValueError):
                pass  # Stale PID file

        self._pidfile.write_text(str(os.getpid()))

        # Handle shutdown signals
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self._shutdown()))

        try:
            async with websockets.serve(
                self._handle_connection,
                "127.0.0.1",
                self.port,
            ):
                logger.info("Agent listening on ws://127.0.0.1:%d (dormant)", self.port)
                await asyncio.Future()  # Block forever
        except asyncio.CancelledError:
            pass
        finally:
            await self._stop_runner()
            self._pidfile.unlink(missing_ok=True)

    async def _shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down agent...")
        await self._stop_runner()
        self._pidfile.unlink(missing_ok=True)
        raise SystemExit(0)

    # --- WebSocket handling ---

    async def _handle_connection(self, ws: ServerConnection) -> None:
        """Handle a single WebSocket connection."""
        # Validate origin
        origin = ""
        if ws.request is not None:
            origin = ws.request.headers.get("Origin", "")
        if origin and not any(origin.startswith(p) for p in ALLOWED_ORIGIN_PREFIXES):
            await ws.close(4403, "Forbidden origin")
            return

        # Send current status
        await ws.send(self._status_json())

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    await self._handle_message(ws, msg)
                except json.JSONDecodeError:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "invalid_json",
                                "message": "Invalid JSON message",
                            }
                        )
                    )
        except websockets.ConnectionClosed:
            pass
        finally:
            # Remove session
            session_id = self._ws_to_session.pop(id(ws), None)
            if session_id and session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(
                    "Session %s disconnected (%d remaining)",
                    session_id[:8],
                    len(self.sessions),
                )
            self._check_empty_sessions()

    async def _handle_message(self, ws: ServerConnection, msg: dict[str, Any]) -> None:
        """Route a message to the appropriate handler."""
        msg_type = msg.get("type", "")

        if msg_type == "activate":
            await self._activate(ws, msg)
        elif msg_type == "deactivate":
            await self._deactivate(msg)
        elif msg_type == "ping":
            await ws.send(json.dumps({"type": "pong"}))
        elif msg_type == "pick_directory":
            await self._pick_directory(ws, msg)

    # --- Directory picker ---

    async def _pick_directory(self, ws: ServerConnection, msg: dict[str, Any]) -> None:
        """Open a native OS directory picker and return the selected path."""
        request_id = msg.get("request_id", "")
        initial_dir = msg.get("initial_dir", "")

        try:
            path = await asyncio.to_thread(self._open_dir_dialog, initial_dir)
            await ws.send(
                json.dumps(
                    {
                        "type": "directory_picked",
                        "request_id": request_id,
                        "path": path or "",
                        "cancelled": path is None,
                    }
                )
            )
        except Exception as e:
            logger.warning("Directory picker failed: %s", e)
            await ws.send(
                json.dumps(
                    {
                        "type": "directory_picked",
                        "request_id": request_id,
                        "path": "",
                        "cancelled": True,
                        "error": str(e),
                    }
                )
            )

    @staticmethod
    def _open_dir_dialog(initial_dir: str = "") -> str | None:
        """Open a native directory dialog. Returns path or None if cancelled.

        Uses osascript on macOS for a native Finder dialog, or tkinter on
        Linux/other. Runs in a thread to avoid blocking the event loop.
        """
        import sys

        if sys.platform == "darwin":
            script = 'tell application "System Events" to activate\n'
            if initial_dir:
                script += (
                    f'set defaultDir to POSIX file "{initial_dir}" as alias\n'
                    "set chosenDir to choose folder "
                    'with prompt "Select working directory" '
                    "default location defaultDir\n"
                )
            else:
                script += 'set chosenDir to choose folder with prompt "Select working directory"\n'
            script += "return POSIX path of chosenDir"

            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().rstrip("/")
                return None
            except (subprocess.TimeoutExpired, OSError):
                return None
        else:
            # Linux/other: use tkinter if available
            try:
                import tkinter as tk
                from tkinter import filedialog

                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                path = filedialog.askdirectory(
                    title="Select working directory",
                    initialdir=initial_dir or None,
                )
                root.destroy()
                return path if path else None
            except ImportError:
                return None

    # --- Activation / deactivation ---

    async def _activate(self, ws: ServerConnection, msg: dict[str, Any]) -> None:
        """Activate the worker with provided credentials."""
        session_id = msg.get("session_id", "")
        token = msg.get("token", "")
        server_url = msg.get("server_url", "")

        if not token or not server_url:
            await ws.send(
                json.dumps(
                    {
                        "type": "error",
                        "code": "missing_fields",
                        "message": "token and server_url are required",
                    }
                )
            )
            return

        # Track this session
        self.sessions[session_id] = ws
        self._ws_to_session[id(ws)] = session_id

        # Cancel grace timer if running
        if self._grace_task and not self._grace_task.done():
            self._grace_task.cancel()
            self._grace_task = None

        if self.state == "active":
            if self._active_server_url == server_url:
                # Same server -- just update the token
                if self.server_client:
                    self.server_client.set_token(token)
                logger.info("Token updated for session %s", session_id[:8])
                await self._broadcast_status()
                return
            else:
                # Different server -- restart
                await self._stop_runner()

        # Activate
        self._set_state("activating")
        try:
            await self._start_runner(server_url, token)
            self._set_state("active")
            logger.info(
                "Agent activated: server=%s, worker=%s",
                server_url,
                self.runner.worker_id if self.runner else "?",
            )
            # Fire-and-forget version check -- don't block activation
            asyncio.create_task(self._check_server_version(server_url))
        except Exception as e:
            logger.error("Activation failed: %s", e)
            await self._broadcast_error("registration_failed", str(e))
            self._set_state("dormant")

    async def _deactivate(self, msg: dict[str, Any]) -> None:
        """Explicit deactivation from browser logout (no grace period)."""
        session_id = msg.get("session_id", "")
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info("Session %s deactivated explicitly", session_id[:8])

        if not self.sessions and self.state == "active":
            await self._stop_runner()
            self._set_state("dormant")
            logger.info("Agent deactivated (explicit logout)")

    # --- WorkerRunner lifecycle ---

    async def _start_runner(self, server_url: str, token: str) -> None:
        """Create ServerClient and WorkerRunner, register, start loops."""
        config = WorkerConfig.load()
        config.server_url = server_url

        self.server_client = ServerClient(server_url, token=token)
        self.runner = WorkerRunner(
            config,
            self.server_client,
            on_tasks_changed=self._on_tasks_changed,
        )

        # Register with server
        result = await self.server_client.register_worker(
            hostname=socket.gethostname(),
            version=WORKER_VERSION,
            capabilities=["agent", "jira", "board_plan", "card_gen"],
        )
        self.runner.worker_id = result["worker_id"]

        # Apply server overrides
        if "poll_interval_seconds" in result:
            config.poll_interval = float(result["poll_interval_seconds"])
        if "max_concurrent_tasks" in result:
            config.max_concurrent_tasks = int(result["max_concurrent_tasks"])

        self._active_server_url = server_url
        self._activated_at = time.monotonic()

        # Start poll + heartbeat loops
        self._runner_task = asyncio.create_task(self._run_loops())

    async def _run_loops(self) -> None:
        """Run the WorkerRunner poll and heartbeat loops concurrently."""
        await asyncio.gather(
            self.runner._poll_loop(),
            self.runner._heartbeat_loop(),
        )

    async def _stop_runner(self) -> None:
        """Stop WorkerRunner and close ServerClient."""
        if self.runner:
            await self.runner.stop()
        if self._runner_task:
            self._runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner_task
            self._runner_task = None
        if self.server_client:
            await self.server_client.close()
            self.server_client = None
        self.runner = None
        self._active_server_url = None
        self._activated_at = None

    # --- Grace period ---

    def _check_empty_sessions(self) -> None:
        """Start grace timer if no sessions remain."""
        if not self.sessions and self.state == "active":
            self._set_state("deactivating")
            self._grace_task = asyncio.create_task(self._grace_expired())

    async def _grace_expired(self) -> None:
        """Grace period elapsed -- deactivate if still empty."""
        await asyncio.sleep(self.grace_period)
        if not self.sessions:
            logger.info("Grace period expired, deactivating")
            await self._stop_runner()
            self._set_state("dormant")
        else:
            # Someone reconnected
            self._set_state("active")

    def _on_tasks_changed(self) -> None:
        """Callback from WorkerRunner when task count changes."""
        asyncio.create_task(self._broadcast_status())

    # --- State and broadcasting ---

    def _set_state(self, state: str) -> None:
        """Update state and broadcast to all connected sessions."""
        old = self.state
        self.state = state
        if old != state:
            logger.info("State: %s -> %s", old, state)
            asyncio.create_task(self._broadcast_status())

    async def _broadcast_status(self) -> None:
        """Send status to all connected sessions."""
        msg = self._status_json()
        closed = []
        for sid, ws in self.sessions.items():
            try:
                await ws.send(msg)
            except websockets.ConnectionClosed:
                closed.append(sid)
        for sid in closed:
            self.sessions.pop(sid, None)

    async def _broadcast_error(self, code: str, message: str) -> None:
        """Send error to all connected sessions."""
        msg = json.dumps({"type": "error", "code": code, "message": message})
        for ws in list(self.sessions.values()):
            with contextlib.suppress(websockets.ConnectionClosed):
                await ws.send(msg)

    def _status_json(self) -> str:
        """Build status JSON message."""
        running_tasks = 0
        if self.runner:
            running_tasks = len(self.runner._current_tasks)

        uptime = 0.0
        if self._activated_at is not None:
            uptime = time.monotonic() - self._activated_at

        worker_id = None
        if self.runner:
            worker_id = self.runner.worker_id

        return json.dumps(
            {
                "type": "status",
                "state": self.state,
                "worker_id": worker_id,
                "server_url": self._active_server_url,
                "running_tasks": running_tasks,
                "uptime_seconds": round(uptime),
            }
        )
