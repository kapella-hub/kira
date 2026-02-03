"""Learning from failures - track errors and solutions to avoid repeating mistakes."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class FailurePattern:
    """A recorded failure pattern."""

    id: int | None
    error_type: str  # e.g., "SyntaxError", "ImportError", "TestFailure"
    error_message: str  # The actual error message
    context: str  # What was being attempted
    solution: str  # How it was fixed
    task_keywords: list[str]  # Keywords from the original task
    file_patterns: list[str]  # File patterns involved
    created_at: datetime = field(default_factory=datetime.utcnow)
    occurrence_count: int = 1
    last_occurred: datetime = field(default_factory=datetime.utcnow)

    def matches_context(self, task: str, files: list[str] | None = None) -> float:
        """Calculate match score for a given context."""
        score = 0.0
        task_lower = task.lower()

        # Check keyword matches
        matching_keywords = sum(1 for kw in self.task_keywords if kw in task_lower)
        if self.task_keywords:
            score += 0.4 * (matching_keywords / len(self.task_keywords))

        # Check file pattern matches
        if files and self.file_patterns:
            matching_files = sum(1 for fp in self.file_patterns if any(fp in f for f in files))
            score += 0.3 * (matching_files / len(self.file_patterns))

        # Boost for error type mention
        if self.error_type.lower() in task_lower:
            score += 0.3

        return min(1.0, score)

    def to_warning(self) -> str:
        """Format as a warning for prompt injection."""
        return f"⚠️ **Known Issue ({self.error_type})**: {self.error_message[:100]}\n   **Solution**: {self.solution[:150]}"


class FailureLearning:
    """Learns from failures to avoid repeating mistakes.

    Stores failure patterns and their solutions in SQLite.
    Before similar tasks, injects warnings about known pitfalls.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (Path.home() / ".kira" / "failures.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_hash TEXT UNIQUE,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    context TEXT,
                    solution TEXT,
                    task_keywords TEXT,
                    file_patterns TEXT,
                    created_at TEXT NOT NULL,
                    occurrence_count INTEGER DEFAULT 1,
                    last_occurred TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_failures_type ON failures(error_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_failures_hash ON failures(error_hash)
            """)

    def record_failure(
        self,
        error_type: str,
        error_message: str,
        context: str,
        solution: str = "",
        task: str = "",
        files: list[str] | None = None,
    ) -> FailurePattern:
        """Record a failure pattern.

        Args:
            error_type: Type of error (e.g., "SyntaxError")
            error_message: The error message
            context: What was being attempted
            solution: How it was/should be fixed
            task: Original task description
            files: Files involved

        Returns:
            The recorded FailurePattern
        """
        # Generate hash for deduplication
        error_hash = hashlib.md5(f"{error_type}:{error_message[:100]}".encode()).hexdigest()

        # Extract keywords from task
        task_keywords = self._extract_keywords(task) if task else []

        # Extract file patterns
        file_patterns = [Path(f).suffix for f in (files or []) if Path(f).suffix]
        file_patterns = list(set(file_patterns))

        now = datetime.utcnow().isoformat()

        with self._connect() as conn:
            # Check if exists
            existing = conn.execute(
                "SELECT id, occurrence_count FROM failures WHERE error_hash = ?", (error_hash,)
            ).fetchone()

            if existing:
                # Update existing
                conn.execute(
                    """
                    UPDATE failures
                    SET occurrence_count = occurrence_count + 1,
                        last_occurred = ?,
                        solution = CASE WHEN ? != '' THEN ? ELSE solution END
                    WHERE id = ?
                """,
                    (now, solution, solution, existing["id"]),
                )

                return FailurePattern(
                    id=existing["id"],
                    error_type=error_type,
                    error_message=error_message,
                    context=context,
                    solution=solution,
                    task_keywords=task_keywords,
                    file_patterns=file_patterns,
                    occurrence_count=existing["occurrence_count"] + 1,
                )
            else:
                # Insert new
                cursor = conn.execute(
                    """
                    INSERT INTO failures
                    (error_hash, error_type, error_message, context, solution,
                     task_keywords, file_patterns, created_at, last_occurred)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        error_hash,
                        error_type,
                        error_message,
                        context,
                        solution,
                        json.dumps(task_keywords),
                        json.dumps(file_patterns),
                        now,
                        now,
                    ),
                )

                return FailurePattern(
                    id=cursor.lastrowid,
                    error_type=error_type,
                    error_message=error_message,
                    context=context,
                    solution=solution,
                    task_keywords=task_keywords,
                    file_patterns=file_patterns,
                )

    def record_solution(self, failure_id: int, solution: str) -> None:
        """Record a solution for a failure."""
        with self._connect() as conn:
            conn.execute("UPDATE failures SET solution = ? WHERE id = ?", (solution, failure_id))

    def get_relevant_warnings(
        self,
        task: str,
        files: list[str] | None = None,
        min_score: float = 0.3,
        limit: int = 3,
    ) -> list[FailurePattern]:
        """Get relevant failure warnings for a task.

        Args:
            task: The task description
            files: Files that will be involved
            min_score: Minimum relevance score
            limit: Maximum warnings to return

        Returns:
            List of relevant FailurePatterns
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM failures
                WHERE solution != ''
                ORDER BY occurrence_count DESC, last_occurred DESC
                LIMIT 50
            """).fetchall()

        patterns = []
        for row in rows:
            pattern = FailurePattern(
                id=row["id"],
                error_type=row["error_type"],
                error_message=row["error_message"],
                context=row["context"] or "",
                solution=row["solution"] or "",
                task_keywords=json.loads(row["task_keywords"] or "[]"),
                file_patterns=json.loads(row["file_patterns"] or "[]"),
                created_at=datetime.fromisoformat(row["created_at"]),
                occurrence_count=row["occurrence_count"],
                last_occurred=datetime.fromisoformat(row["last_occurred"]),
            )

            score = pattern.matches_context(task, files)
            if score >= min_score:
                patterns.append((score, pattern))

        # Sort by score
        patterns.sort(key=lambda x: -x[0])

        return [p for _, p in patterns[:limit]]

    def get_context_string(
        self,
        task: str,
        files: list[str] | None = None,
        max_warnings: int = 3,
    ) -> str:
        """Get warning context for prompt injection.

        Args:
            task: The task description
            files: Files involved
            max_warnings: Maximum warnings to include

        Returns:
            Formatted warning string, or empty if no relevant warnings
        """
        warnings = self.get_relevant_warnings(task, files, limit=max_warnings)

        if not warnings:
            return ""

        lines = ["## Known Pitfalls (learn from past mistakes)\n"]
        for pattern in warnings:
            lines.append(pattern.to_warning())
            lines.append("")

        return "\n".join(lines)

    def _extract_keywords(self, task: str) -> list[str]:
        """Extract relevant keywords from a task description."""
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
            "please",
            "i",
            "you",
            "we",
            "they",
            "it",
            "this",
            "that",
            "these",
            "those",
        }

        words = re.findall(r"\b[a-z]+\b", task.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        # Return unique keywords, preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique[:10]

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about recorded failures."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
            with_solution = conn.execute(
                "SELECT COUNT(*) FROM failures WHERE solution != ''"
            ).fetchone()[0]

            by_type = conn.execute("""
                SELECT error_type, COUNT(*) as count
                FROM failures
                GROUP BY error_type
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()

        return {
            "total_failures": total,
            "with_solutions": with_solution,
            "by_type": {row["error_type"]: row["count"] for row in by_type},
        }


# Patterns for detecting error types from output
ERROR_PATTERNS = {
    "SyntaxError": [r"SyntaxError:", r"syntax error", r"unexpected token"],
    "ImportError": [r"ImportError:", r"ModuleNotFoundError:", r"No module named"],
    "TypeError": [r"TypeError:", r"not callable", r"NoneType"],
    "AttributeError": [r"AttributeError:", r"has no attribute"],
    "ValueError": [r"ValueError:", r"invalid literal", r"could not convert"],
    "KeyError": [r"KeyError:"],
    "IndexError": [r"IndexError:", r"list index out of range"],
    "FileNotFoundError": [r"FileNotFoundError:", r"No such file or directory"],
    "TestFailure": [r"FAILED", r"AssertionError:", r"test.*failed"],
    "RuntimeError": [r"RuntimeError:", r"maximum recursion"],
}


def detect_error_type(output: str) -> str | None:
    """Detect error type from output."""
    for error_type, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return error_type
    return None


def extract_error_message(output: str, error_type: str) -> str:
    """Extract the error message from output."""
    lines = output.split("\n")

    # Find the line with the error
    for i, line in enumerate(lines):
        if error_type in line or any(p in line for p in ERROR_PATTERNS.get(error_type, [])):
            # Return this line and possibly the next for context
            msg = line.strip()
            if i + 1 < len(lines) and lines[i + 1].strip():
                msg += " " + lines[i + 1].strip()
            return msg[:200]

    return output[:200]


def get_failure_learning(db_path: Path | None = None) -> FailureLearning:
    """Get a FailureLearning instance."""
    return FailureLearning(db_path)
