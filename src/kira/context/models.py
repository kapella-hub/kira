"""Data models for project context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ChangeType(Enum):
    """Type of change made to the project."""

    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    DOCS = "docs"
    TEST = "test"
    CHORE = "chore"
    ARCHITECTURE = "architecture"


@dataclass
class ChangeEntry:
    """A single change entry in the changelog."""

    date: datetime
    author: str
    change_type: ChangeType
    summary: str
    details: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = []
        date_str = self.date.strftime("%Y-%m-%d %H:%M")
        type_badge = f"[{self.change_type.value}]"
        lines.append(f"### {date_str} - {self.summary} {type_badge} (@{self.author})")

        for detail in self.details:
            lines.append(f"- {detail}")

        if self.decisions:
            lines.append("")
            lines.append("**Decisions:**")
            for decision in self.decisions:
                lines.append(f"- {decision}")

        if self.files_changed:
            lines.append("")
            lines.append(f"*Files: {', '.join(self.files_changed[:5])}*")
            if len(self.files_changed) > 5:
                lines.append(f"*... and {len(self.files_changed) - 5} more*")

        return "\n".join(lines)


@dataclass
class TechStack:
    """Technology stack information."""

    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = []
        if self.languages:
            lines.append(f"**Languages:** {', '.join(self.languages)}")
        if self.frameworks:
            lines.append(f"**Frameworks:** {', '.join(self.frameworks)}")
        if self.databases:
            lines.append(f"**Databases:** {', '.join(self.databases)}")
        if self.tools:
            lines.append(f"**Tools:** {', '.join(self.tools)}")
        return "\n".join(lines)


@dataclass
class Convention:
    """A coding convention or pattern."""

    category: str  # e.g., "naming", "structure", "testing"
    rule: str
    example: str | None = None


@dataclass
class KnownIssue:
    """A known issue or limitation."""

    description: str
    severity: str = "info"  # info, warning, critical
    added_date: datetime | None = None
    added_by: str | None = None


@dataclass
class ProjectContext:
    """Complete project context for sharing between engineers."""

    # Basic info
    name: str = ""
    description: str = ""
    overview: str = ""

    # Architecture
    architecture: str = ""
    key_components: list[str] = field(default_factory=list)

    # Tech stack
    tech_stack: TechStack = field(default_factory=TechStack)

    # Conventions
    conventions: list[Convention] = field(default_factory=list)

    # Change history
    changelog: list[ChangeEntry] = field(default_factory=list)

    # Issues and notes
    known_issues: list[KnownIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # Metadata
    last_updated: datetime | None = None
    last_updated_by: str | None = None
    version: str = "1.0"

    def get_recent_changes(self, limit: int = 5) -> list[ChangeEntry]:
        """Get most recent changes."""
        sorted_changes = sorted(
            self.changelog,
            key=lambda x: x.date,
            reverse=True,
        )
        return sorted_changes[:limit]

    def add_change(self, entry: ChangeEntry) -> None:
        """Add a change entry."""
        self.changelog.append(entry)
        self.last_updated = datetime.now()
        self.last_updated_by = entry.author

    def add_note(self, note: str, author: str | None = None) -> None:
        """Add a note."""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        if author:
            self.notes.append(f"[{timestamp}] (@{author}) {note}")
        else:
            self.notes.append(f"[{timestamp}] {note}")
        self.last_updated = datetime.now()

    def to_prompt_context(self) -> str:
        """Convert to a concise context string for prompts."""
        lines = []

        if self.name:
            lines.append(f"# Project: {self.name}")
            lines.append("")

        if self.overview:
            lines.append("## Overview")
            lines.append(self.overview)
            lines.append("")

        if self.architecture:
            lines.append("## Architecture")
            lines.append(self.architecture)
            lines.append("")

        if self.tech_stack.languages or self.tech_stack.frameworks:
            lines.append("## Tech Stack")
            lines.append(self.tech_stack.to_markdown())
            lines.append("")

        if self.conventions:
            lines.append("## Conventions")
            for conv in self.conventions[:10]:  # Limit to avoid too much context
                lines.append(f"- **{conv.category}:** {conv.rule}")
            lines.append("")

        # Recent changes (last 3)
        recent = self.get_recent_changes(3)
        if recent:
            lines.append("## Recent Changes")
            for change in recent:
                date_str = change.date.strftime("%Y-%m-%d")
                lines.append(f"- [{date_str}] {change.summary} (@{change.author})")
            lines.append("")

        # Known issues
        if self.known_issues:
            lines.append("## Known Issues")
            for issue in self.known_issues[:5]:
                lines.append(f"- [{issue.severity}] {issue.description}")
            lines.append("")

        return "\n".join(lines)
