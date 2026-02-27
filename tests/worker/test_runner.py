"""Tests for WorkerRunner poll and heartbeat loops."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from kira.worker.client import ServerError
from kira.worker.config import WorkerConfig
from kira.worker.runner import WorkerRunner


@pytest.fixture
def config():
    return WorkerConfig(
        server_url="http://test:8000",
        poll_interval=0.05,  # Fast polling for tests
        heartbeat_interval=0.05,
        max_concurrent_tasks=1,
        kiro_timeout=10,
    )


@pytest.fixture
def mock_server():
    server = AsyncMock()
    server.register_worker.return_value = {
        "worker_id": "w-test-123",
        "poll_interval_seconds": 0.05,
        "max_concurrent_tasks": 1,
    }
    server.heartbeat.return_value = {
        "status": "ok",
        "directives": {"cancel_task_ids": []},
    }
    server.poll_tasks.return_value = []
    server.claim_task.return_value = {"status": "claimed"}
    server.report_progress.return_value = {"status": "ok"}
    server.complete_task.return_value = {"status": "completed"}
    server.fail_task.return_value = {"status": "failed"}
    return server


class TestWorkerRegistration:
    @pytest.mark.asyncio
    async def test_start_registers_worker(self, config, mock_server):
        runner = WorkerRunner(config, mock_server)

        # Stop after one cycle
        async def stop_after_delay():
            await asyncio.sleep(0.1)
            await runner.stop()

        # Start + stop concurrently
        await asyncio.gather(
            runner.start(),
            stop_after_delay(),
        )

        mock_server.register_worker.assert_called_once()
        call_kwargs = mock_server.register_worker.call_args
        assert call_kwargs.kwargs["version"] == "0.3.0"
        assert "agent" in call_kwargs.kwargs["capabilities"]
        assert "jira" in call_kwargs.kwargs["capabilities"]
        assert runner.worker_id == "w-test-123"

    @pytest.mark.asyncio
    async def test_start_applies_server_config(self, config, mock_server):
        mock_server.register_worker.return_value = {
            "worker_id": "w-test",
            "poll_interval_seconds": 15.0,
            "max_concurrent_tasks": 3,
        }

        runner = WorkerRunner(config, mock_server)

        async def stop_after_delay():
            await asyncio.sleep(0.1)
            await runner.stop()

        await asyncio.gather(runner.start(), stop_after_delay())

        assert config.poll_interval == 15.0
        assert config.max_concurrent_tasks == 3


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_poll_with_no_tasks(self, config, mock_server):
        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        async def stop_soon():
            await asyncio.sleep(0.15)
            runner._running = False

        await asyncio.gather(runner._poll_loop(), stop_soon())

        # Should have polled at least once
        assert mock_server.poll_tasks.call_count >= 1

    @pytest.mark.asyncio
    async def test_poll_dispatches_agent_task(self, config, mock_server):
        task_data = {
            "id": "t-agent-1",
            "task_type": "agent_run",
            "agent_type": "coder",
            "agent_model": "smart",
            "prompt_text": "Implement hello world",
        }
        # Return task on first poll, then empty
        mock_server.poll_tasks.side_effect = [[task_data], [], [], []]

        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        # Mock the agent executor to avoid real kiro-cli execution
        mock_agent = patch(
            "kira.worker.runner.WorkerRunner._run_agent",
            new_callable=AsyncMock,
        )
        with mock_agent:

            async def stop_soon():
                await asyncio.sleep(0.2)
                runner._running = False

            await asyncio.gather(runner._poll_loop(), stop_soon())

        # Should have claimed the task
        mock_server.claim_task.assert_called_with("t-agent-1", "w-test")

    @pytest.mark.asyncio
    async def test_poll_dispatches_jira_task(self, config, mock_server):
        task_data = {
            "id": "t-jira-1",
            "task_type": "jira_import",
            "payload_json": '{"jql": "project = TEST"}',
        }
        mock_server.poll_tasks.side_effect = [[task_data], [], [], []]

        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        mock_jira = patch(
            "kira.worker.runner.WorkerRunner._run_jira",
            new_callable=AsyncMock,
        )
        with mock_jira:

            async def stop_soon():
                await asyncio.sleep(0.2)
                runner._running = False

            await asyncio.gather(runner._poll_loop(), stop_soon())

        mock_server.claim_task.assert_called_with("t-jira-1", "w-test")

    @pytest.mark.asyncio
    async def test_poll_skips_already_claimed_task(self, config, mock_server):
        task_data = {"id": "t-1", "task_type": "agent_run", "prompt_text": "test"}
        mock_server.poll_tasks.return_value = [task_data]
        mock_server.claim_task.side_effect = ServerError("Already claimed", status_code=409)

        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        async def stop_soon():
            await asyncio.sleep(0.15)
            runner._running = False

        # Should not raise
        await asyncio.gather(runner._poll_loop(), stop_soon())

    @pytest.mark.asyncio
    async def test_poll_respects_max_concurrent(self, config, mock_server):
        config.max_concurrent_tasks = 1
        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        # Simulate a currently running task
        running_task = asyncio.create_task(asyncio.sleep(10))
        runner._current_tasks["existing"] = running_task

        mock_server.poll_tasks.return_value = [
            {"id": "t-new", "task_type": "agent_run", "prompt_text": "test"}
        ]

        async def stop_soon():
            await asyncio.sleep(0.15)
            runner._running = False
            running_task.cancel()

        await asyncio.gather(runner._poll_loop(), stop_soon())

        # Should not have tried to poll because we're at capacity
        mock_server.poll_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_handles_server_errors(self, config, mock_server):
        mock_server.poll_tasks.side_effect = ServerError("Connection refused")

        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        async def stop_soon():
            await asyncio.sleep(0.15)
            runner._running = False

        # Should not raise, just log and continue
        await asyncio.gather(runner._poll_loop(), stop_soon())


class TestHeartbeatLoop:
    @pytest.mark.asyncio
    async def test_heartbeat_sends_running_task_ids(self, config, mock_server):
        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        # Add a fake running task
        running_task = asyncio.create_task(asyncio.sleep(10))
        runner._current_tasks["t-running"] = running_task

        async def stop_soon():
            await asyncio.sleep(0.15)
            runner._running = False
            running_task.cancel()

        await asyncio.gather(runner._heartbeat_loop(), stop_soon())

        # Should have sent at least one heartbeat with the running task
        assert mock_server.heartbeat.call_count >= 1
        call_args = mock_server.heartbeat.call_args
        assert "t-running" in call_args.args[1]  # running_task_ids

    @pytest.mark.asyncio
    async def test_heartbeat_cancels_tasks_on_directive(self, config, mock_server):
        mock_server.heartbeat.return_value = {
            "status": "ok",
            "directives": {"cancel_task_ids": ["t-cancel-me"]},
        }

        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        # Add a cancelable task
        cancel_event = asyncio.Event()

        async def long_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancel_event.set()
                raise

        task = asyncio.create_task(long_task())
        runner._current_tasks["t-cancel-me"] = task

        async def stop_soon():
            await asyncio.sleep(0.15)
            runner._running = False

        await asyncio.gather(runner._heartbeat_loop(), stop_soon())

        # The task should have been cancelled
        assert cancel_event.is_set() or task.cancelled()

    @pytest.mark.asyncio
    async def test_heartbeat_handles_server_errors(self, config, mock_server):
        mock_server.heartbeat.side_effect = ServerError("Connection refused")

        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        async def stop_soon():
            await asyncio.sleep(0.15)
            runner._running = False

        # Should not raise, just log and continue
        await asyncio.gather(runner._heartbeat_loop(), stop_soon())


class TestUnknownTaskType:
    @pytest.mark.asyncio
    async def test_unknown_task_type_reports_failure(self, config, mock_server):
        task_data = {"id": "t-unknown", "task_type": "alien_task", "prompt_text": ""}
        mock_server.poll_tasks.side_effect = [[task_data], [], []]

        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        async def stop_soon():
            await asyncio.sleep(0.2)
            runner._running = False

        await asyncio.gather(runner._poll_loop(), stop_soon())

        # Should have reported failure for the unknown task type
        mock_server.fail_task.assert_called_once()
        call_kwargs = mock_server.fail_task.call_args
        assert "t-unknown" in call_kwargs.args
        assert "Unknown task type" in call_kwargs.kwargs.get(
            "error_summary", call_kwargs.args[2] if len(call_kwargs.args) > 2 else ""
        )


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_cancels_running_tasks(self, config, mock_server):
        runner = WorkerRunner(config, mock_server)
        runner.worker_id = "w-test"

        cancel_event = asyncio.Event()

        async def long_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancel_event.set()
                raise  # Must re-raise for the task to be marked as cancelled

        task = asyncio.create_task(long_task())
        # Yield control so the task actually starts awaiting sleep
        await asyncio.sleep(0)

        runner._current_tasks["t-1"] = task

        await runner.stop()

        assert runner._running is False
        assert cancel_event.is_set()
        assert len(runner._current_tasks) == 0
