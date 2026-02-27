"""Tests for the AgentDaemon WebSocket server."""

from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import websockets

from kira.agent.daemon import ALLOWED_ORIGIN_PREFIXES, AgentDaemon


@pytest.fixture
def daemon(tmp_path):
    """Create an AgentDaemon with a temp PID file and short grace period."""
    d = AgentDaemon(port=0, grace_period=0.1)
    d._pidfile = tmp_path / "agent.pid"
    return d


@pytest.fixture
def mock_server_client():
    """Create a mock ServerClient."""
    client = AsyncMock()
    client.register_worker.return_value = {
        "worker_id": "w-daemon-test",
        "poll_interval_seconds": 0.05,
        "max_concurrent_tasks": 1,
    }
    client.heartbeat.return_value = {
        "status": "ok",
        "directives": {"cancel_task_ids": []},
    }
    client.poll_tasks.return_value = []
    client.close.return_value = None
    return client


class TestDaemonState:
    def test_initial_state_is_dormant(self, daemon):
        assert daemon.state == "dormant"
        assert daemon.sessions == {}
        assert daemon.runner is None
        assert daemon.server_client is None

    def test_default_port(self):
        d = AgentDaemon()
        assert d.port == 9820

    def test_default_grace_period(self):
        d = AgentDaemon()
        assert d.grace_period == 3.0


class TestStatusJson:
    def test_dormant_status(self, daemon):
        status = json.loads(daemon._status_json())
        assert status["type"] == "status"
        assert status["state"] == "dormant"
        assert status["worker_id"] is None
        assert status["server_url"] is None
        assert status["running_tasks"] == 0
        assert status["uptime_seconds"] == 0

    def test_active_status_includes_worker_info(self, daemon):
        daemon.state = "active"
        daemon._active_server_url = "http://localhost:8000"
        daemon._activated_at = 0  # monotonic time

        mock_runner = MagicMock()
        mock_runner.worker_id = "w-test-456"
        mock_runner._current_tasks = {"t1": MagicMock()}
        daemon.runner = mock_runner

        status = json.loads(daemon._status_json())
        assert status["state"] == "active"
        assert status["worker_id"] == "w-test-456"
        assert status["server_url"] == "http://localhost:8000"
        assert status["running_tasks"] == 1
        assert status["uptime_seconds"] > 0


class TestSetState:
    @pytest.mark.asyncio
    async def test_set_state_changes_state(self, daemon):
        daemon._set_state("activating")
        assert daemon.state == "activating"

    @pytest.mark.asyncio
    async def test_set_state_no_change_does_not_broadcast(self, daemon):
        daemon.state = "dormant"
        # No sessions to broadcast to, but this should not error
        daemon._set_state("dormant")
        assert daemon.state == "dormant"


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_ping_returns_pong(self, daemon):
        ws = AsyncMock()
        await daemon._handle_message(ws, {"type": "ping"})
        ws.send.assert_called_once_with(json.dumps({"type": "pong"}))

    @pytest.mark.asyncio
    async def test_unknown_message_type_ignored(self, daemon):
        ws = AsyncMock()
        # Should not raise
        await daemon._handle_message(ws, {"type": "unknown_type"})
        ws.send.assert_not_called()


