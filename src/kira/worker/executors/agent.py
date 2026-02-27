"""Agent executor -- runs kiro-cli via KiraClient and reports results.

This executor handles 'agent_run' tasks by:
  1. Reporting initial progress to the server.
  2. Creating a KiraClient with the task's model and agent settings.
  3. Streaming kiro-cli output, reporting progress periodically.
  4. Reporting completion or failure.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..client import ServerClient, ServerError
from ..config import WorkerConfig

logger = logging.getLogger(__name__)

# Report progress every N chunks to avoid flooding the server
PROGRESS_REPORT_INTERVAL = 20


class AgentExecutor:
    """Executes agent tasks using kiro-cli."""

    def __init__(self, config: WorkerConfig, server: ServerClient, worker_id: str):
        self.config = config
        self.server = server
        self.worker_id = worker_id

    async def execute(self, task: dict[str, Any], working_dir: Path | None = None) -> None:
        """Run kiro-cli with the task prompt and report results.

        Args:
            task: Task dict from the server containing at minimum:
                - id: Task ID
                - prompt_text: The prompt to send to kiro-cli
                - agent_type: Agent type name (e.g., 'architect', 'coder')
                - agent_model: Model alias or name (e.g., 'smart', 'opus')
                - agent_skill: Optional skill name
            working_dir: Optional working directory for kiro-cli subprocess.
        """
        task_id = task["id"]
        agent_type = task.get("agent_type", "general")
        prompt_text = task.get("prompt_text", "")

        if not prompt_text:
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary="Task has no prompt_text",
            )
            return

        output_chunks: list[str] = []

        try:
            # Report progress: starting
            await self._report_progress(
                task_id,
                f"Starting {agent_type} agent...",
            )

            # Create KiraClient with task settings
            from kira.core.client import KiraClient
            from kira.core.models import resolve_model

            model = resolve_model(task.get("agent_model", "smart"))
            agent_skill = task.get("agent_skill") or None

            client = KiraClient(
                agent=agent_skill,
                model=model,
                trust_all_tools=True,
                timeout=self.config.kiro_timeout,
                working_dir=working_dir,
            )

            # Stream kiro-cli output
            chunk_count = 0
            async for chunk in client.run(prompt_text):
                output_chunks.append(chunk)
                chunk_count += 1

                # Report progress periodically
                if chunk_count % PROGRESS_REPORT_INTERVAL == 0:
                    await self._report_progress(
                        task_id,
                        f"Running {agent_type}... ({chunk_count} chunks)",
                    )

            output = "".join(output_chunks)

            logger.info(
                "Task %s completed: agent=%s, output_length=%d",
                task_id,
                agent_type,
                len(output),
            )

            # Report completion
            await self.server.complete_task(
                task_id,
                self.worker_id,
                output_text=output,
            )

        except Exception as e:
            partial_output = "".join(output_chunks) if output_chunks else ""
            error_msg = str(e)

            logger.error(
                "Task %s failed: agent=%s, error=%s",
                task_id,
                agent_type,
                error_msg,
            )

            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=error_msg,
                output_text=partial_output,
            )

    async def _report_progress(self, task_id: str, text: str) -> None:
        """Report progress, swallowing errors to avoid interrupting execution."""
        try:
            await self.server.report_progress(task_id, self.worker_id, text)
        except ServerError as e:
            logger.debug("Progress report failed for task %s: %s", task_id, e.message)
