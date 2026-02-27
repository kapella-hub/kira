"""GitLab executor -- runs GitLab operations using local credentials.

This executor handles 'gitlab_create_project' and 'gitlab_push' tasks by:
  1. Loading GitLab credentials from the local machine (~/.kira/gitlab.yaml or env vars).
  2. Executing the GitLab operation via GitLabClient.
  3. Reporting results to the server.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from ..client import ServerClient, ServerError
from ..config import WorkerConfig

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug suitable for branch names."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


class GitLabExecutor:
    """Executes GitLab tasks using local credentials."""

    def __init__(self, config: WorkerConfig, server: ServerClient, worker_id: str):
        self.config = config
        self.server = server
        self.worker_id = worker_id

    async def execute(self, task: dict[str, Any], working_dir: Path | None = None) -> None:
        """Route to the appropriate GitLab operation based on task_type.

        Args:
            task: Task dict from the server containing at minimum:
                - id: Task ID
                - task_type: 'gitlab_create_project' or 'gitlab_push'
                - payload_json: JSON string with operation-specific data
            working_dir: Optional working directory for git subprocess calls.
        """
        self._working_dir = working_dir
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
            if task_type == "gitlab_create_project":
                await self._create_project(task, payload)
            elif task_type == "gitlab_push":
                await self._push(task, payload)
            else:
                await self.server.fail_task(
                    task_id,
                    self.worker_id,
                    error_summary=f"Unknown GitLab task type: {task_type}",
                )
        except Exception as e:
            logger.exception("GitLab task %s failed", task_id)
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=str(e),
            )

    async def _create_project(self, task: dict[str, Any], payload: dict[str, Any]) -> None:
        """Create a new GitLab project.

        Payload keys:
            name: Project name
            namespace_id: Namespace/group ID (optional)
            visibility: private/internal/public
            description: Project description
            board_id: Board to link the project to
            auto_push: Whether to enable auto-push
        """
        from kira.integrations.gitlab.client import GitLabClient, GitLabError
        from kira.integrations.gitlab.models import GitLabConfig

        task_id = task["id"]
        name = payload.get("name", "")

        if not name:
            await self.server.fail_task(
                task_id, self.worker_id, error_summary="Missing 'name' in payload"
            )
            return

        await self._report_progress(task_id, "Loading GitLab credentials...")

        config = GitLabConfig.load()
        if not config.is_configured():
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary="GitLab not configured. Set GITLAB_SERVER and GITLAB_TOKEN.",
            )
            return

        gitlab = GitLabClient(config.server, config.token)

        await self._report_progress(task_id, f"Creating project: {name}")

        try:
            project = gitlab.create_project(
                name=name,
                namespace_id=payload.get("namespace_id"),
                visibility=payload.get("visibility", "private"),
                description=payload.get("description", ""),
            )
        except GitLabError as e:
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=f"GitLab project creation failed: {e.message}",
            )
            return

        result_text = f"Created GitLab project: {project.get('path_with_namespace', name)}"
        web_url = project.get("web_url", "")
        if web_url:
            result_text += f"\n{web_url}"

        logger.info("Task %s: created project %s", task_id, project.get("path_with_namespace"))

        await self.server.complete_task(
            task_id,
            self.worker_id,
            output_text=result_text,
            result_data={
                "project_id": project.get("id"),
                "path_with_namespace": project.get("path_with_namespace", ""),
                "web_url": web_url,
                "default_branch": project.get("default_branch", "main"),
            },
        )

    async def _push(self, task: dict[str, Any], payload: dict[str, Any]) -> None:
        """Push changes to GitLab and optionally create a merge request.

        Payload keys:
            project_id: GitLab project ID
            project_path: Project path_with_namespace
            default_branch: Target branch for MR (default: main)
            mr_prefix: Branch name prefix (default: kira/)
            card_title: Card title for branch naming
            branch_name: Explicit branch name (optional)
            commit_message: Git commit message
            create_mr: Whether to create a merge request
            mr_title: MR title
        """
        from kira.integrations.gitlab.client import GitLabClient, GitLabError
        from kira.integrations.gitlab.models import GitLabConfig

        task_id = task["id"]
        project_id = payload.get("project_id")

        if not project_id:
            await self.server.fail_task(
                task_id, self.worker_id, error_summary="Missing 'project_id' in payload"
            )
            return

        await self._report_progress(task_id, "Loading GitLab credentials...")

        config = GitLabConfig.load()
        if not config.is_configured():
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary="GitLab not configured. Set GITLAB_SERVER and GITLAB_TOKEN.",
            )
            return

        # Build branch name
        card_title = payload.get("card_title", "changes")
        card_id_short = task.get("card_id", "unknown")[:8]
        mr_prefix = payload.get("mr_prefix", "kira/")
        branch_name = payload.get("branch_name") or (
            f"{mr_prefix}{card_id_short}-{_slugify(card_title)}"
        )
        default_branch = payload.get("default_branch", "main")
        commit_message = payload.get("commit_message", f"feat: {card_title}")
        create_mr = payload.get("create_mr", True)
        mr_title = payload.get("mr_title", card_title)

        # Git operations
        await self._report_progress(task_id, f"Creating branch: {branch_name}")

        git_cwd = str(self._working_dir) if self._working_dir else None

        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                check=True,
                capture_output=True,
                text=True,
                cwd=git_cwd,
            )
            subprocess.run(
                ["git", "add", "-A"],
                check=True,
                capture_output=True,
                text=True,
                cwd=git_cwd,
            )
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                check=True,
                capture_output=True,
                text=True,
                cwd=git_cwd,
            )

            await self._report_progress(task_id, "Pushing to GitLab...")

            subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                check=True,
                capture_output=True,
                text=True,
                cwd=git_cwd,
            )
        except subprocess.CalledProcessError as e:
            error_output = e.stderr or e.stdout or str(e)
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=f"Git operation failed: {error_output}",
            )
            return

        result_text = f"Pushed branch `{branch_name}` to GitLab"
        result_data: dict[str, Any] = {"branch_name": branch_name}

        # Create merge request if requested
        if create_mr:
            await self._report_progress(task_id, "Creating merge request...")

            gitlab = GitLabClient(config.server, config.token)
            try:
                mr = gitlab.create_merge_request(
                    project_id=project_id,
                    source_branch=branch_name,
                    target_branch=default_branch,
                    title=mr_title,
                    description=f"Changes from Kira card {task.get('card_id', 'unknown')}",
                )
                mr_url = mr.get("web_url", "")
                result_text += f"\nMerge request: {mr_url}"
                result_data["mr_url"] = mr_url
                result_data["mr_iid"] = mr.get("iid")
            except GitLabError as e:
                # MR creation failed but push succeeded -- report partial success
                result_text += f"\nMerge request creation failed: {e.message}"
                result_data["mr_error"] = e.message

        logger.info("Task %s: %s", task_id, result_text)

        await self.server.complete_task(
            task_id,
            self.worker_id,
            output_text=result_text,
            result_data=result_data,
        )

    async def _report_progress(self, task_id: str, text: str) -> None:
        """Report progress, swallowing errors to avoid interrupting execution."""
        try:
            await self.server.report_progress(task_id, self.worker_id, text)
        except ServerError as e:
            logger.debug("Progress report failed for task %s: %s", task_id, e.message)
