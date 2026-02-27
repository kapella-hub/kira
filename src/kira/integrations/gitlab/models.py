"""Data models for GitLab integration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class GitLabConfig:
    """GitLab connection configuration.

    Credentials are stored in ~/.kira/gitlab.yaml
    with restricted file permissions (600).
    """

    server: str = ""
    token: str = ""  # Personal Access Token

    CONFIG_FILE = Path.home() / ".kira" / "gitlab.yaml"

    def is_configured(self) -> bool:
        """Check if GitLab is properly configured."""
        return bool(self.server and self.token)

    @classmethod
    def load(cls) -> GitLabConfig:
        """Load GitLab config from secure file.

        Also supports environment variables:
        - GITLAB_SERVER (e.g., https://gitlab.example.com)
        - GITLAB_TOKEN (Personal Access Token)
        """
        config = cls()

        # Load from file if exists
        if cls.CONFIG_FILE.exists():
            try:
                with open(cls.CONFIG_FILE) as f:
                    data = yaml.safe_load(f) or {}

                config.server = data.get("server", "")
                config.token = data.get("token", "")
            except (yaml.YAMLError, OSError):
                pass

        # Environment variables override file config
        config.server = os.environ.get("GITLAB_SERVER", config.server)
        config.token = os.environ.get("GITLAB_TOKEN", config.token)

        return config

    def save(self) -> None:
        """Save config to secure file with restricted permissions."""
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "server": self.server,
            "token": self.token,
        }

        with open(self.CONFIG_FILE, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)

        # Set file permissions to owner read/write only (600)
        self.CONFIG_FILE.chmod(0o600)