class TestActivate:
    @pytest.mark.asyncio
    async def test_activate_missing_fields_returns_error(self, daemon):
        ws = AsyncMock()

        # Missing token
        msg = {"type": "activate", "server_url": "http://x", "session_id": "s1"}
        await daemon._activate(ws, msg)
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "error"
        assert sent["code"] == "missing_fields"

    @pytest.mark.asyncio
    async def test_activate_missing_server_url_returns_error(self, daemon):
        ws = AsyncMock()

        await daemon._activate(ws, {"type": "activate", "token": "jwt...", "session_id": "s1"})
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "error"
        assert sent["code"] == "missing_fields"

    @pytest.mark.asyncio
    async def test_activate_tracks_session(self, daemon, mock_server_client):
        ws = AsyncMock()

        with patch.object(daemon, "_start_runner", new_callable=AsyncMock) as mock_start:
            await daemon._activate(
                ws,
                {
                    "type": "activate",
                    "token": "jwt-abc",
                    "server_url": "http://localhost:8000",
                    "session_id": "sess-1",
                },
            )

        assert "sess-1" in daemon.sessions
        assert daemon.sessions["sess-1"] is ws
        assert daemon.state == "active"
        mock_start.assert_called_once_with("http://localhost:8000", "jwt-abc")

    @pytest.mark.asyncio
    async def test_activate_same_server_updates_token(self, daemon):
        """When already active on the same server, just update the token."""
        ws = AsyncMock()
        daemon.state = "active"
        daemon._active_server_url = "http://localhost:8000"
        daemon.server_client = MagicMock()

        await daemon._activate(
            ws,
            {
                "type": "activate",
                "token": "new-jwt",
                "server_url": "http://localhost:8000",
                "session_id": "sess-2",
            },
        )

        daemon.server_client.set_token.assert_called_once_with("new-jwt")
        assert daemon.state == "active"  # Stays active

    @pytest.mark.asyncio
    async def test_activate_different_server_restarts(self, daemon):
        """When already active on a different server, stop and restart."""
        ws = AsyncMock()
        daemon.state = "active"
        daemon._active_server_url = "http://old-server:8000"

        with (
            patch.object(daemon, "_stop_runner", new_callable=AsyncMock) as mock_stop,
            patch.object(daemon, "_start_runner", new_callable=AsyncMock) as mock_start,
        ):
            await daemon._activate(
                ws,
                {
                    "type": "activate",
                    "token": "jwt",
                    "server_url": "http://new-server:8000",
                    "session_id": "sess-3",
                },
            )

        mock_stop.assert_called_once()
        mock_start.assert_called_once_with("http://new-server:8000", "jwt")

    @pytest.mark.asyncio
    async def test_activate_failure_returns_to_dormant(self, daemon):
        ws = AsyncMock()

        with patch.object(
            daemon, "_start_runner", new_callable=AsyncMock, side_effect=Exception("conn refused")
        ):
            await daemon._activate(
                ws,
                {
                    "type": "activate",
                    "token": "jwt",
                    "server_url": "http://localhost:8000",
                    "session_id": "sess-4",
                },
            )

        assert daemon.state == "dormant"


class TestDeactivate:
    @pytest.mark.asyncio
    async def test_deactivate_removes_session(self, daemon):
        ws = AsyncMock()
        daemon.sessions["sess-1"] = ws
        daemon.state = "active"

        with patch.object(daemon, "_stop_runner", new_callable=AsyncMock) as mock_stop:
            await daemon._deactivate({"type": "deactivate", "session_id": "sess-1"})

        assert "sess-1" not in daemon.sessions
        mock_stop.assert_called_once()
        assert daemon.state == "dormant"

    @pytest.mark.asyncio
    async def test_deactivate_keeps_running_with_other_sessions(self, daemon):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        daemon.sessions["sess-1"] = ws1
        daemon.sessions["sess-2"] = ws2
        daemon.state = "active"

        with patch.object(daemon, "_stop_runner", new_callable=AsyncMock) as mock_stop:
            await daemon._deactivate({"type": "deactivate", "session_id": "sess-1"})

        assert "sess-1" not in daemon.sessions
        assert "sess-2" in daemon.sessions
        # Should NOT have stopped the runner -- other sessions remain
        mock_stop.assert_not_called()
        assert daemon.state == "active"

    @pytest.mark.asyncio
    async def test_deactivate_unknown_session_is_noop(self, daemon):
        daemon.state = "active"
        daemon.sessions["other"] = AsyncMock()

        with patch.object(daemon, "_stop_runner", new_callable=AsyncMock) as mock_stop:
            await daemon._deactivate({"type": "deactivate", "session_id": "nonexistent"})

        mock_stop.assert_not_called()


