"""Tests for ServerClient HTTP communication."""

from __future__ import annotations

import json

import httpx
import pytest

from kira.worker.client import ServerClient, ServerError


@pytest.fixture
def mock_transport():
    """Create a mock transport that records requests and returns canned responses."""

    class MockTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.requests: list[httpx.Request] = []
            self.responses: dict[str, tuple[int, dict]] = {}

        def set_response(self, method: str, path: str, status: int, body: dict):
            key = f"{method.upper()} {path}"
            self.responses[key] = (status, body)

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            key = f"{request.method} {request.url.raw_path.decode()}"

            if key in self.responses:
                status, body = self.responses[key]
                return httpx.Response(
                    status_code=status,
                    json=body,
                    request=request,
                )

            # Default: 404
            return httpx.Response(
                status_code=404,
                json={"detail": f"No mock for {key}"},
                request=request,
            )

    return MockTransport()


@pytest.fixture
def client_with_transport(mock_transport):
    """Create a ServerClient backed by the mock transport."""

    async def _create(token: str = "test-token"):
        client = ServerClient("http://test-server:8000", token=token)
        # Replace the internal httpx client with one using our mock transport
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="http://test-server:8000",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            transport=mock_transport,
        )
        return client

    return _create


class TestServerClientLogin:
    @pytest.mark.asyncio
    async def test_login_sends_username(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/auth/login",
            200,
            {"token": "jwt-abc", "user": {"username": "alice"}},
        )

        client = await client_with_transport(token="")
        result = await client.login("alice")

        assert result["token"] == "jwt-abc"
        assert result["user"]["username"] == "alice"

        # Verify request body
        request = mock_transport.requests[0]
        body = json.loads(request.content)
        assert body["username"] == "alice"

        await client.close()

    @pytest.mark.asyncio
    async def test_login_failure_raises_server_error(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/auth/login",
            401,
            {"detail": "Invalid credentials"},
        )

        client = await client_with_transport(token="")
        with pytest.raises(ServerError) as exc_info:
            await client.login("bad_user")

        assert exc_info.value.status_code == 401
        assert "Invalid credentials" in exc_info.value.detail

        await client.close()


class TestServerClientWorkerLifecycle:
    @pytest.mark.asyncio
    async def test_register_worker(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/workers/register",
            201,
            {
                "worker_id": "w123",
                "max_concurrent_tasks": 1,
                "poll_interval_seconds": 5,
            },
        )

        client = await client_with_transport()
        result = await client.register_worker(
            hostname="test-host",
            version="0.3.0",
            capabilities=["agent", "jira"],
        )

        assert result["worker_id"] == "w123"
        assert result["max_concurrent_tasks"] == 1

        request = mock_transport.requests[0]
        body = json.loads(request.content)
        assert body["hostname"] == "test-host"
        assert body["capabilities"] == ["agent", "jira"]

        await client.close()

    @pytest.mark.asyncio
    async def test_heartbeat(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/workers/heartbeat",
            200,
            {
                "status": "ok",
                "directives": {"max_concurrent_tasks": 2, "cancel_task_ids": ["t1"]},
            },
        )

        client = await client_with_transport()
        result = await client.heartbeat("w123", ["t1", "t2"], system_load=0.5)

        assert result["status"] == "ok"
        assert result["directives"]["cancel_task_ids"] == ["t1"]

        await client.close()


