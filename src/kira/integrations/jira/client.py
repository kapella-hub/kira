"""Jira API client for creating and managing issues.

Supports Charter Jira Server (API v2) at https://jira.charter.com
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import IssueType, JiraConfig, JiraIssue


class JiraError(Exception):
    """Raised when Jira API request fails."""

    def __init__(self, message: str, status_code: int = 0, response: str = ""):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class JiraClient:
    """Client for Jira REST API v2 (Jira Server/Data Center).

    Default server: https://jira.charter.com
    Uses Basic Auth with username + password/token.
    """

    # Default Charter Jira server
    DEFAULT_SERVER = "https://jira.charter.com"

    def __init__(self, config: JiraConfig | None = None):
        self.config = config or JiraConfig.load()
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate that required config is present."""
        if not self.config.is_configured():
            raise JiraError(
                "Jira not configured. Run '/jira setup' or set environment variables:\n"
                "  JIRA_SERVER, JIRA_USERNAME, JIRA_PASSWORD"
            )

    def _get_auth_header(self) -> str:
        """Get Basic Auth header value."""
        # For Jira Server: username + password/token
        credentials = f"{self.config.username}:{self.config.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
    ) -> dict[str, Any]:
        """Make authenticated request to Jira API v2."""
        server = self.config.server or self.DEFAULT_SERVER
        url = f"{server.rstrip('/')}/rest/api/2/{endpoint.lstrip('/')}"

        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = json.dumps(data).encode() if data else None

        request = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read().decode()
                if response_body:
                    return json.loads(response_body)
                return {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            # Try to parse error message from Jira
            try:
                error_data = json.loads(error_body)
                errors = error_data.get("errorMessages", [])
                field_errors = error_data.get("errors", {})
                error_msg = "; ".join(errors) if errors else str(field_errors)
            except json.JSONDecodeError:
                error_msg = error_body[:200] if error_body else str(e)

            raise JiraError(
                f"Jira API error: {error_msg}",
                status_code=e.code,
                response=error_body,
            ) from e
        except urllib.error.URLError as e:
            raise JiraError(f"Connection error: {e.reason}") from e

    def test_connection(self) -> dict[str, Any]:
        """Test connection and return current user info."""
        return self._request("GET", "myself")

    def create_issue(
        self,
        summary: str,
        description: str = "",
        project: str | None = None,
        issue_type: IssueType | str = IssueType.TASK,
        labels: list[str] | None = None,
        assignee: str | None = None,
        priority: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> JiraIssue:
        """Create a new Jira issue.

        Args:
            summary: Issue title/summary (required)
            description: Issue description (plain text)
            project: Project key (uses default if not specified)
            issue_type: Issue type (Task, Bug, Story, etc.)
            labels: List of labels to add
            assignee: Assignee username
            priority: Priority name (e.g., "High", "Medium", "Low")
            custom_fields: Dict of custom field IDs to values

        Returns:
            Created JiraIssue with key and URL
        """
        # Use defaults if not specified
        project = project or self.config.default_project
        if not project:
            raise JiraError("No project specified and no default project configured")

        if isinstance(issue_type, str):
            issue_type = IssueType.from_string(issue_type)

        # Merge labels with defaults
        all_labels = list(self.config.default_labels)
        if labels:
            all_labels.extend(labels)
        # Remove duplicates while preserving order
        all_labels = list(dict.fromkeys(all_labels))

        issue = JiraIssue(
            summary=summary,
            description=description,
            project=project,
            issue_type=issue_type,
            labels=all_labels,
            assignee=assignee,
            priority=priority,
        )

        # Build payload for API v2 (plain text, not ADF)
        payload = issue.to_api_payload_v2()

        # Add custom fields if provided
        if custom_fields:
            payload["fields"].update(custom_fields)

        response = self._request("POST", "issue", payload)

        # Update issue with response data
        issue.key = response.get("key", "")
        issue.id = response.get("id", "")
        issue.self_url = response.get("self", "")
        server = self.config.server or self.DEFAULT_SERVER
        issue.browse_url = f"{server.rstrip('/')}/browse/{issue.key}"

        return issue

    def get_issue(self, issue_key: str, fields: str | None = None) -> JiraIssue:
        """Get an existing issue by key.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            fields: Comma-separated list of fields to return (optional)
        """
        endpoint = f"issue/{issue_key}"
        if fields:
            endpoint += f"?fields={fields}"
        response = self._request("GET", endpoint)
        server = self.config.server or self.DEFAULT_SERVER
        return JiraIssue.from_api_response(response, server)

    def add_comment(self, issue_key: str, comment: str) -> dict:
        """Add a comment to an existing issue.

        Uses API v2 plain text format.
        """
        data = {"body": comment}
        return self._request("POST", f"issue/{issue_key}/comment", data)

    def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
        update: dict[str, Any] | None = None,
    ) -> None:
        """Update an existing issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            fields: Fields to set directly
            update: Update operations (add/remove labels, etc.)
        """
        data = {}
        if fields:
            data["fields"] = fields
        if update:
            data["update"] = update

        if data:
            self._request("PUT", f"issue/{issue_key}", data)

    def add_label(self, issue_key: str, label: str) -> None:
        """Add a label to an issue."""
        self.update_issue(issue_key, update={"labels": [{"add": label}]})

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> None:
        """Perform a transition on an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            transition_id: Transition ID
            comment: Optional comment to add
            fields: Optional fields to update during transition
        """
        data: dict[str, Any] = {"transition": {"id": transition_id}}

        if comment:
            data["update"] = {"comment": [{"add": {"body": comment}}]}

        if fields:
            data["fields"] = fields

        self._request("POST", f"issue/{issue_key}/transitions", data)

    def get_projects(self) -> list[dict]:
        """Get list of accessible projects."""
        response = self._request("GET", "project")
        return response if isinstance(response, list) else []

    def search_issues(
        self,
        jql: str,
        fields: str = "summary,status,issuetype,project,labels",
        max_results: int = 50,
    ) -> list[JiraIssue]:
        """Search issues using JQL.

        Args:
            jql: JQL query string
            fields: Comma-separated list of fields to return
            max_results: Maximum number of results
        """
        # Use GET with query params for search
        endpoint = f"search?jql={urllib.parse.quote(jql)}&fields={fields}&maxResults={max_results}"
        response = self._request("GET", endpoint)
        issues = response.get("issues", [])
        server = self.config.server or self.DEFAULT_SERVER
        return [JiraIssue.from_api_response(i, server) for i in issues]

    def link_issues(
        self,
        inward_key: str,
        outward_key: str,
        link_type: str = "Relates",
        comment: str | None = None,
    ) -> None:
        """Create a link between two issues.

        Args:
            inward_key: Inward issue key
            outward_key: Outward issue key
            link_type: Link type name (e.g., "Relates", "Blocks", "Clones")
            comment: Optional comment
        """
        data: dict[str, Any] = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        }

        if comment:
            data["comment"] = {"body": comment}

        self._request("POST", "issueLink", data)

    def get_issue_types(self, project_key: str) -> list[dict]:
        """Get available issue types for a project."""
        response = self._request("GET", f"issue/createmeta/{project_key}/issuetypes")
        return response.get("values", []) if isinstance(response, dict) else []
