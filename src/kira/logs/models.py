"""Data models for run logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RunMode(Enum):
    """Mode of execution."""

    REPL = "repl"
    CHAT = "chat"
    THINKING = "thinking"
    AUTONOMOUS = "autonomous"
    WORKFLOW = "workflow"


@dataclass
class RunLogEntry:
    """A single prompt/response pair within a run."""

    id: int | None = None
    run_id: int | None = None
    prompt: str = ""
    response: str = ""
    model: str | None = None
    tokens_prompt: int | None = None
    tokens_response: int | None = None
    duration_seconds: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def preview(self, max_len: int = 50) -> str:
        """Get a preview of the prompt."""
        text = self.prompt.replace("\n", " ").strip()
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text


@dataclass
class RunLog:
    """A run session (REPL session or single chat)."""

    id: int | None = None
    session_id: str = ""
    mode: RunMode = RunMode.CHAT
    model: str | None = None
    working_dir: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None
    entry_count: int = 0
    total_duration: float = 0.0
    skills: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Loaded entries (not always populated)
    entries: list[RunLogEntry] = field(default_factory=list)

    @property
    def duration_display(self) -> str:
        """Human-readable duration."""
        if self.total_duration < 60:
            return f"{self.total_duration:.1f}s"
        mins = int(self.total_duration // 60)
        secs = int(self.total_duration % 60)
        return f"{mins}m {secs}s"

    @property
    def mode_display(self) -> str:
        """Display-friendly mode name."""
        return self.mode.value.capitalize()

    def summary(self) -> str:
        """One-line summary of the run."""
        return f"[{self.mode_display}] {self.entry_count} messages, {self.duration_display}"
