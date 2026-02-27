"""Tests for WorkerConfig loading and saving."""

from __future__ import annotations

import yaml

from kira.worker.config import WorkerConfig


class TestWorkerConfigDefaults:
    """Test default config values."""

    def test_defaults(self):
        config = WorkerConfig()
        assert config.server_url == "http://localhost:8000"
        assert config.token == ""
        assert config.poll_interval == 5.0
        assert config.heartbeat_interval == 30.0
        assert config.max_concurrent_tasks == 1
        assert config.kiro_timeout == 600


class TestWorkerConfigLoad:
    """Test loading config from file and environment."""

    def test_load_from_nonexistent_file_uses_defaults(self, tmp_path):
        config = WorkerConfig.load(config_path=tmp_path / "nonexistent.yaml")
        assert config.server_url == "http://localhost:8000"
        assert config.poll_interval == 5.0

    def test_load_from_yaml_file(self, tmp_path):
        config_file = tmp_path / "worker.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "server_url": "http://kira.internal:9000",
                    "poll_interval": 10.0,
                    "heartbeat_interval": 60.0,
                    "max_concurrent_tasks": 3,
                    "kiro_timeout": 300,
                }
            )
        )

        config = WorkerConfig.load(config_path=config_file)
        assert config.server_url == "http://kira.internal:9000"
        assert config.poll_interval == 10.0
        assert config.heartbeat_interval == 60.0
        assert config.max_concurrent_tasks == 3
        assert config.kiro_timeout == 300

    def test_env_vars_override_file(self, tmp_path, monkeypatch):
        config_file = tmp_path / "worker.yaml"
        config_file.write_text(yaml.safe_dump({"server_url": "http://from-file:8000"}))

        monkeypatch.setenv("KIRA_SERVER_URL", "http://from-env:9000")
        monkeypatch.setenv("KIRA_POLL_INTERVAL", "15.0")
        monkeypatch.setenv("KIRA_KIRO_TIMEOUT", "120")

        config = WorkerConfig.load(config_path=config_file)
        assert config.server_url == "http://from-env:9000"
        assert config.poll_interval == 15.0
        assert config.kiro_timeout == 120

    def test_env_vars_without_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KIRA_SERVER_URL", "http://env-only:8000")
        monkeypatch.setenv("KIRA_WORKER_TOKEN", "jwt-token-123")

        config = WorkerConfig.load(config_path=tmp_path / "nonexistent.yaml")
        assert config.server_url == "http://env-only:8000"
        assert config.token == "jwt-token-123"

    def test_load_handles_malformed_yaml(self, tmp_path):
        config_file = tmp_path / "worker.yaml"
        config_file.write_text("this is: not: valid: yaml: [[[")

        # Should not raise, just use defaults
        config = WorkerConfig.load(config_path=config_file)
        assert config.server_url == "http://localhost:8000"

    def test_partial_yaml_file(self, tmp_path):
        config_file = tmp_path / "worker.yaml"
        config_file.write_text(yaml.safe_dump({"poll_interval": 2.5}))

        config = WorkerConfig.load(config_path=config_file)
        assert config.poll_interval == 2.5
        # Other values should be defaults
        assert config.server_url == "http://localhost:8000"
        assert config.max_concurrent_tasks == 1


class TestWorkerConfigSave:
    """Test saving config to file."""

    def test_save_creates_file(self, tmp_path):
        config = WorkerConfig(
            server_url="http://test:8000",
            poll_interval=7.5,
        )
        config_file = tmp_path / "worker.yaml"
        config.save(config_path=config_file)

        assert config_file.exists()
        data = yaml.safe_load(config_file.read_text())
        assert data["server_url"] == "http://test:8000"
        assert data["poll_interval"] == 7.5

    def test_save_creates_parent_directories(self, tmp_path):
        config = WorkerConfig()
        config_file = tmp_path / "deep" / "nested" / "worker.yaml"
        config.save(config_path=config_file)

        assert config_file.exists()

    def test_roundtrip(self, tmp_path):
        config_file = tmp_path / "worker.yaml"

        original = WorkerConfig(
            server_url="http://roundtrip:8000",
            poll_interval=3.0,
            heartbeat_interval=45.0,
            max_concurrent_tasks=2,
            kiro_timeout=900,
        )
        original.save(config_path=config_file)

        loaded = WorkerConfig.load(config_path=config_file)
        assert loaded.server_url == original.server_url
        assert loaded.poll_interval == original.poll_interval
        assert loaded.heartbeat_interval == original.heartbeat_interval
        assert loaded.max_concurrent_tasks == original.max_concurrent_tasks
        assert loaded.kiro_timeout == original.kiro_timeout