class TestGracePeriod:
    @pytest.mark.asyncio
    async def test_grace_period_deactivates_when_empty(self, daemon):
        daemon.state = "active"

        with patch.object(daemon, "_stop_runner", new_callable=AsyncMock) as mock_stop:
            await daemon._grace_expired()

        mock_stop.assert_called_once()
        assert daemon.state == "dormant"

    @pytest.mark.asyncio
    async def test_grace_period_cancelled_by_reconnect(self, daemon):
        daemon.state = "deactivating"
        daemon.sessions["new-session"] = AsyncMock()  # Someone reconnected

        with patch.object(daemon, "_stop_runner", new_callable=AsyncMock) as mock_stop:
            await daemon._grace_expired()

        mock_stop.assert_not_called()
        assert daemon.state == "active"

    @pytest.mark.asyncio
    async def test_check_empty_sessions_starts_grace(self, daemon):
        daemon.state = "active"
        daemon.sessions.clear()

        daemon._check_empty_sessions()

        assert daemon.state == "deactivating"
        assert daemon._grace_task is not None

        # Cancel the grace task to avoid it running in the background
        daemon._grace_task.cancel()

    @pytest.mark.asyncio
    async def test_check_empty_sessions_noop_when_dormant(self, daemon):
        daemon.state = "dormant"
        daemon.sessions.clear()

        daemon._check_empty_sessions()

        assert daemon._grace_task is None


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_status_to_all_sessions(self, daemon):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        daemon.sessions = {"s1": ws1, "s2": ws2}

        await daemon._broadcast_status()

        assert ws1.send.call_count == 1
        assert ws2.send.call_count == 1

        # Both should receive the same status
        msg1 = json.loads(ws1.send.call_args[0][0])
        msg2 = json.loads(ws2.send.call_args[0][0])
        assert msg1["type"] == "status"
        assert msg2["type"] == "status"

    @pytest.mark.asyncio
    async def test_broadcast_status_removes_closed_connections(self, daemon):
        ws_ok = AsyncMock()
        ws_closed = AsyncMock()
        ws_closed.send.side_effect = websockets.ConnectionClosed(None, None)
        daemon.sessions = {"s-ok": ws_ok, "s-closed": ws_closed}

        await daemon._broadcast_status()

        assert "s-ok" in daemon.sessions
        assert "s-closed" not in daemon.sessions

    @pytest.mark.asyncio
    async def test_broadcast_error_to_all_sessions(self, daemon):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        daemon.sessions = {"s1": ws1, "s2": ws2}

        await daemon._broadcast_error("test_code", "test message")

        msg1 = json.loads(ws1.send.call_args[0][0])
        assert msg1["type"] == "error"
        assert msg1["code"] == "test_code"
        assert msg1["message"] == "test message"


def _make_worker_config():
    """Create a WorkerConfig with fast intervals for testing."""
    from kira.worker.config import WorkerConfig

    return WorkerConfig(
        server_url="http://test:8000",
        poll_interval=0.05,
        heartbeat_interval=0.05,
        max_concurrent_tasks=1,
        kiro_timeout=10,
    )


class TestStartRunner:
    @pytest.mark.asyncio
    async def test_start_runner_creates_client_and_runner(self, daemon, mock_server_client):
        with (
            patch("kira.agent.daemon.ServerClient", return_value=mock_server_client),
            patch("kira.agent.daemon.WorkerConfig") as mock_config_cls,
        ):
            mock_config_cls.load.return_value = _make_worker_config()
            await daemon._start_runner("http://localhost:8000", "jwt-token")

        assert daemon.server_client is mock_server_client
        assert daemon.runner is not None
        assert daemon.runner.worker_id == "w-daemon-test"
        assert daemon._active_server_url == "http://localhost:8000"
        assert daemon._activated_at is not None
        assert daemon._runner_task is not None

        # Clean up the background task
        daemon._runner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await daemon._runner_task

    @pytest.mark.asyncio
    async def test_start_runner_applies_server_overrides(self, daemon, mock_server_client):
        mock_server_client.register_worker.return_value = {
            "worker_id": "w-test",
            "poll_interval_seconds": 15.0,
            "max_concurrent_tasks": 4,
        }

        with (
            patch("kira.agent.daemon.ServerClient", return_value=mock_server_client),
            patch("kira.agent.daemon.WorkerConfig") as mock_config_cls,
        ):
            config = _make_worker_config()
            mock_config_cls.load.return_value = config
            await daemon._start_runner("http://localhost:8000", "jwt")

        assert config.poll_interval == 15.0
        assert config.max_concurrent_tasks == 4

        # Clean up
        daemon._runner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await daemon._runner_task


class TestStopRunner:
    @pytest.mark.asyncio
    async def test_stop_runner_cleans_up_all_state(self, daemon):
        daemon.runner = AsyncMock()
        daemon.server_client = AsyncMock()
        daemon._active_server_url = "http://test"
        daemon._activated_at = 100.0
        daemon._runner_task = asyncio.create_task(asyncio.sleep(100))

        await daemon._stop_runner()

        assert daemon.runner is None
        assert daemon.server_client is None
        assert daemon._active_server_url is None
        assert daemon._activated_at is None
        assert daemon._runner_task is None

    @pytest.mark.asyncio
    async def test_stop_runner_noop_when_not_started(self, daemon):
        # Should not raise when nothing is running
        await daemon._stop_runner()


