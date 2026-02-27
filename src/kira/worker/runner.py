"""Main worker process -- polls for tasks, executes them, and reports results.

The WorkerRunner manages two concurrent loops:
  1. Poll loop: checks the server for pending tasks, claims and executes them.
  2. Heartbeat loop: sends periodic heartbeats and handles cancel directives.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .client import ServerClient, ServerError
from .config import WorkerConfig

logger = logging.getLogger(__name__)

# Version reported to server during registration
WORKER_VERSION = "0.3.0"


class WorkerRunner:
    """Main worker process that polls, executes, and reports."""

    def __init__(
        self,
        config: WorkerConfig,
        server: ServerClient,
        on_tasks_changed: Callable[[], None] | None = None,
    ):
        self.config = config
        self.server = server
        self.worker_id: str | None = None
        self._running = True
        self._current_tasks: dict[str, asyncio.Task[None]] = {}
        self._on_tasks_changed = on_tasks_changed

    async def start(self) -> None:
        """Register with the server and start poll + heartbeat loops.

        This is the main entry point. It blocks until stop() is called
        or a KeyboardInterrupt is received.
        """
        # Register worker
        result = await self.server.register_worker(
            hostname=socket.gethostname(),
            version=WORKER_VERSION,
            capabilities=["agent", "jira", "board_plan", "card_gen"],
        )
        self.worker_id = result["worker_id"]

        # Apply server-side config overrides
        if "poll_interval_seconds" in result:
            self.config.poll_interval = float(result["poll_interval_seconds"])
        if "max_concurrent_tasks" in result:
            self.config.max_concurrent_tasks = int(result["max_concurrent_tasks"])

        logger.info(
            "Worker registered: id=%s, hostname=%s",
            self.worker_id,
            socket.gethostname(),
        )

        # Run both loops concurrently
        try:
            await asyncio.gather(
                self._poll_loop(),
                self._heartbeat_loop(),
            )
        except asyncio.CancelledError:
            logger.info("Worker loops cancelled")

    async def stop(self) -> None:
        """Signal the worker to stop and cancel in-flight tasks."""
        self._running = False

        # Cancel all running task coroutines
        for task_id, async_task in self._current_tasks.items():
            logger.info("Cancelling task %s", task_id)
            async_task.cancel()

        # Wait for cancellation to complete
        if self._current_tasks:
            await asyncio.gather(
                *self._current_tasks.values(),
                return_exceptions=True,
            )
            self._current_tasks.clear()

    # --- Poll loop ---

    async def _poll_loop(self) -> None:
        """Poll the server for tasks and dispatch execution."""
        while self._running:
            try:
                # Clean up completed tasks
                self._cleanup_finished_tasks()

                # Only poll if we have capacity
                if len(self._current_tasks) < self.config.max_concurrent_tasks:
                    available_slots = self.config.max_concurrent_tasks - len(self._current_tasks)
                    tasks = await self.server.poll_tasks(self.worker_id, limit=available_slots)

                    for task_data in tasks:
                        task_id = task_data["id"]
                        if task_id not in self._current_tasks:
                            # Spawn execution as a background coroutine
                            async_task = asyncio.create_task(
                                self._execute_task(task_data),
                                name=f"task-{task_id}",
                            )
                            self._current_tasks[task_id] = async_task
                            self._notify_tasks_changed()

            except ServerError as e:
                logger.warning("Poll failed: %s", e.message)
            except Exception:
                logger.exception("Unexpected error in poll loop")

            await asyncio.sleep(self.config.poll_interval)

    def _cleanup_finished_tasks(self) -> None:
        """Remove completed/cancelled asyncio tasks from the tracking dict."""
        finished = [tid for tid, t in self._current_tasks.items() if t.done()]
        if not finished:
            return
        for tid in finished:
            task = self._current_tasks.pop(tid)
            # Log exceptions from tasks that failed unexpectedly
            if task.exception() is not None:
                logger.error(
                    "Task %s raised an unhandled exception: %s",
                    tid,
                    task.exception(),
                )
        self._notify_tasks_changed()

    def _notify_tasks_changed(self) -> None:
        """Notify the owner that the running task count changed."""
        if self._on_tasks_changed:
            self._on_tasks_changed()

    # --- Task execution ---

    async def _execute_task(self, task_data: dict[str, Any]) -> None:
        """Claim and execute a single task.

        Dispatches to the appropriate executor based on task_type.
        """
        task_id = task_data["id"]
        task_type = task_data.get("task_type", "")

        # Claim the task first
        try:
            await self.server.claim_task(task_id, self.worker_id)
        except ServerError as e:
            if e.status_code == 409:
                logger.debug("Task %s already claimed, skipping", task_id)
            else:
                logger.warning("Failed to claim task %s: %s", task_id, e.message)
            return

        logger.info("Claimed task %s (type=%s)", task_id, task_type)

        # Resolve workspace directory for the task's board
        working_dir = await self._resolve_workspace(task_data)

        # Route to the appropriate executor
        try:
            if task_type == "agent_run":
                await self._run_agent(task_data, working_dir=working_dir)
            elif task_type in ("board_plan", "card_gen"):
                await self._run_planner(task_data, working_dir=working_dir)
            elif task_type.startswith("jira_"):
                await self._run_jira(task_data)
            elif task_type.startswith("gitlab_"):
                await self._run_gitlab(task_data, working_dir=working_dir)
            else:
                await self.server.fail_task(
                    task_id,
                    self.worker_id,
                    error_summary=f"Unknown task type: {task_type}",
                )
        except asyncio.CancelledError:
            # Task was cancelled (e.g., worker shutdown or server directive)
            logger.info("Task %s was cancelled", task_id)
            try:
                await self.server.fail_task(
                    task_id,
                    self.worker_id,
                    error_summary="Task cancelled by worker",
                )
            except ServerError:
                logger.warning("Failed to report cancellation for task %s", task_id)
            raise
        except Exception:
            logger.exception("Unhandled error executing task %s", task_id)
            try:
                await self.server.fail_task(
                    task_id,
                    self.worker_id,
                    error_summary="Internal worker error",
                )
            except ServerError:
                logger.warning("Failed to report failure for task %s", task_id)

    async def _resolve_workspace(self, task_data: dict[str, Any]) -> Path | None:
        """Resolve workspace directory for a task's board."""
        board_id = task_data.get("board_id")
        if not board_id:
            return None
        try:
            from .workspace import WorkspaceResolver

            settings = await self.server.get_board_settings(board_id)
            resolver = WorkspaceResolver(self.config.workspace_root)
            return await resolver.resolve(settings)
        except Exception:
            logger.debug("Workspace resolution failed for board %s, using default", board_id)
            return None

    async def _run_agent(self, task_data: dict[str, Any], working_dir: Path | None = None) -> None:
        """Execute an agent task using kiro-cli."""
        from .executors.agent import AgentExecutor

        executor = AgentExecutor(self.config, self.server, self.worker_id)
        await executor.execute(task_data, working_dir=working_dir)

    async def _run_jira(self, task_data: dict[str, Any]) -> None:
        """Execute a Jira task using local credentials."""
        from .executors.jira import JiraExecutor

        executor = JiraExecutor(self.config, self.server, self.worker_id)
        await executor.execute(task_data)

    async def _run_gitlab(self, task_data: dict[str, Any], working_dir: Path | None = None) -> None:
        """Execute a GitLab task using local credentials."""
        from .executors.gitlab import GitLabExecutor

        executor = GitLabExecutor(self.config, self.server, self.worker_id)
        await executor.execute(task_data, working_dir=working_dir)

    async def _run_planner(
        self, task_data: dict[str, Any], working_dir: Path | None = None
    ) -> None:
        """Execute a board_plan task to decompose a prompt into board structure."""
        from .executors.planner import PlannerExecutor

        executor = PlannerExecutor(self.config, self.server, self.worker_id)
        await executor.execute(task_data, working_dir=working_dir)

    # --- Heartbeat loop ---

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats and handle server directives."""
        while self._running:
            try:
                running_ids = list(self._current_tasks.keys())
                result = await self.server.heartbeat(
                    self.worker_id,
                    running_ids,
                    system_load=self._get_system_load(),
                )

                # Handle cancel directives from the server
                directives = result.get("directives", {})
                cancel_ids = directives.get("cancel_task_ids", [])
                for task_id in cancel_ids:
                    if task_id in self._current_tasks:
                        logger.info("Server requested cancellation of task %s", task_id)
                        self._current_tasks[task_id].cancel()

                # Apply config updates from server
                if "max_concurrent_tasks" in directives:
                    self.config.max_concurrent_tasks = int(directives["max_concurrent_tasks"])

            except ServerError as e:
                logger.warning("Heartbeat failed: %s", e.message)
            except Exception:
                logger.exception("Unexpected error in heartbeat loop")

            await asyncio.sleep(self.config.heartbeat_interval)

    @staticmethod
    def _get_system_load() -> float:
        """Get current system load average (1-minute)."""
        try:
            return os.getloadavg()[0]
        except (OSError, AttributeError):
            return 0.0
