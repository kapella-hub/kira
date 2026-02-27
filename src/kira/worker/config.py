"""Worker configuration.

Loads from ~/.kira/worker.yaml with environment variable overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class WorkerConfig:
    """Configuration for the local worker process."""

    server_url: str = "http://localhost:8000"
    token: str = ""  # JWT token, set after login
    password: str = ""  # CentAuth password, loaded from env only (never saved)
    poll_interval: float = 5.0  # seconds between task polls
    heartbeat_interval: float = 30.0  # seconds between heartbeats
    max_concurrent_tasks: int = 1
    kiro_timeout: int = 600  # kiro-cli subprocess timeout in seconds
    workspace_root: Path = field(
        default_factory=lambda: Path.home() / ".kira" / "workspaces",
    )

    CONFIG_FILE: Path = field(
        default_factory=lambda: Path.home() / ".kira" / "worker.yaml",
        repr=False,
    )

    @classmethod
    def load(cls, config_path: Path | None = None) -> WorkerConfig:
        """Load worker config from file and environment variables.

        Priority (highest wins):
          1. Environment variables (KIRA_SERVER_URL, KIRA_WORKER_TOKEN, etc.)
          2. Config file (~/.kira/worker.yaml or custom path)
          3. Defaults

        Args:
            config_path: Optional path to a YAML config file.

        Returns:
            Populated WorkerConfig instance.
        """
        config = cls()
        file_path = config_path or config.CONFIG_FILE

        # Load from file if it exists
        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = yaml.safe_load(f) or {}

                config.server_url = data.get("server_url", config.server_url)
                config.poll_interval = float(data.get("poll_interval", config.poll_interval))
                config.heartbeat_interval = float(
                    data.get("heartbeat_interval", config.heartbeat_interval)
                )
                config.max_concurrent_tasks = int(
                    data.get("max_concurrent_tasks", config.max_concurrent_tasks)
                )
                config.kiro_timeout = int(data.get("kiro_timeout", config.kiro_timeout))
                if "workspace_root" in data:
                    config.workspace_root = Path(data["workspace_root"]).expanduser()
            except (yaml.YAMLError, OSError, ValueError):
                pass

        # Environment variables override file config
        config.server_url = os.environ.get("KIRA_SERVER_URL", config.server_url)
        config.token = os.environ.get("KIRA_WORKER_TOKEN", config.token)
        config.password = os.environ.get("KIRA_WORKER_PASSWORD", config.password)

        if env_poll := os.environ.get("KIRA_POLL_INTERVAL"):
            config.poll_interval = float(env_poll)
        if env_heartbeat := os.environ.get("KIRA_HEARTBEAT_INTERVAL"):
            config.heartbeat_interval = float(env_heartbeat)
        if env_concurrent := os.environ.get("KIRA_MAX_CONCURRENT_TASKS"):
            config.max_concurrent_tasks = int(env_concurrent)
        if env_timeout := os.environ.get("KIRA_KIRO_TIMEOUT"):
            config.kiro_timeout = int(env_timeout)
        if env_workspace := os.environ.get("KIRA_WORKSPACE_ROOT"):
            config.workspace_root = Path(env_workspace).expanduser()

        return config

    def save(self, config_path: Path | None = None) -> None:
        """Save current config to file.

        Args:
            config_path: Optional path override.
        """
        file_path = config_path or self.CONFIG_FILE
        file_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "server_url": self.server_url,
            "poll_interval": self.poll_interval,
            "heartbeat_interval": self.heartbeat_interval,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "kiro_timeout": self.kiro_timeout,
            "workspace_root": str(self.workspace_root),
        }

        with open(file_path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)