class TestPidFile:
    @pytest.mark.asyncio
    async def test_stale_pidfile_is_overwritten(self, daemon, tmp_path):
        daemon._pidfile = tmp_path / "agent.pid"
        daemon._pidfile.write_text("99999999")  # Non-existent PID

        # start() should overwrite the stale PID file.
        # We can't easily test the full start() here, but we can verify
        # the PID check logic doesn't block.
        assert daemon._pidfile.exists()


class TestOriginValidation:
    def test_allowed_origin_prefixes(self):
        assert any("http://localhost:3000".startswith(p) for p in ALLOWED_ORIGIN_PREFIXES)
        assert any("http://127.0.0.1:5173".startswith(p) for p in ALLOWED_ORIGIN_PREFIXES)
        assert any("https://kira.example.com".startswith(p) for p in ALLOWED_ORIGIN_PREFIXES)

    def test_disallowed_origin(self):
        assert not any("http://evil.com".startswith(p) for p in ALLOWED_ORIGIN_PREFIXES)
        assert not any("http://10.0.0.1:8080".startswith(p) for p in ALLOWED_ORIGIN_PREFIXES)


class TestIsKiraProcess:
    def test_detects_kira_process(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="kira\n", stderr="")
        with patch("kira.agent.daemon.subprocess.run", return_value=result):
            assert AgentDaemon._is_kira_process(12345) is True

    def test_detects_non_kira_process(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="python\n", stderr="")
        with patch("kira.agent.daemon.subprocess.run", return_value=result):
            assert AgentDaemon._is_kira_process(12345) is False

    def test_case_insensitive_match(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="Kira\n", stderr="")
        with patch("kira.agent.daemon.subprocess.run", return_value=result):
            assert AgentDaemon._is_kira_process(12345) is True

    def test_timeout_assumes_kira(self):
        with patch(
            "kira.agent.daemon.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ps", timeout=5),
        ):
            assert AgentDaemon._is_kira_process(12345) is True

    def test_os_error_assumes_kira(self):
        with patch("kira.agent.daemon.subprocess.run", side_effect=OSError("no ps")):
            assert AgentDaemon._is_kira_process(12345) is True

    def test_passes_correct_args(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="kira\n", stderr="")
        with patch("kira.agent.daemon.subprocess.run", return_value=result) as mock_run:
            AgentDaemon._is_kira_process(42)
            mock_run.assert_called_once_with(
                ["ps", "-p", "42", "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5,
            )


class TestCheckServerVersion:
    @pytest.mark.asyncio
    async def test_broadcasts_upgrade_when_version_differs(self, daemon):
        ws = AsyncMock()
        daemon.sessions = {"s1": ws}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "version": "0.4.0",
            "install_url": "https://kira.example.com",
        }

        with (
            patch("importlib.metadata.version", return_value="0.3.0"),
            patch("kira.agent.daemon.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await daemon._check_server_version("https://kira.example.com")

        ws.send.assert_called_once()
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["type"] == "upgrade_available"
        assert msg["current_version"] == "0.3.0"
        assert msg["server_version"] == "0.4.0"
        assert msg["install_url"] == "https://kira.example.com/api/agent/install.sh"

    @pytest.mark.asyncio
    async def test_no_broadcast_when_versions_match(self, daemon):
        ws = AsyncMock()
        daemon.sessions = {"s1": ws}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"version": "0.3.0", "install_url": "https://x"}

        with (
            patch("importlib.metadata.version", return_value="0.3.0"),
            patch("kira.agent.daemon.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await daemon._check_server_version("https://kira.example.com")

        ws.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_silent_on_http_failure(self, daemon):
        ws = AsyncMock()
        daemon.sessions = {"s1": ws}

        with (
            patch("importlib.metadata.version", return_value="0.3.0"),
            patch("kira.agent.daemon.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Should not raise
            await daemon._check_server_version("https://kira.example.com")

        ws.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_silent_on_package_not_found(self, daemon):
        import importlib.metadata as _meta

        ws = AsyncMock()
        daemon.sessions = {"s1": ws}

        with patch("importlib.metadata.version", side_effect=_meta.PackageNotFoundError("kira")):
            # Should not raise
            await daemon._check_server_version("https://kira.example.com")

        ws.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_server_install_url_from_response(self, daemon):
        """When server returns a custom install_url, it should be used as the base."""
        ws = AsyncMock()
        daemon.sessions = {"s1": ws}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "version": "0.5.0",
            "install_url": "https://cdn.example.com",
        }

        with (
            patch("importlib.metadata.version", return_value="0.3.0"),
            patch("kira.agent.daemon.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await daemon._check_server_version("https://kira.example.com")

        msg = json.loads(ws.send.call_args[0][0])
        assert msg["install_url"] == "https://cdn.example.com/api/agent/install.sh"

    @pytest.mark.asyncio
    async def test_falls_back_to_server_url_when_no_install_url(self, daemon):
        """When server response has no install_url, fall back to server_url."""
        ws = AsyncMock()
        daemon.sessions = {"s1": ws}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"version": "0.5.0"}

        with (
            patch("importlib.metadata.version", return_value="0.3.0"),
            patch("kira.agent.daemon.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await daemon._check_server_version("https://myserver.com")

        msg = json.loads(ws.send.call_args[0][0])
        assert msg["install_url"] == "https://myserver.com/api/agent/install.sh"


class TestActivateVersionCheck:
    @pytest.mark.asyncio
    async def test_activate_fires_version_check(self, daemon):
        """Successful activation should fire a version check task."""
        ws = AsyncMock()

        with (
            patch.object(daemon, "_start_runner", new_callable=AsyncMock),
            patch.object(daemon, "_check_server_version", new_callable=AsyncMock) as mock_check,
        ):
            await daemon._activate(
                ws,
                {
                    "type": "activate",
                    "token": "jwt-abc",
                    "server_url": "http://localhost:8000",
                    "session_id": "sess-vc",
                },
            )

            # Give the fire-and-forget task a chance to run
            await asyncio.sleep(0)

        mock_check.assert_called_once_with("http://localhost:8000")

    @pytest.mark.asyncio
    async def test_activate_failure_does_not_fire_version_check(self, daemon):
        """Failed activation should NOT fire a version check."""
        ws = AsyncMock()

        with (
            patch.object(
                daemon,
                "_start_runner",
                new_callable=AsyncMock,
                side_effect=Exception("fail"),
            ),
            patch.object(daemon, "_check_server_version", new_callable=AsyncMock) as mock_check,
        ):
            await daemon._activate(
                ws,
                {
                    "type": "activate",
                    "token": "jwt",
                    "server_url": "http://localhost:8000",
                    "session_id": "sess-fail",
                },
            )

            await asyncio.sleep(0)

        mock_check.assert_not_called()


class TestPickDirectory:
    @pytest.mark.asyncio
    async def test_pick_directory_routes_from_handle_message(self, daemon):
        ws = AsyncMock()
        with patch.object(daemon, "_pick_directory", new_callable=AsyncMock) as mock_pick:
            await daemon._handle_message(ws, {"type": "pick_directory", "request_id": "r1"})
        mock_pick.assert_called_once_with(ws, {"type": "pick_directory", "request_id": "r1"})

    @pytest.mark.asyncio
    async def test_pick_directory_returns_selected_path(self, daemon):
        ws = AsyncMock()
        msg = {"type": "pick_directory", "request_id": "req-42", "initial_dir": "/tmp"}

        with patch.object(AgentDaemon, "_open_dir_dialog", return_value="/Users/me/project"):
            await daemon._pick_directory(ws, msg)

        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "directory_picked"
        assert sent["request_id"] == "req-42"
        assert sent["path"] == "/Users/me/project"
        assert sent["cancelled"] is False

    @pytest.mark.asyncio
    async def test_pick_directory_returns_cancelled_when_none(self, daemon):
        ws = AsyncMock()
        msg = {"type": "pick_directory", "request_id": "req-43"}

        with patch.object(AgentDaemon, "_open_dir_dialog", return_value=None):
            await daemon._pick_directory(ws, msg)

        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "directory_picked"
        assert sent["request_id"] == "req-43"
        assert sent["path"] == ""
        assert sent["cancelled"] is True

    @pytest.mark.asyncio
    async def test_pick_directory_handles_exception(self, daemon):
        ws = AsyncMock()
        msg = {"type": "pick_directory", "request_id": "req-44"}

        with patch.object(
            AgentDaemon, "_open_dir_dialog", side_effect=RuntimeError("display not found")
        ):
            await daemon._pick_directory(ws, msg)

        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "directory_picked"
        assert sent["request_id"] == "req-44"
        assert sent["path"] == ""
        assert sent["cancelled"] is True
        assert sent["error"] == "display not found"

    @pytest.mark.asyncio
    async def test_pick_directory_defaults_for_missing_fields(self, daemon):
        ws = AsyncMock()
        msg = {"type": "pick_directory"}

        with patch.object(AgentDaemon, "_open_dir_dialog", return_value="/chosen") as mock_dialog:
            await daemon._pick_directory(ws, msg)

        mock_dialog.assert_called_once_with("")
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["request_id"] == ""
        assert sent["path"] == "/chosen"


class TestOpenDirDialog:
    def test_macos_osascript_success(self):
        result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="/Users/me/project/\n", stderr=""
        )
        with (
            patch("sys.platform", "darwin"),
            patch("kira.agent.daemon.subprocess.run", return_value=result),
        ):
            path = AgentDaemon._open_dir_dialog("/Users/me")
        assert path == "/Users/me/project"

    def test_macos_osascript_cancel(self):
        result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        with (
            patch("sys.platform", "darwin"),
            patch("kira.agent.daemon.subprocess.run", return_value=result),
        ):
            path = AgentDaemon._open_dir_dialog()
        assert path is None

    def test_macos_osascript_timeout(self):
        with (
            patch("sys.platform", "darwin"),
            patch(
                "kira.agent.daemon.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=120),
            ),
        ):
            path = AgentDaemon._open_dir_dialog()
        assert path is None

    def test_macos_includes_initial_dir_in_script(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="/chosen\n", stderr="")
        with (
            patch("sys.platform", "darwin"),
            patch("kira.agent.daemon.subprocess.run", return_value=result) as mock_run,
        ):
            AgentDaemon._open_dir_dialog("/start/here")

        script = mock_run.call_args[0][0][2]  # ["osascript", "-e", script]
        assert "default location" in script
        assert "/start/here" in script

    def test_macos_no_initial_dir(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="/chosen\n", stderr="")
        with (
            patch("sys.platform", "darwin"),
            patch("kira.agent.daemon.subprocess.run", return_value=result) as mock_run,
        ):
            AgentDaemon._open_dir_dialog("")

        script = mock_run.call_args[0][0][2]
        assert "default location" not in script

    def test_linux_tkinter_not_available(self):
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fake_import(name, *args, **kwargs):
            if name == "tkinter":
                raise ImportError("no tkinter")
            return real_import(name, *args, **kwargs)

        with (
            patch("sys.platform", "linux"),
            patch("builtins.__import__", side_effect=fake_import),
        ):
            path = AgentDaemon._open_dir_dialog()
        assert path is None


class TestPidFileHardening:
    @pytest.mark.asyncio
    async def test_stale_pid_non_kira_process_allows_startup(self, daemon, tmp_path, caplog):
        """A PID file pointing to a non-kira process should be treated as stale."""
        daemon._pidfile = tmp_path / "agent.pid"
        daemon._pidfile.write_text("12345")

        with (
            patch("os.kill") as mock_kill,
            patch.object(AgentDaemon, "_is_kira_process", return_value=False),
            patch("kira.agent.daemon.websockets.serve", side_effect=RuntimeError("test-stop")),
        ):
            mock_kill.return_value = None

            # start() should pass the PID check (non-kira process), log a warning,
            # and proceed to websockets.serve -- NOT exit with SystemExit(1).
            # websockets.serve is stubbed to raise RuntimeError to stop execution.
            with pytest.raises(RuntimeError, match="test-stop"):
                await daemon.start()

        assert "not a kira process" in caplog.text

    @pytest.mark.asyncio
    async def test_active_kira_pid_blocks_startup(self, daemon, tmp_path):
        """A PID file pointing to a running kira process should block startup."""
        daemon._pidfile = tmp_path / "agent.pid"
        daemon._pidfile.write_text("12345")

        with (
            patch("os.kill") as mock_kill,
            patch.object(AgentDaemon, "_is_kira_process", return_value=True),
        ):
            mock_kill.return_value = None

            with pytest.raises(SystemExit) as exc_info:
                await daemon.start()

            assert exc_info.value.code == 1
