"""Formatters for converting kira session data to Jira ticket content."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


def get_git_changes(working_dir: Path | None = None) -> dict:
    """Get recent git changes in the working directory."""
    cwd = working_dir or Path.cwd()
    result = {
        "branch": "",
        "recent_commits": [],
        "changed_files": [],
        "has_uncommitted": False,
    }

    try:
        # Get current branch
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if branch.returncode == 0:
            result["branch"] = branch.stdout.strip()

        # Get recent commits (last 5)
        commits = subprocess.run(
            ["git", "log", "--oneline", "-5", "--no-decorate"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if commits.returncode == 0:
            result["recent_commits"] = commits.stdout.strip().split("\n")

        # Get changed files (staged + unstaged)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if status.returncode == 0 and status.stdout.strip():
            result["has_uncommitted"] = True
            lines = status.stdout.strip().split("\n")
            result["changed_files"] = [line[3:] for line in lines if line]

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return result


def format_session_description(
    summary: str,
    session_context: str = "",
    working_dir: Path | None = None,
    include_git: bool = True,
    include_timestamp: bool = True,
) -> str:
    """Format session data into a Jira ticket description.

    Args:
        summary: Brief summary of work done
        session_context: Additional context from the session
        working_dir: Working directory for git info
        include_git: Whether to include git changes
        include_timestamp: Whether to include timestamp

    Returns:
        Formatted description for Jira ticket
    """
    parts = []

    # Summary section
    parts.append(f"h3. Summary\n{summary}")

    # Session context
    if session_context:
        parts.append(f"h3. Details\n{session_context}")

    # Git information
    if include_git:
        git_info = get_git_changes(working_dir)

        if git_info["branch"]:
            git_section = ["h3. Git Information", f"*Branch:* {git_info['branch']}"]

            if git_info["recent_commits"]:
                git_section.append("\n*Recent commits:*")
                for commit in git_info["recent_commits"][:5]:
                    git_section.append(f"* {commit}")

            if git_info["changed_files"]:
                git_section.append("\n*Changed files:*")
                for file in git_info["changed_files"][:10]:
                    git_section.append(f"* {file}")
                if len(git_info["changed_files"]) > 10:
                    git_section.append(f"* ... and {len(git_info['changed_files']) - 10} more")

            parts.append("\n".join(git_section))

    # Timestamp
    if include_timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        parts.append(f"----\n_Created from kira session at {timestamp}_")

    return "\n\n".join(parts)


def suggest_labels_from_context(context: str) -> list[str]:
    """Suggest labels based on work context."""
    labels = []
    context_lower = context.lower()

    # Detect work type
    if any(word in context_lower for word in ["fix", "bug", "error", "issue"]):
        labels.append("bugfix")
    if any(word in context_lower for word in ["feature", "implement", "add", "new"]):
        labels.append("feature")
    if any(word in context_lower for word in ["refactor", "clean", "improve"]):
        labels.append("refactor")
    if any(word in context_lower for word in ["test", "spec", "coverage"]):
        labels.append("testing")
    if any(word in context_lower for word in ["doc", "readme", "comment"]):
        labels.append("documentation")
    if any(word in context_lower for word in ["ui", "frontend", "css", "style"]):
        labels.append("frontend")
    if any(word in context_lower for word in ["api", "backend", "server"]):
        labels.append("backend")
    if any(word in context_lower for word in ["deploy", "ci", "cd", "pipeline"]):
        labels.append("devops")

    # Always add kira label to track automated tickets
    labels.append("kira-generated")

    return labels


def suggest_issue_type(context: str) -> str:
    """Suggest issue type based on work context."""
    context_lower = context.lower()

    if any(word in context_lower for word in ["bug", "fix", "error", "broken"]):
        return "Bug"
    if any(word in context_lower for word in ["story", "user story", "as a user"]):
        return "Story"
    if any(word in context_lower for word in ["epic", "initiative", "theme"]):
        return "Epic"

    return "Task"  # Default
