"""Git assistant - smart commit messages, branch names, and git operations."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitStatus:
    """Current git repository status."""

    is_repo: bool = False
    branch: str = ""
    staged: list[str] = None
    unstaged: list[str] = None
    untracked: list[str] = None
    ahead: int = 0
    behind: int = 0

    def __post_init__(self):
        self.staged = self.staged or []
        self.unstaged = self.unstaged or []
        self.untracked = self.untracked or []

    @property
    def has_changes(self) -> bool:
        return bool(self.staged or self.unstaged or self.untracked)

    @property
    def has_staged(self) -> bool:
        return bool(self.staged)

    def summary(self) -> str:
        """Get a brief summary of the status."""
        parts = []
        if self.staged:
            parts.append(f"{len(self.staged)} staged")
        if self.unstaged:
            parts.append(f"{len(self.unstaged)} modified")
        if self.untracked:
            parts.append(f"{len(self.untracked)} untracked")
        if self.ahead:
            parts.append(f"↑{self.ahead}")
        if self.behind:
            parts.append(f"↓{self.behind}")
        return ", ".join(parts) if parts else "clean"


@dataclass
class CommitSuggestion:
    """Suggested commit message."""

    type: str  # feat, fix, refactor, docs, test, chore
    scope: str  # component/area affected
    subject: str  # short description
    body: str = ""  # longer description
    breaking: bool = False

    def format(self, style: str = "conventional") -> str:
        """Format the commit message."""
        if style == "conventional":
            prefix = f"{self.type}"
            if self.scope:
                prefix += f"({self.scope})"
            if self.breaking:
                prefix += "!"
            msg = f"{prefix}: {self.subject}"
            if self.body:
                msg += f"\n\n{self.body}"
            return msg
        else:
            # Simple style
            return self.subject


class GitAssistant:
    """Smart git operations assistant."""

    # Patterns to detect change types from file paths
    TYPE_PATTERNS = {
        "test": [r"test[s]?/", r"_test\.", r"\.test\.", r"spec\."],
        "docs": [r"docs?/", r"README", r"\.md$", r"CHANGELOG"],
        "config": [r"config", r"\.env", r"\.yaml$", r"\.toml$", r"\.json$"],
        "ci": [r"\.github/", r"\.gitlab", r"Jenkinsfile", r"\.circleci"],
    }

    # Keywords to detect commit type from diff
    COMMIT_KEYWORDS = {
        "feat": ["add", "new", "implement", "create", "support"],
        "fix": ["fix", "bug", "issue", "error", "correct", "patch"],
        "refactor": ["refactor", "restructure", "reorganize", "clean", "simplify"],
        "perf": ["performance", "optimize", "speed", "faster", "cache"],
        "style": ["style", "format", "lint", "whitespace"],
        "chore": ["update", "upgrade", "bump", "dependency", "deps"],
    }

    def __init__(self, repo_dir: Path | None = None):
        self.repo_dir = repo_dir or Path.cwd()

    def get_status(self) -> GitStatus:
        """Get current git status."""
        status = GitStatus()

        # Check if git repo
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return status
            status.is_repo = True
        except FileNotFoundError:
            return status

        # Get current branch
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            status.branch = result.stdout.strip()
        except Exception:
            pass

        # Get status
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                indicator = line[:2]
                file_path = line[3:]

                if indicator[0] in "MADRC":
                    status.staged.append(file_path)
                if indicator[1] in "MD":
                    status.unstaged.append(file_path)
                if indicator == "??":
                    status.untracked.append(file_path)
        except Exception:
            pass

        # Get ahead/behind
        try:
            result = subprocess.run(
                [
                    "git",
                    "rev-list",
                    "--left-right",
                    "--count",
                    f"{status.branch}...origin/{status.branch}",
                ],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split("\t")
                if len(parts) == 2:
                    status.ahead = int(parts[0])
                    status.behind = int(parts[1])
        except Exception:
            pass

        return status

    def get_diff(self, staged: bool = True) -> str:
        """Get the current diff."""
        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")
            result = subprocess.run(
                cmd,
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            return result.stdout
        except Exception:
            return ""

    def suggest_commit(self, task_context: str = "") -> CommitSuggestion:
        """Suggest a commit message based on changes."""
        status = self.get_status()
        diff = self.get_diff(staged=True)

        # Determine files changed
        files = status.staged or status.unstaged

        # Detect type from files
        commit_type = self._detect_type_from_files(files)

        # If no clear type, detect from diff content
        if commit_type == "chore" and diff:
            commit_type = self._detect_type_from_diff(diff)

        # Detect scope from files
        scope = self._detect_scope(files)

        # Generate subject
        subject = self._generate_subject(files, diff, task_context)

        # Generate body if significant changes
        body = ""
        if len(files) > 3:
            body = self._generate_body(files, diff)

        return CommitSuggestion(
            type=commit_type,
            scope=scope,
            subject=subject,
            body=body,
        )

    def suggest_branch(self, task: str) -> str:
        """Suggest a branch name from task description."""
        # Clean up task
        task_lower = task.lower()

        # Detect type prefix
        prefix = "feature"
        if any(kw in task_lower for kw in ["fix", "bug", "issue", "error"]):
            prefix = "fix"
        elif any(kw in task_lower for kw in ["refactor", "clean", "improve"]):
            prefix = "refactor"
        elif any(kw in task_lower for kw in ["doc", "readme", "comment"]):
            prefix = "docs"
        elif any(kw in task_lower for kw in ["test", "spec"]):
            prefix = "test"

        # Extract key words for branch name
        # Remove common words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "please",
            "implement",
            "add",
            "create",
            "make",
            "build",
            "update",
            "fix",
            "change",
        }

        words = re.findall(r"\b[a-z]+\b", task_lower)
        key_words = [w for w in words if w not in stop_words and len(w) > 2][:4]

        if not key_words:
            key_words = ["update"]

        slug = "-".join(key_words)
        return f"{prefix}/{slug}"

    def stage_all(self) -> bool:
        """Stage all changes."""
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.repo_dir,
                check=True,
            )
            return True
        except Exception:
            return False

    def commit(self, message: str) -> tuple[bool, str]:
        """Create a commit with the given message."""
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    def _detect_type_from_files(self, files: list[str]) -> str:
        """Detect commit type from file paths."""
        for commit_type, patterns in self.TYPE_PATTERNS.items():
            for pattern in patterns:
                if any(re.search(pattern, f, re.IGNORECASE) for f in files):
                    if commit_type == "test":
                        return "test"
                    elif commit_type == "docs":
                        return "docs"
                    elif commit_type == "config":
                        return "chore"
                    elif commit_type == "ci":
                        return "ci"
        return "chore"

    def _detect_type_from_diff(self, diff: str) -> str:
        """Detect commit type from diff content."""
        diff_lower = diff.lower()

        # Count keyword occurrences
        scores = {}
        for commit_type, keywords in self.COMMIT_KEYWORDS.items():
            scores[commit_type] = sum(diff_lower.count(kw) for kw in keywords)

        if not any(scores.values()):
            return "chore"

        return max(scores, key=scores.get)

    def _detect_scope(self, files: list[str]) -> str:
        """Detect scope from file paths."""
        if not files:
            return ""

        # Find common directory
        parts_list = [Path(f).parts for f in files]
        if not parts_list:
            return ""

        # Find common prefix
        common = []
        for parts in zip(*parts_list):
            if len(set(parts)) == 1:
                common.append(parts[0])
            else:
                break

        if common:
            # Use last meaningful directory
            for part in reversed(common):
                if part not in ("src", "lib", "app", "."):
                    return part

        # If single file, use directory
        if len(files) == 1:
            parts = Path(files[0]).parts
            if len(parts) > 1:
                return parts[-2] if parts[-2] not in ("src", "lib") else ""

        return ""

    def _generate_subject(self, files: list[str], diff: str, task_context: str) -> str:
        """Generate a commit subject line."""
        # If task context provided, use it
        if task_context:
            # Clean up and truncate
            subject = task_context.strip().split("\n")[0]
            subject = re.sub(
                r"^(implement|add|create|fix|update|make)\s+", "", subject, flags=re.IGNORECASE
            )
            if len(subject) > 50:
                subject = subject[:47] + "..."
            return subject.lower()

        # Generate from files
        if len(files) == 1:
            return f"update {Path(files[0]).name}"
        elif len(files) <= 3:
            names = [Path(f).name for f in files]
            return f"update {', '.join(names)}"
        else:
            # Find common theme
            scope = self._detect_scope(files)
            if scope:
                return f"update {scope} ({len(files)} files)"
            return f"update {len(files)} files"

    def _generate_body(self, files: list[str], diff: str) -> str:
        """Generate commit body for significant changes."""
        lines = ["Changes:"]
        for f in files[:10]:
            lines.append(f"- {f}")
        if len(files) > 10:
            lines.append(f"- ... and {len(files) - 10} more")
        return "\n".join(lines)


def get_git_assistant(repo_dir: Path | None = None) -> GitAssistant:
    """Get a git assistant instance."""
    return GitAssistant(repo_dir)
