"""System service installer for the Kira agent."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

MACOS_PLIST_NAME = "com.kira.agent"
LINUX_SERVICE_NAME = "kira-agent"


def install() -> str:
    """Install agent as a system service. Returns status message."""
    system = platform.system()
    if system == "Darwin":
        return _install_macos()
    elif system == "Linux":
        return _install_linux()
    else:
        return f"Unsupported platform: {system}"


def uninstall() -> str:
    """Remove agent system service. Returns status message."""
    system = platform.system()
    if system == "Darwin":
        return _uninstall_macos()
    elif system == "Linux":
        return _uninstall_linux()
    else:
        return f"Unsupported platform: {system}"


def is_installed() -> bool:
    """Check if the agent service is installed."""
    system = platform.system()
    if system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{MACOS_PLIST_NAME}.plist"
        return plist_path.exists()
    elif system == "Linux":
        unit_path = Path.home() / ".config" / "systemd" / "user" / f"{LINUX_SERVICE_NAME}.service"
        return unit_path.exists()
    return False


def _get_kira_path() -> str:
    """Find the kira executable."""
    kira_path = shutil.which("kira")
    if not kira_path:
        raise RuntimeError("'kira' not found in PATH. Is it installed?")
    return kira_path


def _get_user_path() -> str:
    """Get the current PATH for the service environment."""
    return os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")


def _install_macos() -> str:
    kira_path = _get_kira_path()
    user_path = _get_user_path()
    home = str(Path.home())

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{MACOS_PLIST_NAME}.plist"

    log_path = Path.home() / ".kira" / "agent.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    plist_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MACOS_PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{kira_path}</string>
        <string>agent</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{user_path}</string>
        <key>HOME</key>
        <string>{home}</string>
    </dict>
</dict>
</plist>
"""

    plist_path.write_text(plist_content)

    # Load the service
    subprocess.run(
        ["launchctl", "load", str(plist_path)],
        check=True,
        capture_output=True,
    )

    return f"Agent service installed and started.\nPlist: {plist_path}\nLogs: {log_path}"


def _uninstall_macos() -> str:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{MACOS_PLIST_NAME}.plist"
    if not plist_path.exists():
        return "Agent service is not installed."

    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        check=False,
        capture_output=True,
    )
    plist_path.unlink(missing_ok=True)
    return "Agent service uninstalled."


def _install_linux() -> str:
    kira_path = _get_kira_path()
    user_path = _get_user_path()

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / f"{LINUX_SERVICE_NAME}.service"

    unit_content = f"""\
[Unit]
Description=Kira Agent Daemon
After=network.target

[Service]
Type=simple
ExecStart={kira_path} agent start
Restart=always
RestartSec=5
StartLimitIntervalSec=300
StartLimitBurst=20
Environment=PATH={user_path}

[Install]
WantedBy=default.target
"""

    unit_path.write_text(unit_content)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", LINUX_SERVICE_NAME],
        check=True,
        capture_output=True,
    )

    log_hint = f"journalctl --user -u {LINUX_SERVICE_NAME} -f"
    return f"Agent service installed and started.\nUnit: {unit_path}\nLogs: {log_hint}"


def _uninstall_linux() -> str:
    unit_path = Path.home() / ".config" / "systemd" / "user" / f"{LINUX_SERVICE_NAME}.service"
    if not unit_path.exists():
        return "Agent service is not installed."

    subprocess.run(
        ["systemctl", "--user", "disable", "--now", LINUX_SERVICE_NAME],
        check=False,
        capture_output=True,
    )
    unit_path.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
    return "Agent service uninstalled."
