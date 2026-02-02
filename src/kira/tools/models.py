"""Data models for tool system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ToolStatus(Enum):
    """Status of a tool execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class ToolCall:
    """Represents a call to a tool."""

    tool_name: str
    arguments: dict[str, str | int | bool | list[str] | None]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_context(self) -> str:
        """Format for display."""
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"{self.tool_name}({args_str})"


@dataclass
class ToolResult:
    """Result of a tool execution."""

    tool_name: str
    status: ToolStatus
    output: str
    error: str | None = None
    duration_seconds: float = 0.0
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Whether the tool execution succeeded."""
        return self.status == ToolStatus.SUCCESS

    def to_context(self) -> str:
        """Format for display."""
        status_str = "[green]OK[/green]" if self.success else f"[red]{self.status.value}[/red]"
        lines = [f"{self.tool_name}: {status_str}"]
        if self.output:
            # Truncate long output
            output_preview = self.output[:500] + "..." if len(self.output) > 500 else self.output
            lines.append(f"Output: {output_preview}")
        if self.error:
            lines.append(f"Error: {self.error}")
        if self.files_modified:
            lines.append(f"Modified: {', '.join(self.files_modified)}")
        if self.files_created:
            lines.append(f"Created: {', '.join(self.files_created)}")
        return "\n".join(lines)


@dataclass
class ToolContext:
    """Context for tool execution."""

    working_dir: str
    trust_level: str = "normal"  # "normal", "trusted", "restricted"
    timeout_seconds: int = 120
    dry_run: bool = False
    verbose: bool = False

    # Tracking
    calls_made: list[ToolCall] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)

    def record_call(self, call: ToolCall, result: ToolResult) -> None:
        """Record a tool call and its result."""
        self.calls_made.append(call)
        self.results.append(result)

    @property
    def files_modified(self) -> list[str]:
        """All files modified across all tool calls."""
        files: list[str] = []
        for result in self.results:
            files.extend(result.files_modified)
            files.extend(result.files_created)
        return list(set(files))
