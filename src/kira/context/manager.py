"""Context file management - read/write/update project context."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    ChangeEntry,
    ChangeType,
    Convention,
    KnownIssue,
    ProjectContext,
    TechStack,
)

# Default context file paths
CONTEXT_FILE = ".kira/context.md"
CHANGELOG_FILE = ".kira/changelog.md"


class ContextManager:
    """Manages project context files."""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self.context_path = self.project_dir / CONTEXT_FILE
        self.changelog_path = self.project_dir / CHANGELOG_FILE
        self._context: ProjectContext | None = None

    @property
    def context(self) -> ProjectContext:
        """Get or load the project context."""
        if self._context is None:
            self._context = self.load()
        return self._context

    def exists(self) -> bool:
        """Check if context file exists."""
        return self.context_path.exists()

    def load(self) -> ProjectContext:
        """Load context from file."""
        if not self.context_path.exists():
            return ProjectContext()

        content = self.context_path.read_text()
        return self._parse_context(content)

    def save(self, context: ProjectContext | None = None) -> None:
        """Save context to file."""
        ctx = context or self._context or ProjectContext()

        # Ensure directory exists
        self.context_path.parent.mkdir(parents=True, exist_ok=True)

        # Update metadata
        ctx.last_updated = datetime.now()
        if not ctx.last_updated_by:
            ctx.last_updated_by = self._get_current_user()

        content = self._generate_markdown(ctx)
        self.context_path.write_text(content)
        self._context = ctx

    def add_change(
        self,
        summary: str,
        details: list[str] | None = None,
        change_type: ChangeType = ChangeType.FEATURE,
        decisions: list[str] | None = None,
        files_changed: list[str] | None = None,
    ) -> ChangeEntry:
        """Add a change entry to the context."""
        entry = ChangeEntry(
            date=datetime.now(),
            author=self._get_current_user(),
            change_type=change_type,
            summary=summary,
            details=details or [],
            decisions=decisions or [],
            files_changed=files_changed or [],
        )

        self.context.add_change(entry)
        self.save()

        # Also append to changelog file
        self._append_to_changelog(entry)

        return entry

    def add_note(self, note: str) -> None:
        """Add a note to the context."""
        self.context.add_note(note, self._get_current_user())
        self.save()

    def update_overview(self, overview: str) -> None:
        """Update the project overview."""
        self.context.overview = overview
        self.save()

    def update_architecture(self, architecture: str) -> None:
        """Update the architecture description."""
        self.context.architecture = architecture
        self.save()

    def add_convention(self, category: str, rule: str, example: str | None = None) -> None:
        """Add a coding convention."""
        conv = Convention(category=category, rule=rule, example=example)
        self.context.conventions.append(conv)
        self.save()

    def add_issue(self, description: str, severity: str = "info") -> None:
        """Add a known issue."""
        issue = KnownIssue(
            description=description,
            severity=severity,
            added_date=datetime.now(),
            added_by=self._get_current_user(),
        )
        self.context.known_issues.append(issue)
        self.save()

    def get_prompt_context(self) -> str:
        """Get context formatted for prompt injection."""
        if not self.exists():
            return ""
        return self.context.to_prompt_context()

    def _get_current_user(self) -> str:
        """Get current user name from git or environment."""
        # Try git config first
        try:
            import subprocess

            result = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True,
                text=True,
                cwd=self.project_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        # Fall back to environment
        return os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

    def _parse_context(self, content: str) -> ProjectContext:
        """Parse markdown content into ProjectContext."""
        ctx = ProjectContext()

        # Extract sections using regex
        sections = self._split_sections(content)

        # Parse each section
        if "Project Context" in sections:
            # Extract project name from header
            header = sections.get("Project Context", "")
            if match := re.search(r"#\s+(.+?)(?:\n|$)", header):
                ctx.name = match.group(1).replace("Project Context", "").strip(" -:")

        if "Overview" in sections:
            ctx.overview = sections["Overview"].strip()

        if "Architecture" in sections:
            ctx.architecture = sections["Architecture"].strip()

        if "Tech Stack" in sections:
            ctx.tech_stack = self._parse_tech_stack(sections["Tech Stack"])

        if "Conventions" in sections:
            ctx.conventions = self._parse_conventions(sections["Conventions"])

        if "Recent Changes" in sections:
            ctx.changelog = self._parse_changelog(sections["Recent Changes"])

        if "Known Issues" in sections:
            ctx.known_issues = self._parse_issues(sections["Known Issues"])

        if "Notes" in sections:
            ctx.notes = self._parse_notes(sections["Notes"])

        return ctx

    def _split_sections(self, content: str) -> dict[str, str]:
        """Split markdown into sections by headers."""
        sections: dict[str, str] = {}
        current_section = ""
        current_content: list[str] = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[3:].strip()
                current_content = []
            elif line.startswith("# "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[2:].strip()
                current_content = []
            else:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content)

        return sections

    def _parse_tech_stack(self, content: str) -> TechStack:
        """Parse tech stack section."""
        stack = TechStack()

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("**Languages:**"):
                stack.languages = self._parse_list_inline(line)
            elif line.startswith("**Frameworks:**"):
                stack.frameworks = self._parse_list_inline(line)
            elif line.startswith("**Databases:**"):
                stack.databases = self._parse_list_inline(line)
            elif line.startswith("**Tools:**"):
                stack.tools = self._parse_list_inline(line)
            elif line.startswith("- "):
                # Handle bullet point format
                item = line[2:].strip()
                # Try to categorize
                if any(
                    x in item.lower()
                    for x in ["python", "javascript", "typescript", "java", "go", "rust"]
                ):
                    stack.languages.append(item)
                elif any(
                    x in item.lower() for x in ["react", "vue", "fastapi", "django", "spring"]
                ):
                    stack.frameworks.append(item)
                elif any(x in item.lower() for x in ["postgres", "mysql", "mongodb", "redis"]):
                    stack.databases.append(item)
                else:
                    stack.tools.append(item)

        return stack

    def _parse_list_inline(self, line: str) -> list[str]:
        """Parse inline comma-separated list."""
        # Remove the label
        if ":" in line:
            line = line.split(":", 1)[1]
        # Remove markdown formatting
        line = re.sub(r"\*\*|\*|`", "", line)
        # Split and clean
        return [x.strip() for x in line.split(",") if x.strip()]

    def _parse_conventions(self, content: str) -> list[Convention]:
        """Parse conventions section."""
        conventions = []

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                line = line[2:]
                # Try to extract category
                if match := re.match(r"\*\*(.+?):\*\*\s*(.+)", line):
                    conventions.append(
                        Convention(
                            category=match.group(1),
                            rule=match.group(2),
                        )
                    )
                else:
                    conventions.append(
                        Convention(
                            category="general",
                            rule=line,
                        )
                    )

        return conventions

    def _parse_changelog(self, content: str) -> list[ChangeEntry]:
        """Parse changelog section."""
        entries = []
        current_entry: dict[str, Any] | None = None

        for line in content.split("\n"):
            line = line.strip()

            # Match header: ### 2024-01-15 - Summary [type] (@author)
            if line.startswith("### "):
                if current_entry:
                    entries.append(self._create_entry(current_entry))

                current_entry = {"details": [], "decisions": [], "files": []}

                # Parse header
                header = line[4:]
                if match := re.match(
                    r"(\d{4}-\d{2}-\d{2})\s*(?:\d{2}:\d{2})?\s*-\s*(.+?)(?:\s*\[(\w+)\])?\s*(?:\(@(\w+)\))?$",
                    header,
                ):
                    current_entry["date"] = match.group(1)
                    current_entry["summary"] = match.group(2).strip()
                    current_entry["type"] = match.group(3) or "feature"
                    current_entry["author"] = match.group(4) or "unknown"

            elif current_entry:
                if line.startswith("- "):
                    current_entry["details"].append(line[2:])
                elif line.startswith("**Decisions:**"):
                    pass  # Next lines will be decisions
                elif "decision" in line.lower() or (current_entry.get("in_decisions")):
                    if line.startswith("- "):
                        current_entry["decisions"].append(line[2:])

        if current_entry:
            entries.append(self._create_entry(current_entry))

        return entries

    def _create_entry(self, data: dict[str, Any]) -> ChangeEntry:
        """Create a ChangeEntry from parsed data."""
        try:
            date = datetime.strptime(data.get("date", ""), "%Y-%m-%d")
        except ValueError:
            date = datetime.now()

        type_str = data.get("type", "feature").lower()
        try:
            change_type = ChangeType(type_str)
        except ValueError:
            change_type = ChangeType.FEATURE

        return ChangeEntry(
            date=date,
            author=data.get("author", "unknown"),
            change_type=change_type,
            summary=data.get("summary", ""),
            details=data.get("details", []),
            decisions=data.get("decisions", []),
            files_changed=data.get("files", []),
        )

    def _parse_issues(self, content: str) -> list[KnownIssue]:
        """Parse known issues section."""
        issues = []

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                line = line[2:]
                # Try to extract severity
                severity = "info"
                if match := re.match(r"\[(\w+)\]\s*(.+)", line):
                    severity = match.group(1).lower()
                    line = match.group(2)

                issues.append(
                    KnownIssue(
                        description=line,
                        severity=severity,
                    )
                )

        return issues

    def _parse_notes(self, content: str) -> list[str]:
        """Parse notes section."""
        notes = []

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                notes.append(line[2:])
            elif line and not line.startswith("#"):
                notes.append(line)

        return [n for n in notes if n]

    def _generate_markdown(self, ctx: ProjectContext) -> str:
        """Generate markdown from ProjectContext."""
        lines = []

        # Header
        name = ctx.name or self.project_dir.name
        lines.append(f"# Project Context - {name}")
        lines.append("")
        lines.append(
            f"*Last updated: {ctx.last_updated.strftime('%Y-%m-%d %H:%M') if ctx.last_updated else 'never'}*"
        )
        if ctx.last_updated_by:
            lines.append(f"*Updated by: @{ctx.last_updated_by}*")
        lines.append("")

        # Overview
        lines.append("## Overview")
        lines.append("")
        lines.append(
            ctx.overview or "*No overview yet. Run `/context refresh` to analyze the project.*"
        )
        lines.append("")

        # Architecture
        lines.append("## Architecture")
        lines.append("")
        lines.append(ctx.architecture or "*No architecture description yet.*")
        lines.append("")

        # Tech Stack
        lines.append("## Tech Stack")
        lines.append("")
        if ctx.tech_stack.languages or ctx.tech_stack.frameworks:
            lines.append(ctx.tech_stack.to_markdown())
        else:
            lines.append("*Tech stack will be detected on first analysis.*")
        lines.append("")

        # Conventions
        lines.append("## Conventions")
        lines.append("")
        if ctx.conventions:
            for conv in ctx.conventions:
                lines.append(f"- **{conv.category}:** {conv.rule}")
        else:
            lines.append("*No conventions documented yet.*")
        lines.append("")

        # Recent Changes
        lines.append("## Recent Changes")
        lines.append("")
        recent = ctx.get_recent_changes(10)
        if recent:
            for entry in recent:
                lines.append(entry.to_markdown())
                lines.append("")
        else:
            lines.append("*No changes recorded yet.*")
        lines.append("")

        # Known Issues
        lines.append("## Known Issues")
        lines.append("")
        if ctx.known_issues:
            for issue in ctx.known_issues:
                lines.append(f"- [{issue.severity}] {issue.description}")
        else:
            lines.append("*No known issues.*")
        lines.append("")

        # Notes
        lines.append("## Notes")
        lines.append("")
        if ctx.notes:
            for note in ctx.notes:
                lines.append(f"- {note}")
        else:
            lines.append("*Add notes with `/context note <your note>`*")
        lines.append("")

        return "\n".join(lines)

    def _append_to_changelog(self, entry: ChangeEntry) -> None:
        """Append entry to separate changelog file."""
        self.changelog_path.parent.mkdir(parents=True, exist_ok=True)

        # Create or append
        if not self.changelog_path.exists():
            header = f"# Changelog - {self.project_dir.name}\n\n"
            header += "*AI-assisted changes tracked by kira*\n\n"
            header += "---\n\n"
            self.changelog_path.write_text(header)

        # Append new entry
        with open(self.changelog_path, "a") as f:
            f.write(entry.to_markdown())
            f.write("\n\n---\n\n")


def get_context_manager(project_dir: Path | None = None) -> ContextManager:
    """Get a context manager for the given project directory."""
    return ContextManager(project_dir)
