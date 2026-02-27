"""Tests for the agent system service installer."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from kira.agent.service import (
    LINUX_SERVICE_NAME,
    MACOS_PLIST_NAME,
    is_installed,
)


class TestIsInstalled:
    def test_macos_installed_when_plist_exists(self, tmp_path):
        plist_path = tmp_path / "Library" / "LaunchAgents" / f"{MACOS_PLIST_NAME}.plist"
        plist_path.parent.mkdir(parents=True)
        plist_path.write_text("<plist/>")

        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service.platform.system", return_value="Darwin"),
        ):
            assert is_installed() is True

    def test_macos_not_installed_when_no_plist(self, tmp_path):
        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service.platform.system", return_value="Darwin"),
        ):
            assert is_installed() is False

    def test_linux_installed_when_unit_exists(self, tmp_path):
        unit_path = tmp_path / ".config" / "systemd" / "user" / f"{LINUX_SERVICE_NAME}.service"
        unit_path.parent.mkdir(parents=True)
        unit_path.write_text("[Unit]\n")

        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service.platform.system", return_value="Linux"),
        ):
            assert is_installed() is True

    def test_linux_not_installed_when_no_unit(self, tmp_path):
        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service.platform.system", return_value="Linux"),
        ):
            assert is_installed() is False

    def test_unsupported_platform_returns_false(self):
        with patch("kira.agent.service.platform.system", return_value="Windows"):
            assert is_installed() is False


class TestGetKiraPath:
    def test_raises_when_kira_not_found(self):
        from kira.agent.service import _get_kira_path

        with (
            patch("kira.agent.service.shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="'kira' not found in PATH"),
        ):
            _get_kira_path()

    def test_returns_path_when_found(self):
        from kira.agent.service import _get_kira_path

        with patch("kira.agent.service.shutil.which", return_value="/usr/local/bin/kira"):
            assert _get_kira_path() == "/usr/local/bin/kira"


class TestInstallUninstallMessages:
    def test_install_unsupported_platform(self):
        from kira.agent.service import install

        with patch("kira.agent.service.platform.system", return_value="Windows"):
            result = install()
        assert "Unsupported platform" in result

    def test_uninstall_unsupported_platform(self):
        from kira.agent.service import uninstall

        with patch("kira.agent.service.platform.system", return_value="Windows"):
            result = uninstall()
        assert "Unsupported platform" in result

    def test_uninstall_macos_not_installed(self, tmp_path):
        from kira.agent.service import _uninstall_macos

        with patch("kira.agent.service.Path.home", return_value=tmp_path):
            result = _uninstall_macos()
        assert "not installed" in result

    def test_uninstall_linux_not_installed(self, tmp_path):
        from kira.agent.service import _uninstall_linux

        with patch("kira.agent.service.Path.home", return_value=tmp_path):
            result = _uninstall_linux()
        assert "not installed" in result


class TestMacOsPlistContent:
    def test_keepalive_uses_successful_exit_dict(self, tmp_path):
        """Plist should use conditional KeepAlive (restart on crash, not on clean exit)."""
        from kira.agent.service import _install_macos

        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service._get_kira_path", return_value="/usr/local/bin/kira"),
            patch("kira.agent.service._get_user_path", return_value="/usr/local/bin:/usr/bin"),
            patch("kira.agent.service.subprocess.run"),
        ):
            _install_macos()

        plist_path = tmp_path / "Library" / "LaunchAgents" / f"{MACOS_PLIST_NAME}.plist"
        content = plist_path.read_text()

        # Should have the conditional KeepAlive dict, not bare <true/>
        assert "<key>KeepAlive</key>" in content
        assert "<key>SuccessfulExit</key>" in content
        assert "<false/>" in content
        # Should NOT have the old bare <true/> for KeepAlive
        # (Check that <true/> only appears for RunAtLoad, not KeepAlive)
        keepalive_idx = content.index("<key>KeepAlive</key>")
        throttle_idx = content.index("<key>ThrottleInterval</key>")
        keepalive_section = content[keepalive_idx:throttle_idx]
        assert "<true/>" not in keepalive_section

    def test_throttle_interval_is_5_seconds(self, tmp_path):
        """Plist should have ThrottleInterval of 5 seconds for fast crash recovery."""
        from kira.agent.service import _install_macos

        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service._get_kira_path", return_value="/usr/local/bin/kira"),
            patch("kira.agent.service._get_user_path", return_value="/usr/local/bin:/usr/bin"),
            patch("kira.agent.service.subprocess.run"),
        ):
            _install_macos()

        plist_path = tmp_path / "Library" / "LaunchAgents" / f"{MACOS_PLIST_NAME}.plist"
        content = plist_path.read_text()

        assert "<key>ThrottleInterval</key>" in content
        assert "<integer>5</integer>" in content


class TestLinuxUnitContent:
    def test_restart_always(self, tmp_path):
        """Systemd unit should use Restart=always."""
        from kira.agent.service import _install_linux

        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service._get_kira_path", return_value="/usr/local/bin/kira"),
            patch("kira.agent.service._get_user_path", return_value="/usr/local/bin:/usr/bin"),
            patch("kira.agent.service.subprocess.run"),
        ):
            _install_linux()

        unit_path = tmp_path / ".config" / "systemd" / "user" / f"{LINUX_SERVICE_NAME}.service"
        content = unit_path.read_text()

        assert "Restart=always" in content
        assert "Restart=on-failure" not in content

    def test_restart_rate_limiting(self, tmp_path):
        """Systemd unit should have rate-limiting directives."""
        from kira.agent.service import _install_linux

        with (
            patch("kira.agent.service.Path.home", return_value=tmp_path),
            patch("kira.agent.service._get_kira_path", return_value="/usr/local/bin/kira"),
            patch("kira.agent.service._get_user_path", return_value="/usr/local/bin:/usr/bin"),
            patch("kira.agent.service.subprocess.run"),
        ):
            _install_linux()

        unit_path = tmp_path / ".config" / "systemd" / "user" / f"{LINUX_SERVICE_NAME}.service"
        content = unit_path.read_text()

        assert "RestartSec=5" in content
        assert "StartLimitIntervalSec=300" in content
        assert "StartLimitBurst=20" in content
