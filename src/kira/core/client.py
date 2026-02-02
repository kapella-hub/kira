"""KiraClient - Subprocess wrapper for kiro-cli.

Uses kiro-cli in non-interactive mode with prompts sent via stdin.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncIterator


# ANSI escape code pattern - matches all CSI sequences, OSC sequences, and cursor controls
ANSI_ESCAPE = re.compile(
    r"\x1b\[[0-9;?]*[a-zA-Z]"  # CSI sequences like [0m, [?25l
    r"|\x1b\].*?\x07"          # OSC sequences
    r"|\x1b[()][AB012]"        # Character set selection
    r"|\r"                      # Carriage return (used in spinners)
)

# Patterns to filter from kiro-cli output
FILTER_PATTERNS = [
    # ASCII art and banners
    r"^[─│┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬█▀▄░▒▓\s]+$",
    # Model selection line
    r"^Model:\s*",
    # Did you know tips
    r"^Did you know\?",
    # Tool execution logs
    r"^(Reading|Writing|Executing|Running|Creating|Deleting)\s+",
    # Timing info
    r"^▸\s*Time:",
    # Spinner artifacts
    r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏\s]+$",
    # Empty lines with just spaces
    r"^\s*$",
]

# Compiled filter patterns
COMPILED_FILTERS = [re.compile(p) for p in FILTER_PATTERNS]


@dataclass
class KiraResult:
    """Result from a kiro-cli execution."""

    output: str
    exit_code: int


class KiraNotFoundError(Exception):
    """Raised when kiro-cli is not installed."""

    pass


class KiraClient:
    """Executes kiro-cli as a subprocess.

    Uses kiro-cli in non-interactive mode:
    - Prompts sent via stdin
    - Output streamed from stdout
    - ANSI codes and banners filtered
    """

    def __init__(
        self,
        *,
        agent: str | None = None,
        model: str | None = None,
        trust_all_tools: bool = False,
        working_dir: Path | None = None,
        timeout: int = 600,
    ):
        self.agent = agent
        self.model = model
        self.trust_all_tools = trust_all_tools
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout
        self._kiro_path: str | None = None

    def _find_kiro(self) -> str:
        """Find kiro-cli executable."""
        if self._kiro_path:
            return self._kiro_path

        # Check common locations
        kiro = shutil.which("kiro-cli") or shutil.which("kiro")
        if kiro:
            self._kiro_path = kiro
            return kiro

        # Check common install paths
        for path in [
            os.path.expanduser("~/.local/bin/kiro-cli"),
            "/usr/local/bin/kiro-cli",
            os.path.expanduser("~/.npm-global/bin/kiro-cli"),
        ]:
            if os.path.exists(path):
                self._kiro_path = path
                return path

        raise KiraNotFoundError(
            "kiro-cli not found. Install from https://kiro.dev or ensure it's in PATH"
        )

    def _build_command(
        self,
        *,
        agent: str | None = None,
        resume: bool = False,
    ) -> list[str]:
        """Build the kiro-cli command (prompt goes via stdin)."""
        kiro = self._find_kiro()
        cmd = [kiro, "chat"]

        # Agent selection
        if agent or self.agent:
            cmd.extend(["--agent", agent or self.agent])

        # Model selection
        if self.model:
            cmd.extend(["--model", self.model])

        # Trust all tools
        if self.trust_all_tools:
            cmd.append("--trust-all-tools")

        # Resume previous session
        if resume:
            cmd.append("-r")

        # Non-interactive mode (prompt via stdin)
        cmd.append("--no-interactive")

        # Disable line wrapping for clean output
        cmd.extend(["--wrap", "never"])

        return cmd

    def _clean_line(self, line: str) -> str | None:
        """Clean a single line of output. Returns None if line should be filtered."""
        # Strip ANSI escape codes
        line = ANSI_ESCAPE.sub("", line)

        # Check if line matches any filter pattern
        for pattern in COMPILED_FILTERS:
            if pattern.match(line):
                return None

        # Remove leading "> " prefix that kiro uses for responses
        if line.startswith("> "):
            line = line[2:]

        return line

    def _clean_output(self, text: str) -> str:
        """Clean complete output text."""
        lines = text.split("\n")
        cleaned = []

        for line in lines:
            clean = self._clean_line(line)
            if clean is not None:
                cleaned.append(clean)

        # Remove leading/trailing empty lines
        while cleaned and not cleaned[0].strip():
            cleaned.pop(0)
        while cleaned and not cleaned[-1].strip():
            cleaned.pop()

        return "\n".join(cleaned)

    async def run(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        resume: bool = False,
    ) -> AsyncIterator[str]:
        """Execute a prompt through kiro-cli, streaming output.

        Yields cleaned output chunks as they arrive from kiro-cli.
        """
        cmd = self._build_command(agent=agent, resume=resume)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env={**os.environ},
        )

        # Send prompt via stdin
        process.stdin.write(prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        # Buffer for incomplete lines
        buffer = ""
        started_output = False

        try:
            while True:
                # Read chunks from stdout
                chunk = await asyncio.wait_for(
                    process.stdout.read(512),
                    timeout=self.timeout,
                )

                if not chunk:
                    break

                text = chunk.decode("utf-8", errors="replace")
                buffer += text

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    cleaned = self._clean_line(line)

                    if cleaned is not None:
                        # Skip initial empty lines
                        if not started_output and not cleaned.strip():
                            continue
                        started_output = True
                        yield cleaned + "\n"

            # Handle any remaining buffer content
            if buffer.strip():
                cleaned = self._clean_line(buffer)
                if cleaned is not None:
                    yield cleaned

            await process.wait()

            # Check for errors
            if process.returncode != 0:
                stderr_data = await process.stderr.read()
                if stderr_data:
                    stderr_text = stderr_data.decode("utf-8", errors="replace").strip()
                    if stderr_text:
                        yield f"\n[Error from kiro-cli: {stderr_text}]\n"

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            yield "\n[Error: kiro-cli timed out]\n"

    async def run_batch(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        resume: bool = False,
    ) -> KiraResult:
        """Run kiro-cli and return complete result (non-streaming)."""
        cmd = self._build_command(agent=agent, resume=resume)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env={**os.environ},
            )

            # Send prompt via stdin
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode("utf-8")),
                timeout=self.timeout,
            )

            output = self._clean_output(stdout.decode("utf-8", errors="replace"))

            return KiraResult(output=output, exit_code=process.returncode or 0)

        except asyncio.TimeoutError:
            return KiraResult(output="[Error: kiro-cli timed out]", exit_code=-1)

    def run_sync(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        resume: bool = False,
    ) -> KiraResult:
        """Synchronous version of run_batch."""
        cmd = self._build_command(agent=agent, resume=resume)

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
                env={**os.environ},
            )
            output = self._clean_output(result.stdout)
            return KiraResult(output=output, exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            return KiraResult(output="[Error: kiro-cli timed out]", exit_code=-1)

    @staticmethod
    def is_available() -> bool:
        """Check if kiro-cli is available."""
        return shutil.which("kiro-cli") is not None or shutil.which("kiro") is not None

    @staticmethod
    def get_version() -> str | None:
        """Get kiro-cli version."""
        kiro = shutil.which("kiro-cli") or shutil.which("kiro")
        if not kiro:
            return None

        try:
            result = subprocess.run(
                [kiro, "--version"], capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            return None

    @staticmethod
    def get_diagnostic_info() -> dict | None:
        """Get diagnostic info from kiro-cli.

        Returns:
            Dict with version, date, etc. or None if failed.
        """
        kiro = shutil.which("kiro-cli") or shutil.which("kiro")
        if not kiro:
            return None

        try:
            result = subprocess.run(
                [kiro, "diagnostic"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None

            # Parse TOML-like output
            info = {}
            current_section = None
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                elif "=" in line and current_section == "q-details":
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"')
                    info[key] = value

            return info if info else None

        except (subprocess.TimeoutExpired, OSError):
            return None

    @staticmethod
    def check_for_updates() -> dict | None:
        """Check if kiro-cli updates might be available.

        Returns:
            Dict with 'should_remind', 'version', 'age_days', 'message'
            or None if check failed.
        """
        from ..core.config import Config

        # Check last reminder time
        state_file = Config.USER_DATA_DIR / "update_check.json"
        now = datetime.utcnow()
        remind_interval_days = 7

        # Load previous state
        last_check = None
        last_reminded = None
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
                    last_check = datetime.fromisoformat(state.get("last_check", ""))
                    last_reminded = datetime.fromisoformat(state.get("last_reminded", ""))
            except (json.JSONDecodeError, ValueError, KeyError):
                pass

        # Don't remind too frequently
        if last_reminded and (now - last_reminded).days < remind_interval_days:
            return {"should_remind": False}

        # Get diagnostic info
        info = KiraClient.get_diagnostic_info()
        if not info:
            return None

        version = info.get("version", "unknown")
        date_str = info.get("date", "")

        # Parse build date
        age_days = 0
        if date_str:
            try:
                # Format: "2026-01-27T20:48:19.714341Z (5d ago)"
                date_part = date_str.split("(")[0].strip()
                if date_part.endswith("Z"):
                    date_part = date_part[:-1]
                build_date = datetime.fromisoformat(date_part.split(".")[0])
                age_days = (now - build_date).days
            except (ValueError, IndexError):
                pass

        # Remind if version is older than 14 days
        should_remind = age_days > 14

        result = {
            "should_remind": should_remind,
            "version": version,
            "age_days": age_days,
            "message": f"kiro-cli {version} is {age_days} days old. Run 'kiro-cli update' to check for updates."
            if should_remind else None,
        }

        # Save state
        if should_remind:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({
                    "last_check": now.isoformat(),
                    "last_reminded": now.isoformat(),
                    "version": version,
                }, f)

        return result
