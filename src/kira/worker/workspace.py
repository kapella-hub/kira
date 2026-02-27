"""Workspace resolution for worker tasks.

Resolves a board's workspace path before task execution:
- Local path: validates existence, returns Path
- GitLab clone: clones or pulls repo into workspace_root/project-path
- No workspace: returns None (cwd defaults to worker's cwd)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceResolver:
    """Resolves workspace directories for task execution."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    async def resolve(self, board_settings: dict[str, Any] | None) -> Path | None:
        """Resolve the workspace path for a board.

        Checks board settings_json for:
        - workspace.local_path: path to existing directory
        - workspace.gitlab_project: project path to clone/pull

        Returns:
            Path to use as working directory, or None for default.
        """
        if not board_settings:
            return None

        workspace = board_settings.get("workspace")
        if not workspace:
            return None

        # Local path takes precedence
        local_path = workspace.get("local_path")
        if local_path:
            path = Path(local_path).expanduser().resolve()
            if path.is_dir():
                logger.info("Using local workspace: %s", path)
                return path
            else:
                logger.warning("Local workspace path does not exist: %s", path)
                return None

        # GitLab clone
        gitlab_project = workspace.get("gitlab_project")
        if gitlab_project:
            return await self._clone_or_pull(gitlab_project)

        return None

    async def _clone_or_pull(self, project_path: str) -> Path | None:
        """Clone a GitLab project or pull if already cloned.

        Clones into workspace_root/project-path (replacing / with -).
        """
        # Sanitize project path for directory name
        dir_name = project_path.replace("/", "-").replace("\\", "-")
        clone_dir = self.workspace_root / dir_name

        try:
            if clone_dir.exists() and (clone_dir / ".git").is_dir():
                # Pull latest
                logger.info("Pulling latest for %s in %s", project_path, clone_dir)
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "pull",
                    "--ff-only",
                    cwd=clone_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.warning(
                        "Git pull failed for %s: %s",
                        project_path,
                        stderr.decode().strip(),
                    )
                return clone_dir

            # Need GitLab config for clone URL
            from kira.integrations.gitlab.models import GitLabConfig

            config = GitLabConfig.load()
            if not config.is_configured():
                logger.warning("GitLab not configured, cannot clone %s", project_path)
                return None

            clone_url = f"{config.server.rstrip('/')}/{project_path}.git"

            logger.info("Cloning %s into %s", clone_url, clone_dir)
            clone_dir.parent.mkdir(parents=True, exist_ok=True)
            proc = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                clone_url,
                str(clone_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(
                    "Git clone failed for %s: %s",
                    project_path,
                    stderr.decode().strip(),
                )
                return None

            return clone_dir

        except Exception:
            logger.exception("Workspace resolution failed for %s", project_path)
            return None
