"""Tests for GitLab executor."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kira.worker.config import WorkerConfig
from kira.worker.executors.gitlab import GitLabExecutor, _slugify


@pytest.fixture
def config():
    return WorkerConfig(kiro_timeout=10)


@pytest.fixture
def mock_server():
    server = AsyncMock()
    server.report_progress.return_value = {"status": "ok"}
    server.complete_task.return_value = {"status": "completed"}
    server.fail_task.return_value = {"status": "failed"}
    return server


@pytest.fixture
def mock_gitlab_modules():
    """Mock the GitLab integration modules to prevent import issues."""
    mock_gitlab_client_module = MagicMock()
    mock_gitlab_models_module = MagicMock()
    mock_integrations_module = MagicMock()
    mock_integrations_gitlab_module = MagicMock()

    saved = {}
    modules_to_mock = {
        "kira.integrations": mock_integrations_module,
        "kira.integrations.gitlab": mock_integrations_gitlab_module,
        "kira.integrations.gitlab.client": mock_gitlab_client_module,
        "kira.integrations.gitlab.models": mock_gitlab_models_module,
    }

    for mod_name, mock_mod in modules_to_mock.items():
        if mod_name in sys.modules:
            saved[mod_name] = sys.modules[mod_name]
        sys.modules[mod_name] = mock_mod

    yield {
        "client_module": mock_gitlab_client_module,
        "models_module": mock_gitlab_models_module,
    }

    for mod_name in modules_to_mock:
        if mod_name in saved:
            sys.modules[mod_name] = saved[mod_name]
        else:
            sys.modules.pop(mod_name, None)


# --- Slugify Tests ---


class TestSlugify:
    def test_basic_slugify(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_characters(self):
        assert _slugify("feat: Build REST API!") == "feat-build-rest-api"

    def test_truncation(self):
        result = _slugify("a" * 100)
        assert len(result) <= 50

    def test_strips_leading_trailing_hyphens(self):
        assert _slugify("--hello--") == "hello"


# --- Create Project Tests ---


class TestGitLabCreateProject:
    @pytest.mark.asyncio
    async def test_creates_project_successfully(self, config, mock_server, mock_gitlab_modules):
        task = {
            "id": "t-gl-create",
            "task_type": "gitlab_create_project",
            "payload_json": json.dumps({
                "name": "my-new-project",
                "visibility": "private",
                "description": "A test project",
            }),
        }

        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        mock_config.server = "https://gitlab.example.com"
        mock_config.token = "glpat-abc123"
        mock_gitlab_modules["models_module"].GitLabConfig.load.return_value = mock_config

        mock_client = MagicMock()
        mock_client.create_project.return_value = {
            "id": 42,
            "path_with_namespace": "user/my-new-project",
            "web_url": "https://gitlab.example.com/user/my-new-project",
            "default_branch": "main",
        }
        mock_gitlab_modules["client_module"].GitLabClient.return_value = mock_client
        mock_gitlab_modules["client_module"].GitLabError = Exception

        executor = GitLabExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_client.create_project.assert_called_once_with(
            name="my-new-project",
            namespace_id=None,
            visibility="private",
            description="A test project",
        )

        mock_server.complete_task.assert_called_once()
        complete_kwargs = mock_server.complete_task.call_args.kwargs
        assert "my-new-project" in complete_kwargs["output_text"]
        assert complete_kwargs["result_data"]["project_id"] == 42

    @pytest.mark.asyncio
    async def test_fails_on_missing_name(self, config, mock_server):
        task = {
            "id": "t-gl-no-name",
            "task_type": "gitlab_create_project",
            "payload_json": json.dumps({"visibility": "private"}),
        }

        executor = GitLabExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "name" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()

    @pytest.mark.asyncio
    async def test_fails_on_unconfigured_credentials(
        self, config, mock_server, mock_gitlab_modules
    ):
        task = {
            "id": "t-gl-noconfig",
            "task_type": "gitlab_create_project",
            "payload_json": json.dumps({"name": "test"}),
        }

        mock_config = MagicMock()
        mock_config.is_configured.return_value = False
        mock_gitlab_modules["models_module"].GitLabConfig.load.return_value = mock_config
        mock_gitlab_modules["client_module"].GitLabError = Exception

        executor = GitLabExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "not configured" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()

    @pytest.mark.asyncio
    async def test_fails_on_invalid_json(self, config, mock_server):
        task = {
            "id": "t-gl-bad-json",
            "task_type": "gitlab_create_project",
            "payload_json": "not valid json {{{",
        }

        executor = GitLabExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "invalid" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()


# --- Push Tests ---


class TestGitLabPush:
    @pytest.mark.asyncio
    async def test_push_and_create_mr(self, config, mock_server, mock_gitlab_modules):
        task = {
            "id": "t-gl-push",
            "task_type": "gitlab_push",
            "card_id": "card-abc12345",
            "payload_json": json.dumps({
                "project_id": 42,
                "project_path": "group/my-project",
                "default_branch": "main",
                "mr_prefix": "kira/",
                "card_title": "Build REST API",
                "commit_message": "feat: Build REST API",
                "create_mr": True,
                "mr_title": "Build REST API",
            }),
        }

        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        mock_config.server = "https://gitlab.example.com"
        mock_config.token = "glpat-abc123"
        mock_gitlab_modules["models_module"].GitLabConfig.load.return_value = mock_config

        mock_client = MagicMock()
        mock_client.create_merge_request.return_value = {
            "iid": 1,
            "web_url": "https://gitlab.example.com/group/my-project/-/merge_requests/1",
        }
        mock_gitlab_modules["client_module"].GitLabClient.return_value = mock_client
        mock_gitlab_modules["client_module"].GitLabError = Exception

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            executor = GitLabExecutor(config, mock_server, "w-1")
            await executor.execute(task)

        # Should have run 4 git commands
        assert mock_run.call_count == 4
        git_calls = [call.args[0] for call in mock_run.call_args_list]
        assert git_calls[0][0] == "git"
        assert "checkout" in git_calls[0]
        assert "add" in git_calls[1]
        assert "commit" in git_calls[2]
        assert "push" in git_calls[3]

        # Should have created MR
        mock_client.create_merge_request.assert_called_once()
        mr_call_kwargs = mock_client.create_merge_request.call_args.kwargs
        assert mr_call_kwargs["project_id"] == 42
        assert mr_call_kwargs["target_branch"] == "main"

        # Should have completed
        mock_server.complete_task.assert_called_once()
        complete_kwargs = mock_server.complete_task.call_args.kwargs
        assert "merge_requests/1" in complete_kwargs["output_text"]
        assert complete_kwargs["result_data"]["mr_iid"] == 1

    @pytest.mark.asyncio
    async def test_push_without_mr(self, config, mock_server, mock_gitlab_modules):
        task = {
            "id": "t-gl-push-nomr",
            "task_type": "gitlab_push",
            "card_id": "card-abc12345",
            "payload_json": json.dumps({
                "project_id": 42,
                "default_branch": "main",
                "card_title": "Quick fix",
                "create_mr": False,
            }),
        }

        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        mock_config.server = "https://gitlab.example.com"
        mock_config.token = "glpat-abc123"
        mock_gitlab_modules["models_module"].GitLabConfig.load.return_value = mock_config
        mock_gitlab_modules["client_module"].GitLabError = Exception

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            executor = GitLabExecutor(config, mock_server, "w-1")
            await executor.execute(task)

        # Should have completed without creating MR
        mock_server.complete_task.assert_called_once()
        complete_kwargs = mock_server.complete_task.call_args.kwargs
        assert "merge_request" not in complete_kwargs["output_text"].lower()

    @pytest.mark.asyncio
    async def test_push_fails_on_git_error(self, config, mock_server, mock_gitlab_modules):
        import subprocess

        task = {
            "id": "t-gl-push-fail",
            "task_type": "gitlab_push",
            "card_id": "card-abc12345",
            "payload_json": json.dumps({
                "project_id": 42,
                "card_title": "Bad push",
            }),
        }

        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        mock_config.server = "https://gitlab.example.com"
        mock_config.token = "glpat-abc123"
        mock_gitlab_modules["models_module"].GitLabConfig.load.return_value = mock_config
        mock_gitlab_modules["client_module"].GitLabError = Exception

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git", stderr="fatal: not a git repository"
            )

            executor = GitLabExecutor(config, mock_server, "w-1")
            await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "git" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()

    @pytest.mark.asyncio
    async def test_push_fails_on_missing_project_id(self, config, mock_server):
        task = {
            "id": "t-gl-push-noid",
            "task_type": "gitlab_push",
            "payload_json": json.dumps({"card_title": "Test"}),
        }

        executor = GitLabExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "project_id" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()


# --- Unknown Task Type ---


class TestGitLabUnknownType:
    @pytest.mark.asyncio
    async def test_fails_on_unknown_gitlab_type(self, config, mock_server):
        task = {
            "id": "t-gl-unknown",
            "task_type": "gitlab_teleport",
            "payload_json": "{}",
        }

        executor = GitLabExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "Unknown" in mock_server.fail_task.call_args.kwargs["error_summary"]