class TestServerClientTaskOperations:
    @pytest.mark.asyncio
    async def test_poll_tasks(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "GET",
            "/api/workers/tasks/poll?worker_id=w123&limit=1",
            200,
            {"tasks": [{"id": "t1", "task_type": "agent_run"}]},
        )

        client = await client_with_transport()
        tasks = await client.poll_tasks("w123", limit=1)

        assert len(tasks) == 1
        assert tasks[0]["id"] == "t1"

        await client.close()

    @pytest.mark.asyncio
    async def test_poll_tasks_empty(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "GET",
            "/api/workers/tasks/poll?worker_id=w123&limit=1",
            200,
            {"tasks": []},
        )

        client = await client_with_transport()
        tasks = await client.poll_tasks("w123", limit=1)

        assert tasks == []

        await client.close()

    @pytest.mark.asyncio
    async def test_claim_task(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/workers/tasks/t1/claim",
            200,
            {"status": "claimed", "task": {"id": "t1"}},
        )

        client = await client_with_transport()
        result = await client.claim_task("t1", "w123")

        assert result["status"] == "claimed"

        await client.close()

    @pytest.mark.asyncio
    async def test_claim_task_conflict(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/workers/tasks/t1/claim",
            409,
            {"detail": "Task already claimed"},
        )

        client = await client_with_transport()
        with pytest.raises(ServerError) as exc_info:
            await client.claim_task("t1", "w123")

        assert exc_info.value.status_code == 409

        await client.close()

    @pytest.mark.asyncio
    async def test_complete_task(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/workers/tasks/t1/complete",
            200,
            {
                "status": "completed",
                "next_action": {"type": "card_moved", "card_id": "c1"},
            },
        )

        client = await client_with_transport()
        result = await client.complete_task(
            "t1", "w123", output_text="Done!", result_data={"lines": 42}
        )

        assert result["status"] == "completed"

        request = mock_transport.requests[0]
        body = json.loads(request.content)
        assert body["output_text"] == "Done!"
        assert body["result_data"]["lines"] == 42

        await client.close()

    @pytest.mark.asyncio
    async def test_fail_task(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/workers/tasks/t1/fail",
            200,
            {"status": "failed", "next_action": None},
        )

        client = await client_with_transport()
        result = await client.fail_task(
            "t1", "w123", error_summary="Timeout", output_text="partial"
        )

        assert result["status"] == "failed"

        await client.close()

    @pytest.mark.asyncio
    async def test_report_progress(self, mock_transport, client_with_transport):
        mock_transport.set_response(
            "POST",
            "/api/workers/tasks/t1/progress",
            200,
            {"status": "ok"},
        )

        client = await client_with_transport()
        result = await client.report_progress("t1", "w123", "Running phase 2...")

        assert result["status"] == "ok"

        await client.close()

    @pytest.mark.asyncio
    async def test_report_progress_with_phase_metadata(
        self, mock_transport, client_with_transport
    ):
        mock_transport.set_response(
            "POST",
            "/api/workers/tasks/t1/progress",
            200,
            {"status": "ok"},
        )

        client = await client_with_transport()
        result = await client.report_progress(
            "t1",
            "w123",
            "Analyzing...",
            step=1,
            total_steps=5,
            phase="analyzing",
        )

        assert result["status"] == "ok"

        request = mock_transport.requests[0]
        body = json.loads(request.content)
        assert body["step"] == 1
        assert body["total_steps"] == 5
        assert body["phase"] == "analyzing"
        assert body["progress_text"] == "Analyzing..."

        await client.close()

    @pytest.mark.asyncio
    async def test_report_progress_omits_none_fields(
        self, mock_transport, client_with_transport
    ):
        mock_transport.set_response(
            "POST",
            "/api/workers/tasks/t1/progress",
            200,
            {"status": "ok"},
        )

        client = await client_with_transport()
        await client.report_progress(
            "t1", "w123", "Working...", step=2,
        )

        request = mock_transport.requests[0]
        body = json.loads(request.content)
        assert body["step"] == 2
        assert "total_steps" not in body
        assert "phase" not in body

        await client.close()


class TestServerClientTokenManagement:
    @pytest.mark.asyncio
    async def test_set_token_updates_header(self, mock_transport, client_with_transport):
        client = await client_with_transport(token="old-token")
        client.set_token("new-token")

        assert client._client.headers["Authorization"] == "Bearer new-token"

        await client.close()
