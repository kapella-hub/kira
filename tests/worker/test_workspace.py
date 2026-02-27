"""Tests for WorkspaceResolver."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kira.worker.workspace import WorkspaceResolver


@pytest.fixture
def workspace_root(tmp_path):
    """Create a temporary workspace root directory."""
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


class TestResolveNone:
    """Resolver returns None when no workspace is configured."""

    @pytest.mark.asyncio
    async def test_returns_none_for_none_settings(self, workspace_root):
        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_settings(self, workspace_root):
        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve({})
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_no_workspace_key(self, workspace_root):
        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve({"gitlab": {"project": "foo"}})
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_workspace(self, workspace_root):
        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve({"workspace": {}})
        assert result is None


class TestResolveLocalPath:
    """Resolver handles local_path workspace settings."""

    @pytest.mark.asyncio
    async def test_returns_existing_local_path(self, workspace_root, tmp_path):
        local_dir = tmp_path / "my-project"
        local_dir.mkdir()

        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve({"workspace": {"local_path": str(local_dir)}})
        assert result == local_dir.resolve()

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_local_path(self, workspace_root):
        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve(
            {"workspace": {"local_path": "/nonexistent/path/that/does/not/exist"}}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_expands_tilde_in_local_path(self, workspace_root, tmp_path, monkeypatch):
        # Create a dir that simulates ~/my-project
        home_dir = tmp_path / "fake_home"
        home_dir.mkdir()
        project_dir = home_dir / "my-project"
        project_dir.mkdir()

        monkeypatch.setenv("HOME", str(home_dir))

        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve({"workspace": {"local_path": "~/my-project"}})
        assert result == project_dir.resolve()

    @pytest.mark.asyncio
    async def test_local_path_takes_precedence_over_gitlab(self, workspace_root, tmp_path):
        """When both local_path and gitlab_project are set, local_path wins."""
        local_dir = tmp_path / "my-project"
        local_dir.mkdir()

        resolver = WorkspaceResolver(workspace_root)
        result = await resolver.resolve(
            {
                "workspace": {
                    "local_path": str(local_dir),
                    "gitlab_project": "group/project",
                }
            }
        )
        assert result == local_dir.resolve()


class TestResolveGitLabClone:
    """Resolver handles gitlab_project workspace settings."""

    @pytest.mark.asyncio
    async def test_clones_new_project(self, workspace_root):
        """Should clone when directory doesn't exist."""
        mock_gitlab_modules = MagicMock()
        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        mock_config.server = "https://gitlab.example.com"
        mock_gitlab_modules.GitLabConfig.load.return_value = mock_config

        with (
            patch.dict(
                sys.modules,
                {"kira.integrations.gitlab.models": mock_gitlab_modules},
            ),
            patch("asyncio.create_subprocess_exec") as mock_exec,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            resolver = WorkspaceResolver(workspace_root)
            result = await resolver.resolve({"workspace": {"gitlab_project": "group/my-project"}})

        expected_dir = workspace_root / "group-my-project"
        assert result == expected_dir

        # Verify clone was called with the right URL
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        assert call_args.args[0] == "git"
        assert call_args.args[1] == "clone"
        assert "https://gitlab.example.com/group/my-project.git" in call_args.args[2]

    @pytest.mark.asyncio
    async def test_pulls_existing_clone(self, workspace_root):
        """Should pull when directory already exists with .git."""
        clone_dir = workspace_root / "group-my-project"
        clone_dir.mkdir(parents=True)
        (clone_dir / ".git").mkdir()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"Already up to date.\n", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            resolver = WorkspaceResolver(workspace_root)
            result = await resolver.resolve({"workspace": {"gitlab_project": "group/my-project"}})

        assert result == clone_dir

        # Verify pull was called (not clone)
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        assert call_args.args[0] == "git"
        assert call_args.args[1] == "pull"
        assert call_args.kwargs.get("cwd") == clone_dir

    @pytest.mark.asyncio
    async def test_returns_clone_dir_even_if_pull_fails(self, workspace_root):
        """Pull failure should still return the clone directory."""
        clone_dir = workspace_root / "group-my-project"
        clone_dir.mkdir(parents=True)
        (clone_dir / ".git").mkdir()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"error: merge conflict\n")
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            resolver = WorkspaceResolver(workspace_root)
            result = await resolver.resolve({"workspace": {"gitlab_project": "group/my-project"}})

        # Still returns the dir even though pull failed
        assert result == clone_dir

    @pytest.mark.asyncio
    async def test_returns_none_if_clone_fails(self, workspace_root):
        """Should return None when clone fails."""
        mock_gitlab_modules = MagicMock()
        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        mock_config.server = "https://gitlab.example.com"
        mock_gitlab_modules.GitLabConfig.load.return_value = mock_config

        with (
            patch.dict(
                sys.modules,
                {"kira.integrations.gitlab.models": mock_gitlab_modules},
            ),
            patch("asyncio.create_subprocess_exec") as mock_exec,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"",
                b"fatal: repository not found\n",
            )
            mock_proc.returncode = 128
            mock_exec.return_value = mock_proc

            resolver = WorkspaceResolver(workspace_root)
            result = await resolver.resolve({"workspace": {"gitlab_project": "group/missing"}})

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_if_gitlab_not_configured(self, workspace_root):
        """Should return None when GitLab credentials are not set."""
        mock_gitlab_modules = MagicMock()
        mock_config = MagicMock()
        mock_config.is_configured.return_value = False
        mock_gitlab_modules.GitLabConfig.load.return_value = mock_config

        with patch.dict(
            sys.modules,
            {"kira.integrations.gitlab.models": mock_gitlab_modules},
        ):
            resolver = WorkspaceResolver(workspace_root)
            result = await resolver.resolve({"workspace": {"gitlab_project": "group/my-project"}})

        assert result is None

    @pytest.mark.asyncio
    async def test_sanitizes_project_path_for_directory_name(self, workspace_root):
        """Slashes in project path should be replaced with hyphens."""
        mock_gitlab_modules = MagicMock()
        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        mock_config.server = "https://gitlab.example.com"
        mock_gitlab_modules.GitLabConfig.load.return_value = mock_config

        with (
            patch.dict(
                sys.modules,
                {"kira.integrations.gitlab.models": mock_gitlab_modules},
            ),
            patch("asyncio.create_subprocess_exec") as mock_exec,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            resolver = WorkspaceResolver(workspace_root)
            result = await resolver.resolve(
                {"workspace": {"gitlab_project": "deep/nested/project"}}
            )

        expected_dir = workspace_root / "deep-nested-project"
        assert result == expected_dir

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, workspace_root):
        """Unexpected exceptions should be caught and return None."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = OSError("git not found")

            # Create the .git dir so it tries to pull (not clone, which needs GitLab import)
            clone_dir = workspace_root / "group-project"
            clone_dir.mkdir()
            (clone_dir / ".git").mkdir()

            resolver = WorkspaceResolver(workspace_root)
            result = await resolver.resolve({"workspace": {"gitlab_project": "group/project"}})

        assert result is None
