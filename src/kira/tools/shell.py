"""Shell execution tool."""

from __future__ import annotations

import asyncio
import os
import shlex
import time

from .base import BaseTool, registry
from .models import ToolResult, ToolStatus

# Commands that are always allowed
SAFE_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "wc",
    "echo",
    "pwd",
    "which",
    "whoami",
    "date",
    "env",
    "python",
    "python3",
    "pip",
    "pip3",
    "node",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "git",
    "gh",
    "cargo",
    "rustc",
    "go",
    "make",
    "cmake",
    "docker",
    "docker-compose",
    "curl",
    "wget",
    "jq",
    "yq",
    "sed",
    "awk",
    "sort",
    "uniq",
    "cut",
    "tr",
    "diff",
    "patch",
    "tar",
    "zip",
    "unzip",
    "gzip",
    "gunzip",
    "tree",
    "file",
    "stat",
    "pytest",
    "mypy",
    "ruff",
    "black",
    "isort",
}

# Commands that require elevated trust
DANGEROUS_COMMANDS = {
    "rm",
    "rmdir",
    "mv",
    "cp",  # File operations
    "chmod",
    "chown",
    "chgrp",  # Permission changes
    "sudo",
    "su",  # Privilege escalation
    "kill",
    "killall",
    "pkill",  # Process management
    "shutdown",
    "reboot",  # System control
    "dd",
    "mkfs",
    "fdisk",  # Disk operations
    "iptables",
    "ufw",  # Network security
}


@registry.register
class Shell(BaseTool):
    """Execute shell commands."""

    name = "shell"
    description = "Execute shell commands"
    requires_trust = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = self.context.timeout_seconds

    def is_command_safe(self, command: str) -> tuple[bool, str]:
        """Check if a command is safe to execute.

        Args:
            command: Shell command to check.

        Returns:
            Tuple of (is_safe, reason).
        """
        try:
            # Parse the command to get the base command
            parts = shlex.split(command)
            if not parts:
                return False, "Empty command"

            base_cmd = os.path.basename(parts[0])

            # Check for dangerous commands
            if base_cmd in DANGEROUS_COMMANDS:
                if self.context.trust_level != "trusted":
                    return False, f"Command '{base_cmd}' requires trusted mode"

            # Check for pipes/redirects to dangerous commands
            if "|" in command:
                for part in command.split("|"):
                    part_parts = shlex.split(part.strip())
                    if part_parts:
                        part_base = os.path.basename(part_parts[0])
                        if part_base in DANGEROUS_COMMANDS:
                            if self.context.trust_level != "trusted":
                                return False, f"Pipe to '{part_base}' requires trusted mode"

            return True, ""
        except ValueError as e:
            return False, f"Invalid command syntax: {e}"

    async def execute(
        self,
        command: str | None = None,
        timeout: int | None = None,
        **kwargs: str | int | bool | list[str] | None,
    ) -> ToolResult:
        """Execute a shell command.

        Args:
            command: Shell command to execute.
            timeout: Optional timeout override in seconds.
            **kwargs: Additional arguments (ignored).

        Returns:
            Tool result with command output.
        """
        if not command:
            return self.make_result(ToolStatus.FAILURE, "", error="command argument required")

        start = time.time()
        exec_timeout = timeout or self.timeout

        # Check command safety
        is_safe, reason = self.is_command_safe(command)
        if not is_safe:
            return self.make_result(ToolStatus.PERMISSION_DENIED, "", error=reason)

        # Dry run mode
        if self.context.dry_run:
            return self.make_result(
                ToolStatus.SUCCESS,
                f"[DRY RUN] Would execute: {command}",
                duration=time.time() - start,
            )

        try:
            # Execute the command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.context.working_dir,
                env={**os.environ, "TERM": "dumb"},  # Disable colors
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=exec_timeout,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return self.make_result(
                    ToolStatus.TIMEOUT,
                    "",
                    error=f"Command timed out after {exec_timeout}s",
                    duration=time.time() - start,
                )

            # Combine output
            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            if process.returncode == 0:
                result = self.make_result(
                    ToolStatus.SUCCESS,
                    output,
                    duration=time.time() - start,
                )
            else:
                result = self.make_result(
                    ToolStatus.FAILURE,
                    output,
                    error=error_output or f"Exit code: {process.returncode}",
                    duration=time.time() - start,
                )

            self.record({"command": command}, result)
            return result

        except FileNotFoundError:
            return self.make_result(
                ToolStatus.FAILURE,
                "",
                error="Command not found",
                duration=time.time() - start,
            )
        except PermissionError:
            return self.make_result(
                ToolStatus.PERMISSION_DENIED,
                "",
                error="Permission denied",
                duration=time.time() - start,
            )
        except Exception as e:
            return self.make_result(
                ToolStatus.FAILURE,
                "",
                error=str(e),
                duration=time.time() - start,
            )


@registry.register
class PythonExec(BaseTool):
    """Execute Python code."""

    name = "python_exec"
    description = "Execute Python code"
    requires_trust = True

    async def execute(
        self,
        code: str | None = None,
        timeout: int | None = None,
        **kwargs: str | int | bool | list[str] | None,
    ) -> ToolResult:
        """Execute Python code.

        Args:
            code: Python code to execute.
            timeout: Optional timeout in seconds.
            **kwargs: Additional arguments (ignored).

        Returns:
            Tool result with execution output.
        """
        if not code:
            return self.make_result(ToolStatus.FAILURE, "", error="code argument required")

        start = time.time()
        exec_timeout = timeout or self.context.timeout_seconds

        # Check trust level
        can_exec, reason = self.can_execute()
        if not can_exec:
            return self.make_result(ToolStatus.PERMISSION_DENIED, "", error=reason)

        # Dry run mode
        if self.context.dry_run:
            return self.make_result(
                ToolStatus.SUCCESS,
                f"[DRY RUN] Would execute {len(code)} bytes of Python code",
                duration=time.time() - start,
            )

        try:
            # Execute via subprocess for isolation
            process = await asyncio.create_subprocess_exec(
                "python3",
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.context.working_dir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=exec_timeout,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return self.make_result(
                    ToolStatus.TIMEOUT,
                    "",
                    error=f"Execution timed out after {exec_timeout}s",
                    duration=time.time() - start,
                )

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            if process.returncode == 0:
                result = self.make_result(
                    ToolStatus.SUCCESS,
                    output,
                    duration=time.time() - start,
                )
            else:
                result = self.make_result(
                    ToolStatus.FAILURE,
                    output,
                    error=error_output,
                    duration=time.time() - start,
                )

            self.record({"code_length": len(code)}, result)
            return result

        except Exception as e:
            return self.make_result(
                ToolStatus.FAILURE,
                "",
                error=str(e),
                duration=time.time() - start,
            )
