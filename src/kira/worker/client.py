"""HTTP client for communicating with the Kira server.

Wraps all worker-to-server API calls: auth, registration, heartbeat,
task polling, progress reporting, and card creation.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ServerError(Exception):
    """Raised when a server API call fails."""

    def __init__(self, message: str, status_code: int = 0, detail: str = ""):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class ServerClient:
    """HTTP client for the Kira server API.

    All methods are async and raise ServerError on failure.
    """

    def __init__(self, base_url: str, token: str = ""):
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(30.0),
        )

    def set_token(self, token: str) -> None:
        """Update the authorization token after login."""
        self._client.headers["Authorization"] = f"Bearer {token}"

    # --- Auth ---

    async def login(self, username: str, password: str = "") -> dict[str, Any]:
        """Authenticate with the server.

        POST /api/auth/login

        Args:
            username: Username to log in as.
            password: Password (required for CentAuth mode, ignored in mock mode).

        Returns:
            Dict with 'token' and 'user' keys.

        Raises:
            ServerError: On auth failure.
        """
        response = await self._request(
            "POST",
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        return response

    async def get_auth_config(self) -> dict[str, Any]:
        """Fetch server auth configuration.

        GET /api/auth/config

        Returns:
            Dict with 'auth_mode' and 'demo_users' keys.
        """
        return await self._request("GET", "/api/auth/config")

    # --- Worker lifecycle ---

    async def register_worker(
        self,
        hostname: str,
        version: str,
        capabilities: list[str],
    ) -> dict[str, Any]:
        """Register this worker with the server.

        POST /api/workers/register

        Returns:
            Dict with 'worker_id', 'max_concurrent_tasks', etc.
        """
        return await self._request(
            "POST",
            "/api/workers/register",
            json={
                "hostname": hostname,
                "worker_version": version,
                "capabilities": capabilities,
            },
        )

    async def heartbeat(
        self,
        worker_id: str,
        running_task_ids: list[str],
        system_load: float = 0.0,
    ) -> dict[str, Any]:
        """Send a heartbeat to the server.

        POST /api/workers/heartbeat

        Returns:
            Dict with 'status' and 'directives' keys.
        """
        return await self._request(
            "POST",
            "/api/workers/heartbeat",
            json={
                "worker_id": worker_id,
                "running_task_ids": running_task_ids,
                "system_load": system_load,
            },
        )

    # --- Task operations ---

    async def poll_tasks(self, worker_id: str, limit: int = 1) -> list[dict[str, Any]]:
        """Poll for pending tasks assigned to this worker's user.

        GET /api/workers/tasks/poll?worker_id=X&limit=N

        Returns:
            List of task dicts (may be empty).
        """
        response = await self._request(
            "GET",
            "/api/workers/tasks/poll",
            params={"worker_id": worker_id, "limit": limit},
        )
        # Poll endpoint returns a flat list of tasks
        if isinstance(response, list):
            return response
        return response.get("tasks", [])

    async def claim_task(self, task_id: str, worker_id: str) -> dict[str, Any]:
        """Claim a task before executing it.

        POST /api/workers/tasks/{task_id}/claim

        Returns:
            Dict with 'status' and 'task' keys.

        Raises:
            ServerError: 409 if task already claimed by another worker.
        """
        return await self._request(
            "POST",
            f"/api/workers/tasks/{task_id}/claim",
            json={"worker_id": worker_id},
        )

    async def report_progress(
        self,
        task_id: str,
        worker_id: str,
        progress_text: str,
        *,
        step: int | None = None,
        total_steps: int | None = None,
        phase: str | None = None,
    ) -> dict[str, Any]:
        """Report task execution progress.

        POST /api/workers/tasks/{task_id}/progress

        Args:
            task_id: Task being reported on.
            worker_id: Worker making the report.
            progress_text: Human-readable progress message.
            step: Current step number (1-based).
            total_steps: Total number of steps.
            phase: Named phase (e.g. "analyzing", "thinking").

        Returns:
            Dict with 'status' key.
        """
        body: dict[str, Any] = {
            "worker_id": worker_id,
            "status": "running",
            "progress_text": progress_text,
        }
        if step is not None:
            body["step"] = step
        if total_steps is not None:
            body["total_steps"] = total_steps
        if phase is not None:
            body["phase"] = phase

        return await self._request(
            "POST",
            f"/api/workers/tasks/{task_id}/progress",
            json=body,
        )

    async def complete_task(
        self,
        task_id: str,
        worker_id: str,
        output_text: str,
        result_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Report successful task completion.

        POST /api/workers/tasks/{task_id}/complete

        Returns:
            Dict with 'status' and 'next_action' keys.
        """
        return await self._request(
            "POST",
            f"/api/workers/tasks/{task_id}/complete",
            json={
                "worker_id": worker_id,
                "output_text": output_text,
                "result_data": result_data or {},
            },
        )

    async def fail_task(
        self,
        task_id: str,
        worker_id: str,
        error_summary: str,
        output_text: str = "",
    ) -> dict[str, Any]:
        """Report task failure.

        POST /api/workers/tasks/{task_id}/fail

        Returns:
            Dict with 'status' and 'next_action' keys.
        """
        return await self._request(
            "POST",
            f"/api/workers/tasks/{task_id}/fail",
            json={
                "worker_id": worker_id,
                "error_summary": error_summary,
                "output_text": output_text,
            },
        )

    # --- Board settings ---

    async def get_board_settings(self, board_id: str) -> dict[str, Any]:
        """Fetch board settings for workspace resolution.

        GET /api/boards/{board_id}/settings

        Returns:
            Parsed settings_json dict.
        """
        return await self._request("GET", f"/api/boards/{board_id}/settings")

    # --- Card operations (used by Jira import to create cards) ---

    async def create_card(
        self,
        column_id: str,
        title: str,
        description: str = "",
        priority: str = "medium",
        labels: str = "[]",
    ) -> dict[str, Any]:
        """Create a card via the server API.

        POST /api/cards

        Used by the Jira executor to import issues as cards.

        Returns:
            Created card dict.
        """
        return await self._request(
            "POST",
            "/api/cards",
            json={
                "column_id": column_id,
                "title": title,
                "description": description,
                "priority": priority,
                "labels": labels,
            },
        )

    # --- Board/Column operations (used by PlannerExecutor) ---

    async def create_column(
        self,
        board_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a column on a board.

        POST /api/boards/{board_id}/columns

        Returns:
            Created column dict.
        """
        return await self._request(
            "POST",
            f"/api/boards/{board_id}/columns",
            json=data,
        )

    async def update_board(
        self,
        board_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update board name/description.

        PATCH /api/boards/{board_id}

        Returns:
            Updated board dict.
        """
        return await self._request(
            "PATCH",
            f"/api/boards/{board_id}",
            json=data,
        )

    async def update_column(
        self,
        column_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update column settings (e.g., automation routing).

        PATCH /api/columns/{column_id}

        Returns:
            Updated column dict.
        """
        return await self._request(
            "PATCH",
            f"/api/columns/{column_id}",
            json=data,
        )

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # --- Internal ---

    async def _request(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the server.

        Raises:
            ServerError: On HTTP errors or connection failures.
        """
        try:
            response = await self._client.request(
                method,
                url,
                json=json,
                params=params,
            )

            if response.status_code >= 400:
                detail = ""
                try:
                    body = response.json()
                    detail = body.get("detail", str(body))
                except Exception:
                    detail = response.text[:200]

                raise ServerError(
                    f"{method} {url} returned {response.status_code}: {detail}",
                    status_code=response.status_code,
                    detail=detail,
                )

            # Handle empty responses
            if not response.content:
                return {}

            return response.json()

        except httpx.ConnectError as e:
            raise ServerError(
                f"Cannot connect to server: {e}",
                detail=str(e),
            ) from e
        except httpx.TimeoutException as e:
            raise ServerError(
                f"Request timed out: {method} {url}",
                detail=str(e),
            ) from e
        except ServerError:
            raise
        except Exception as e:
            raise ServerError(
                f"Unexpected error: {e}",
                detail=str(e),
            ) from e
