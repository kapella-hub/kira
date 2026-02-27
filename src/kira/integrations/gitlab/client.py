"""GitLab API client for project management and CI/CD operations.

Supports GitLab self-hosted and GitLab.com (API v4).
"""

from __future__ import annotations

from typing import Any

import httpx


class GitLabError(Exception):
    """Raised when a GitLab API request fails."""

    def __init__(self, message: str, status_code: int = 0, response: str = ""):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class GitLabClient:
    """Client for GitLab REST API v4.

    Uses Personal Access Token (PAT) for authentication.
    """

    def __init__(self, server: str, token: str):
        self.base_url = server.rstrip("/")
        self.token = token
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v4",
            headers={
                "PRIVATE-TOKEN": token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated request to the GitLab API.

        Returns parsed JSON response (dict or list).

        Raises:
            GitLabError: On HTTP errors or connection failures.
        """
        try:
            response = self._client.request(
                method,
                endpoint,
                params=params,
                json=json,
            )

            if response.status_code >= 400:
                detail = ""
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        detail = body.get("message", body.get("error", str(body)))
                    else:
                        detail = str(body)
                except Exception:
                    detail = response.text[:200]

                raise GitLabError(
                    f"GitLab API error: {detail}",
                    status_code=response.status_code,
                    response=response.text[:500],
                )

            if not response.content:
                return {}

            return response.json()

        except httpx.ConnectError as e:
            raise GitLabError(f"Cannot connect to GitLab: {e}") from e
        except httpx.TimeoutException as e:
            raise GitLabError(f"Request timed out: {method} {endpoint}") from e
        except GitLabError:
            raise
        except Exception as e:
            raise GitLabError(f"Unexpected error: {e}") from e

    def test_connection(self) -> dict:
        """Test connection and return current user info.

        GET /api/v4/user

        Returns:
            Dict with user info (id, username, name, email, etc.)
        """
        return self._request("GET", "/user")

    def list_projects(self, search: str = "") -> list[dict]:
        """List projects the authenticated user is a member of.

        GET /api/v4/projects?membership=true&search=...

        Args:
            search: Optional search term to filter projects.

        Returns:
            List of project dicts.
        """
        params: dict[str, Any] = {"membership": "true", "per_page": 50}
        if search:
            params["search"] = search
        return self._request("GET", "/projects", params=params)

    def list_namespaces(self) -> list[dict]:
        """List namespaces available to the authenticated user.

        GET /api/v4/namespaces

        Returns:
            List of namespace dicts.
        """
        return self._request("GET", "/namespaces")

    def get_project(self, project_id: int) -> dict:
        """Get a project by ID.

        GET /api/v4/projects/{id}

        Args:
            project_id: GitLab project ID.

        Returns:
            Project dict.
        """
        return self._request("GET", f"/projects/{project_id}")

    def create_project(
        self,
        name: str,
        namespace_id: int | None = None,
        visibility: str = "private",
        description: str = "",
    ) -> dict:
        """Create a new project.

        POST /api/v4/projects

        Args:
            name: Project name.
            namespace_id: Namespace/group ID (optional, defaults to user namespace).
            visibility: Project visibility (private, internal, public).
            description: Project description.

        Returns:
            Created project dict.
        """
        data: dict[str, Any] = {
            "name": name,
            "visibility": visibility,
        }
        if namespace_id is not None:
            data["namespace_id"] = namespace_id
        if description:
            data["description"] = description

        return self._request("POST", "/projects", json=data)

    def create_branch(
        self,
        project_id: int,
        branch_name: str,
        ref: str = "main",
    ) -> dict:
        """Create a new branch in a project.

        POST /api/v4/projects/{id}/repository/branches

        Args:
            project_id: GitLab project ID.
            branch_name: Name for the new branch.
            ref: Source branch or commit SHA.

        Returns:
            Created branch dict.
        """
        return self._request(
            "POST",
            f"/projects/{project_id}/repository/branches",
            json={"branch": branch_name, "ref": ref},
        )

    def create_merge_request(
        self,
        project_id: int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
    ) -> dict:
        """Create a merge request.

        POST /api/v4/projects/{id}/merge_requests

        Args:
            project_id: GitLab project ID.
            source_branch: Source branch name.
            target_branch: Target branch name.
            title: MR title.
            description: MR description.

        Returns:
            Created merge request dict.
        """
        data: dict[str, Any] = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
        }
        if description:
            data["description"] = description

        return self._request("POST", f"/projects/{project_id}/merge_requests", json=data)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
