"""Data models for Jira integration.

Supports Charter Jira Server (API v2) at https://jira.charter.com
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml


class IssueType(Enum):
    """Standard Jira issue types."""

    TASK = "Task"
    BUG = "Bug"
    STORY = "Story"
    EPIC = "Epic"
    SUBTASK = "Sub-task"
    # Charter-specific types can be added or use string directly
    INTAKE_REQUEST = "Intake Request"

    @classmethod
    def from_string(cls, value: str) -> IssueType:
        """Parse issue type from string."""
        value_lower = value.lower()
        for issue_type in cls:
            if issue_type.value.lower() == value_lower:
                return issue_type
        return cls.TASK  # Default


@dataclass
class JiraConfig:
    """Jira Server connection configuration.

    Default server: https://jira.charter.com
    Credentials are stored securely in ~/.kira/jira.yaml
    with restricted file permissions (600).
    """

    server: str = "https://jira.charter.com"
    username: str = ""
    password: str = ""  # Can be password or API token
    default_project: str = ""
    default_issue_type: IssueType = IssueType.TASK
    default_labels: list[str] = field(default_factory=list)

    # Path to secure config file
    CONFIG_FILE = Path.home() / ".kira" / "jira.yaml"

    def is_configured(self) -> bool:
        """Check if Jira is properly configured."""
        return bool(self.server and self.username and self.password)

    @classmethod
    def load(cls) -> JiraConfig:
        """Load Jira config from secure file.

        Also supports environment variables:
        - JIRA_SERVER (default: https://jira.charter.com)
        - JIRA_USERNAME
        - JIRA_PASSWORD
        - JIRA_PROJECT
        """
        config = cls()

        # Load from file if exists
        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE) as f:
                    data = yaml.safe_load(f) or {}

                config.server = data.get("server", config.server)
                config.username = data.get("username", "")
                config.password = data.get("password", "")
                config.default_project = data.get("default_project", "")

                issue_type = data.get("default_issue_type", "Task")
                config.default_issue_type = IssueType.from_string(issue_type)

                config.default_labels = data.get("default_labels", [])
            except (yaml.YAMLError, OSError):
                pass

        # Environment variables override file config
        config.server = os.environ.get("JIRA_SERVER", config.server)
        config.username = os.environ.get("JIRA_USERNAME", config.username)
        config.password = os.environ.get("JIRA_PASSWORD", config.password)
        config.default_project = os.environ.get("JIRA_PROJECT", config.default_project)

        return config

    def save(self) -> None:
        """Save config to secure file with restricted permissions."""
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "server": self.server,
            "username": self.username,
            "password": self.password,
            "default_project": self.default_project,
            "default_issue_type": self.default_issue_type.value,
            "default_labels": self.default_labels,
        }

        # Write with restricted permissions
        with open(self.CONFIG_FILE, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)

        # Set file permissions to owner read/write only (600)
        self.CONFIG_FILE.chmod(0o600)


@dataclass
class JiraIssue:
    """Represents a Jira issue."""

    key: str = ""  # e.g., "PROJ-123"
    summary: str = ""
    description: str = ""
    issue_type: IssueType = IssueType.TASK
    project: str = ""
    labels: list[str] = field(default_factory=list)
    assignee: str | None = None
    priority: str | None = None
    status: str = ""

    # Response fields
    id: str = ""
    self_url: str = ""
    browse_url: str = ""

    def to_api_payload_v2(self) -> dict:
        """Convert to Jira API v2 create issue payload (plain text format)."""
        fields: dict = {
            "project": {"key": self.project},
            "summary": self.summary,
            "issuetype": {"name": self.issue_type.value},
        }

        # API v2 uses plain text for description
        if self.description:
            fields["description"] = self.description

        if self.labels:
            fields["labels"] = self.labels

        # Jira Server uses username for assignee, not accountId
        if self.assignee:
            fields["assignee"] = {"name": self.assignee}

        if self.priority:
            fields["priority"] = {"name": self.priority}

        return {"fields": fields}

    def to_api_payload(self) -> dict:
        """Alias for to_api_payload_v2 (API v2 is default)."""
        return self.to_api_payload_v2()

    @classmethod
    def from_api_response(cls, data: dict, server: str = "") -> JiraIssue:
        """Create JiraIssue from API response."""
        fields = data.get("fields", {})

        # Get status
        status_data = fields.get("status", {})
        status = status_data.get("name", "") if isinstance(status_data, dict) else ""

        # Get assignee (username in API v2)
        assignee_data = fields.get("assignee", {})
        assignee = assignee_data.get("name", "") if isinstance(assignee_data, dict) else None

        issue = cls(
            key=data.get("key", ""),
            id=data.get("id", ""),
            self_url=data.get("self", ""),
            summary=fields.get("summary", ""),
            description=fields.get("description", ""),
            project=fields.get("project", {}).get("key", ""),
            labels=fields.get("labels", []),
            status=status,
            assignee=assignee,
        )

        # Parse issue type
        issue_type_data = fields.get("issuetype", {})
        if issue_type_data:
            issue.issue_type = IssueType.from_string(issue_type_data.get("name", "Task"))

        # Build browse URL
        if server and issue.key:
            issue.browse_url = f"{server.rstrip('/')}/browse/{issue.key}"

        return issue
