"""Tests for agent and Jira executors."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from kira.worker.config import WorkerConfig
from kira.worker.executors.agent import AgentExecutor
from kira.worker.executors.jira import JiraExecutor


@pytest.fixture
def config():
    return WorkerConfig(kiro_timeout=10)


@pytest.fixture
def mock_server():
    server = AsyncMock()
    server.report_progress.return_value = {"status": "ok"}
    server.complete_task.return_value = {"status": "completed"}
    server.fail_task.return_value = {"status": "failed"}
    server.create_card.return_value = {"id": "card-new"}
    return server


def _make_fake_kira_client(chunks):
    """Create a mock KiraClient that yields the given chunks."""
    mock_client = MagicMock()

    async def fake_run(prompt, **kwargs):
        for chunk in chunks:
            yield chunk

    mock_client.run = fake_run
    return mock_client


@pytest.fixture
def mock_kira_core():
    """Mock kira.core.client and kira.core.models for agent executor tests.

    The agent executor uses lazy imports:
        from kira.core.client import KiraClient
        from kira.core.models import resolve_model

    We mock these at sys.modules level to intercept the imports cleanly.
    """
    mock_client_mod = MagicMock()
    mock_models_mod = MagicMock()

    saved = {}
    modules = {
        "kira.core": MagicMock(),
        "kira.core.client": mock_client_mod,
        "kira.core.models": mock_models_mod,
    }

    for name, mod in modules.items():
        if name in sys.modules:
            saved[name] = sys.modules[name]
        sys.modules[name] = mod

    yield {"client_module": mock_client_mod, "models_module": mock_models_mod}

    for name in modules:
        if name in saved:
            sys.modules[name] = saved[name]
        else:
            sys.modules.pop(name, None)


@pytest.fixture
def mock_jira_modules():
    """Mock the Jira integration modules to prevent import issues.

    The kira.integrations.__init__ tries to import chalk which doesn't exist.
    """
    mock_jira_client_module = MagicMock()
    mock_jira_models_module = MagicMock()
    mock_integrations_module = MagicMock()
    mock_integrations_jira_module = MagicMock()

    saved = {}
    modules_to_mock = {
        "kira.integrations": mock_integrations_module,
        "kira.integrations.jira": mock_integrations_jira_module,
        "kira.integrations.jira.client": mock_jira_client_module,
        "kira.integrations.jira.models": mock_jira_models_module,
    }

    for mod_name, mock_mod in modules_to_mock.items():
        if mod_name in sys.modules:
            saved[mod_name] = sys.modules[mod_name]
        sys.modules[mod_name] = mock_mod

    yield {
        "client_module": mock_jira_client_module,
        "models_module": mock_jira_models_module,
    }

    for mod_name in modules_to_mock:
        if mod_name in saved:
            sys.modules[mod_name] = saved[mod_name]
        else:
            sys.modules.pop(mod_name, None)


# --- Agent Executor Tests ---


class TestAgentExecutorHappyPath:
    @pytest.mark.asyncio
    async def test_executes_prompt_and_reports_completion(
        self, config, mock_server, mock_kira_core
    ):
        task = {
            "id": "t-1",
            "task_type": "agent_run",
            "agent_type": "coder",
            "agent_model": "smart",
            "agent_skill": "",
            "prompt_text": "Write a hello world function",
        }

        mock_client = _make_fake_kira_client(["def hello():\n", "    print('Hello, world!')\n"])
        mock_kira_core["client_module"].KiraClient.return_value = mock_client
        mock_kira_core["models_module"].resolve_model.return_value = "claude-sonnet-4"

        executor = AgentExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        # Should have reported progress at the start
        mock_server.report_progress.assert_called()

        # Should have completed with the output
        mock_server.complete_task.assert_called_once()
        call_kwargs = mock_server.complete_task.call_args.kwargs
        assert "hello" in call_kwargs["output_text"].lower()


class TestAgentExecutorEmptyPrompt:
    @pytest.mark.asyncio
    async def test_fails_with_empty_prompt(self, config, mock_server):
        task = {
            "id": "t-empty",
            "task_type": "agent_run",
            "agent_type": "coder",
            "prompt_text": "",
        }

        executor = AgentExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        mock_server.complete_task.assert_not_called()
        assert "no prompt_text" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()


class TestAgentExecutorKiroFailure:
    @pytest.mark.asyncio
    async def test_reports_failure_on_kiro_error(self, config, mock_server, mock_kira_core):
        task = {
            "id": "t-fail",
            "task_type": "agent_run",
            "agent_type": "coder",
            "agent_model": "smart",
            "prompt_text": "Do something",
        }

        mock_client = MagicMock()

        async def failing_run(prompt, **kwargs):
            yield "partial output\n"
            raise RuntimeError("kiro-cli crashed")

        mock_client.run = failing_run
        mock_kira_core["client_module"].KiraClient.return_value = mock_client
        mock_kira_core["models_module"].resolve_model.return_value = "claude-sonnet-4"

        executor = AgentExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        call_kwargs = mock_server.fail_task.call_args.kwargs
        assert "crashed" in call_kwargs["error_summary"]
        assert "partial output" in call_kwargs["output_text"]


class TestAgentExecutorProgressReporting:
    @pytest.mark.asyncio
    async def test_reports_progress_periodically(self, config, mock_server, mock_kira_core):
        task = {
            "id": "t-progress",
            "task_type": "agent_run",
            "agent_type": "coder",
            "agent_model": "smart",
            "prompt_text": "Generate lots of code",
        }

        chunks = [f"line {i}\n" for i in range(25)]
        mock_client = _make_fake_kira_client(chunks)
        mock_kira_core["client_module"].KiraClient.return_value = mock_client
        mock_kira_core["models_module"].resolve_model.return_value = "claude-sonnet-4"

        executor = AgentExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        # Should have reported progress: 1 initial + at least 1 periodic (at chunk 20)
        assert mock_server.report_progress.call_count >= 2


# --- Jira Executor Tests ---


class TestJiraExecutorImport:
    @pytest.mark.asyncio
    async def test_imports_issues_as_cards(self, config, mock_server, mock_jira_modules):
        task = {
            "id": "t-jira-import",
            "task_type": "jira_import",
            "payload_json": json.dumps(
                {
                    "jql": "project = TEST",
                    "column_id": "col-backlog",
                }
            ),
        }

        mock_issue_1 = MagicMock()
        mock_issue_1.key = "TEST-1"
        mock_issue_1.summary = "First issue"
        mock_issue_1.description = "Description of first"
        mock_issue_1.labels = ["backend"]
        mock_issue_1.priority = "High"

        mock_issue_2 = MagicMock()
        mock_issue_2.key = "TEST-2"
        mock_issue_2.summary = "Second issue"
        mock_issue_2.description = ""
        mock_issue_2.labels = []
        mock_issue_2.priority = "Low"

        mock_jira = MagicMock()
        mock_jira.search_issues.return_value = [mock_issue_1, mock_issue_2]

        mock_jira_modules["client_module"].JiraClient.return_value = mock_jira
        mock_jira_modules["client_module"].JiraError = Exception
        mock_jira_modules["models_module"].JiraConfig.load.return_value = MagicMock()

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        # Should have created 2 cards
        assert mock_server.create_card.call_count == 2

        # Check first card
        first_call = mock_server.create_card.call_args_list[0]
        assert first_call.kwargs["column_id"] == "col-backlog"
        assert "[TEST-1]" in first_call.kwargs["title"]
        assert first_call.kwargs["priority"] == "high"

        # Should have completed
        mock_server.complete_task.assert_called_once()
        complete_kwargs = mock_server.complete_task.call_args.kwargs
        assert "2" in complete_kwargs["output_text"]
        assert complete_kwargs["result_data"]["imported"] == 2


class TestJiraExecutorImportErrors:
    @pytest.mark.asyncio
    async def test_fails_on_missing_jql(self, config, mock_server, mock_jira_modules):
        task = {
            "id": "t-bad",
            "task_type": "jira_import",
            "payload_json": json.dumps({"column_id": "col-1"}),
        }

        mock_jira_modules["client_module"].JiraClient = MagicMock()
        mock_jira_modules["client_module"].JiraError = Exception
        mock_jira_modules["models_module"].JiraConfig = MagicMock()

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "jql" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()

    @pytest.mark.asyncio
    async def test_fails_on_missing_column_id(self, config, mock_server, mock_jira_modules):
        task = {
            "id": "t-bad",
            "task_type": "jira_import",
            "payload_json": json.dumps({"jql": "project = TEST"}),
        }

        mock_jira_modules["client_module"].JiraClient = MagicMock()
        mock_jira_modules["client_module"].JiraError = Exception
        mock_jira_modules["models_module"].JiraConfig = MagicMock()

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "column_id" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()

    @pytest.mark.asyncio
    async def test_fails_on_invalid_json(self, config, mock_server):
        task = {
            "id": "t-bad-json",
            "task_type": "jira_import",
            "payload_json": "not valid json {{{",
        }

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "invalid" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()


class TestJiraExecutorPush:
    @pytest.mark.asyncio
    async def test_pushes_card_to_jira(self, config, mock_server, mock_jira_modules):
        task = {
            "id": "t-push",
            "task_type": "jira_push",
            "payload_json": json.dumps(
                {
                    "card_title": "My Card",
                    "card_description": "A description",
                    "project": "TEST",
                }
            ),
        }

        mock_issue = MagicMock()
        mock_issue.key = "TEST-99"
        mock_issue.browse_url = "https://jira.example.com/browse/TEST-99"

        mock_jira = MagicMock()
        mock_jira.create_issue.return_value = mock_issue

        mock_jira_modules["client_module"].JiraClient.return_value = mock_jira
        mock_jira_modules["client_module"].JiraError = Exception
        mock_jira_modules["models_module"].JiraConfig.load.return_value = MagicMock()

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.complete_task.assert_called_once()
        complete_kwargs = mock_server.complete_task.call_args.kwargs
        assert "TEST-99" in complete_kwargs["output_text"]
        assert complete_kwargs["result_data"]["issue_key"] == "TEST-99"

    @pytest.mark.asyncio
    async def test_push_fails_on_missing_title(self, config, mock_server, mock_jira_modules):
        task = {
            "id": "t-push-bad",
            "task_type": "jira_push",
            "payload_json": json.dumps({"card_description": "no title"}),
        }

        mock_jira_modules["client_module"].JiraClient = MagicMock()
        mock_jira_modules["client_module"].JiraError = Exception
        mock_jira_modules["models_module"].JiraConfig = MagicMock()

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()


class TestJiraExecutorSync:
    @pytest.mark.asyncio
    async def test_sync_completes_with_placeholder(self, config, mock_server):
        task = {
            "id": "t-sync",
            "task_type": "jira_sync",
            "payload_json": json.dumps({"board_id": "b-1"}),
        }

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.complete_task.assert_called_once()
        assert (
            "not yet fully implemented" in mock_server.complete_task.call_args.kwargs["output_text"]
        )


class TestJiraExecutorUnknownType:
    @pytest.mark.asyncio
    async def test_fails_on_unknown_jira_type(self, config, mock_server):
        task = {
            "id": "t-unknown-jira",
            "task_type": "jira_teleport",
            "payload_json": "{}",
        }

        executor = JiraExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "Unknown" in mock_server.fail_task.call_args.kwargs["error_summary"]
