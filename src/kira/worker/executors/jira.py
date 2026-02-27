"""Jira executor -- runs Jira operations using local credentials.

This executor handles 'jira_import', 'jira_push', and 'jira_sync' tasks by:
  1. Loading Jira credentials from the local machine (~/.kira/jira.yaml or env vars).
  2. Executing the Jira operation via JiraClient.
  3. Creating cards on the server (for import) or reporting results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..client import ServerClient, ServerError
from ..config import WorkerConfig

logger = logging.getLogger(__name__)

# Map Jira priority names to Kira priority levels
_PRIORITY_MAP: dict[str, str] = {
    "Highest": "critical",
    "High": "high",
    "Medium": "medium",
    "Low": "low",
    "Lowest": "low",
}


class JiraExecutor:
    """Executes Jira tasks using local credentials."""

    def __init__(self, config: WorkerConfig, server: ServerClient, worker_id: str):
        self.config = config
        self.server = server
        self.worker_id = worker_id

    async def execute(self, task: dict[str, Any]) -> None:
        """Route to the appropriate Jira operation based on task_type.

        Args:
            task: Task dict from the server containing at minimum:
                - id: Task ID
                - task_type: 'jira_import', 'jira_push', or 'jira_sync'
                - payload_json: JSON string with operation-specific data
        """
        task_id = task["id"]
        task_type = task.get("task_type", "")

        try:
            payload = json.loads(task.get("payload_json", "{}"))
        except json.JSONDecodeError as e:
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=f"Invalid payload_json: {e}",
            )
            return

        try:
            if task_type == "jira_import":
                await self._import(task, payload)
            elif task_type == "jira_push":
                await self._push(task, payload)
            elif task_type == "jira_sync":
                await self._sync(task, payload)
            else:
                await self.server.fail_task(
                    task_id,
                    self.worker_id,
                    error_summary=f"Unknown Jira task type: {task_type}",
                )
        except Exception as e:
            logger.exception("Jira task %s failed", task_id)
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=str(e),
            )

    async def _import(self, task: dict[str, Any], payload: dict[str, Any]) -> None:
        """Import issues from Jira as cards on the board.

        Payload keys:
            jql: JQL query string
            column_id: Target column for imported cards
        """
        from kira.integrations.jira.client import JiraClient, JiraError
        from kira.integrations.jira.models import JiraConfig

        task_id = task["id"]
        jql = payload.get("jql", "")
        column_id = payload.get("column_id", "")

        if not jql:
            await self.server.fail_task(
                task_id, self.worker_id, error_summary="Missing 'jql' in payload"
            )
            return

        if not column_id:
            await self.server.fail_task(
                task_id, self.worker_id, error_summary="Missing 'column_id' in payload"
            )
            return

        # Report progress
        await self._report_progress(task_id, "Loading Jira credentials...")

        config = JiraConfig.load()
        jira = JiraClient(config)

        await self._report_progress(task_id, f"Searching Jira: {jql}")

        try:
            issues = jira.search_issues(jql)
        except JiraError as e:
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=f"Jira search failed: {e.message}",
            )
            return

        imported = 0
        skipped = 0

        for issue in issues:
            try:
                labels_json = json.dumps(issue.labels) if issue.labels else "[]"
                priority = _PRIORITY_MAP.get(issue.priority or "", "medium")

                await self.server.create_card(
                    column_id=column_id,
                    title=f"[{issue.key}] {issue.summary}",
                    description=issue.description or "",
                    priority=priority,
                    labels=labels_json,
                )
                imported += 1
            except ServerError as e:
                logger.warning("Failed to create card for %s: %s", issue.key, e.message)
                skipped += 1

            # Report progress periodically
            if (imported + skipped) % 5 == 0:
                await self._report_progress(
                    task_id,
                    f"Imported {imported}/{len(issues)} issues...",
                )

        result_text = f"Imported {imported} issues from Jira"
        if skipped:
            result_text += f" ({skipped} skipped due to errors)"

        logger.info("Task %s: %s", task_id, result_text)

        await self.server.complete_task(
            task_id,
            self.worker_id,
            output_text=result_text,
            result_data={"imported": imported, "skipped": skipped},
        )

    async def _push(self, task: dict[str, Any], payload: dict[str, Any]) -> None:
        """Push a card to Jira as a new issue.

        Payload keys:
            card_title: Card title
            card_description: Card description
            project: Jira project key (optional, uses default)
            issue_type: Jira issue type (optional, defaults to Task)
        """
        from kira.integrations.jira.client import JiraClient, JiraError
        from kira.integrations.jira.models import JiraConfig

        task_id = task["id"]

        card_title = payload.get("card_title", "")
        if not card_title:
            await self.server.fail_task(
                task_id, self.worker_id, error_summary="Missing 'card_title' in payload"
            )
            return

        await self._report_progress(task_id, "Pushing to Jira...")

        config = JiraConfig.load()
        jira = JiraClient(config)

        try:
            issue = jira.create_issue(
                summary=card_title,
                description=payload.get("card_description", ""),
                project=payload.get("project"),
                issue_type=payload.get("issue_type", "Task"),
                labels=payload.get("labels"),
            )
        except JiraError as e:
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=f"Jira push failed: {e.message}",
            )
            return

        result_text = f"Created Jira issue: {issue.key}"
        if issue.browse_url:
            result_text += f"\n{issue.browse_url}"

        logger.info("Task %s: created %s", task_id, issue.key)

        await self.server.complete_task(
            task_id,
            self.worker_id,
            output_text=result_text,
            result_data={"issue_key": issue.key, "browse_url": issue.browse_url},
        )

    async def _sync(self, task: dict[str, Any], payload: dict[str, Any]) -> None:
        """Sync a board with Jira (refresh statuses).

        Payload keys:
            jql: JQL query for issues to sync
            board_id: Board ID to sync with

        This is a placeholder for future implementation.
        For now, it reports completion with a summary.
        """
        task_id = task["id"]

        await self._report_progress(task_id, "Jira sync started...")

        # TODO: Implement full sync logic (fetch Jira statuses, update cards)
        await self.server.complete_task(
            task_id,
            self.worker_id,
            output_text="Jira sync is not yet fully implemented",
            result_data={"synced": 0},
        )

    async def _report_progress(self, task_id: str, text: str) -> None:
        """Report progress, swallowing errors to avoid interrupting execution."""
        try:
            await self.server.report_progress(task_id, self.worker_id, text)
        except ServerError as e:
            logger.debug("Progress report failed for task %s: %s", task_id, e.message)
