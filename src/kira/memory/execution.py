"""Execution memory for learning from past attempts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ExecutionRecord:
    """Record of a task execution."""

    id: int | None = None
    task_hash: str = ""
    task_pattern: str = ""
    task_summary: str = ""
    approach: str = ""
    success: bool = False
    error_type: str | None = None
    error_message: str | None = None
    learnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    attempts: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_context(self) -> str:
        """Format for injection into prompts."""
        status = "[green]SUCCESS[/green]" if self.success else "[red]FAILED[/red]"
        lines = [
            f"Task: {self.task_summary}",
            f"Status: {status}",
            f"Approach: {self.approach}",
        ]
        if self.learnings:
            lines.append("Learnings:")
            for learning in self.learnings:
                lines.append(f"  - {learning}")
        if self.error_type and not self.success:
            lines.append(f"Error: {self.error_type} - {self.error_message}")
        return "\n".join(lines)


class ExecutionMemory:
    """Memory store for learning from past executions."""

    def __init__(self, db_path: Path | None = None):
        """Initialize execution memory.

        Args:
            db_path: Path to SQLite database.
        """
        if db_path is None:
            from ..core.config import Config

            db_path = Config.USER_DATA_DIR / "execution_memory.db"

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_hash TEXT NOT NULL,
                    task_pattern TEXT NOT NULL,
                    task_summary TEXT NOT NULL,
                    approach TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    learnings TEXT,
                    duration_seconds REAL,
                    attempts INTEGER,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_hash ON executions(task_hash)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_pattern ON executions(task_pattern)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_success ON executions(success)
            """)

    def _hash_task(self, task: str) -> str:
        """Create a hash for task similarity matching."""
        # Normalize task text
        normalized = task.lower().strip()
        # Remove specific identifiers (file paths, numbers, etc.)
        normalized = re.sub(r"/[\w/.-]+", "<path>", normalized)
        normalized = re.sub(r"\d+", "<num>", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _extract_pattern(self, task: str) -> str:
        """Extract a pattern from task for fuzzy matching."""
        # Extract key action words
        action_words = [
            "implement",
            "create",
            "add",
            "fix",
            "update",
            "refactor",
            "delete",
            "remove",
            "change",
            "modify",
            "write",
            "build",
            "test",
            "debug",
            "deploy",
            "configure",
            "install",
            "setup",
        ]
        words = task.lower().split()
        actions = [w for w in words if w in action_words]

        # Extract key nouns/concepts
        concept_words = [
            "function",
            "class",
            "method",
            "api",
            "endpoint",
            "database",
            "file",
            "config",
            "test",
            "error",
            "bug",
            "feature",
            "module",
            "component",
            "service",
            "model",
            "view",
            "controller",
        ]
        concepts = [w for w in words if w in concept_words]

        return f"{' '.join(actions[:2])} {' '.join(concepts[:2])}".strip()

    def record_success(
        self,
        task: str,
        approach: str,
        learnings: list[str] | None = None,
        duration_seconds: float = 0.0,
        attempts: int = 1,
    ) -> int:
        """Record a successful execution.

        Args:
            task: Task description.
            approach: Approach that was used.
            learnings: What was learned.
            duration_seconds: Execution duration.
            attempts: Number of attempts needed.

        Returns:
            Record ID.
        """
        return self._record(
            task=task,
            approach=approach,
            success=True,
            learnings=learnings or [],
            duration_seconds=duration_seconds,
            attempts=attempts,
        )

    def record_failure(
        self,
        task: str,
        approach: str,
        error_type: str,
        error_message: str,
        learnings: list[str] | None = None,
        duration_seconds: float = 0.0,
        attempts: int = 1,
    ) -> int:
        """Record a failed execution.

        Args:
            task: Task description.
            approach: Approach that was used.
            error_type: Type of error encountered.
            error_message: Error message.
            learnings: What was learned from failure.
            duration_seconds: Execution duration.
            attempts: Number of attempts made.

        Returns:
            Record ID.
        """
        learnings = learnings or []
        learnings.append(f"Avoid: {error_type} - {error_message}")

        return self._record(
            task=task,
            approach=approach,
            success=False,
            error_type=error_type,
            error_message=error_message,
            learnings=learnings,
            duration_seconds=duration_seconds,
            attempts=attempts,
        )

    def _record(
        self,
        task: str,
        approach: str,
        success: bool,
        error_type: str | None = None,
        error_message: str | None = None,
        learnings: list[str] | None = None,
        duration_seconds: float = 0.0,
        attempts: int = 1,
    ) -> int:
        """Record an execution.

        Returns:
            Record ID.
        """
        task_hash = self._hash_task(task)
        task_pattern = self._extract_pattern(task)
        task_summary = task[:200]  # Truncate long tasks

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO executions (
                    task_hash, task_pattern, task_summary, approach,
                    success, error_type, error_message, learnings,
                    duration_seconds, attempts, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_hash,
                    task_pattern,
                    task_summary,
                    approach,
                    1 if success else 0,
                    error_type,
                    error_message,
                    json.dumps(learnings or []),
                    duration_seconds,
                    attempts,
                    datetime.utcnow().isoformat(),
                ),
            )
            return cursor.lastrowid or 0

    def get_relevant_history(
        self,
        task: str,
        limit: int = 5,
        include_failures: bool = True,
    ) -> list[ExecutionRecord]:
        """Get relevant history for a task.

        Args:
            task: Task description to find history for.
            limit: Maximum records to return.
            include_failures: Whether to include failures.

        Returns:
            List of relevant execution records.
        """
        task_hash = self._hash_task(task)
        task_pattern = self._extract_pattern(task)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # First try exact hash match
            success_filter = "" if include_failures else "AND success = 1"
            rows = conn.execute(
                f"""
                SELECT * FROM executions
                WHERE task_hash = ? {success_filter}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (task_hash, limit),
            ).fetchall()

            if len(rows) < limit:
                # Try pattern match for more
                remaining = limit - len(rows)
                pattern_rows = conn.execute(
                    f"""
                    SELECT * FROM executions
                    WHERE task_pattern LIKE ? {success_filter}
                    AND task_hash != ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (f"%{task_pattern}%", task_hash, remaining),
                ).fetchall()
                rows.extend(pattern_rows)

            return [self._row_to_record(row) for row in rows]

    def get_successful_approaches(
        self,
        task: str,
        limit: int = 3,
    ) -> list[tuple[str, int]]:
        """Get successful approaches for similar tasks.

        Args:
            task: Task description.
            limit: Maximum approaches to return.

        Returns:
            List of (approach, success_count) tuples.
        """
        task_pattern = self._extract_pattern(task)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT approach, COUNT(*) as count
                FROM executions
                WHERE task_pattern LIKE ?
                AND success = 1
                GROUP BY approach
                ORDER BY count DESC
                LIMIT ?
                """,
                (f"%{task_pattern}%", limit),
            ).fetchall()

            return [(row[0], row[1]) for row in rows]

    def get_failure_patterns(
        self,
        task: str,
    ) -> list[tuple[str, str]]:
        """Get failure patterns to avoid for similar tasks.

        Args:
            task: Task description.

        Returns:
            List of (error_type, approach_to_avoid) tuples.
        """
        task_pattern = self._extract_pattern(task)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT error_type, approach
                FROM executions
                WHERE task_pattern LIKE ?
                AND success = 0
                AND error_type IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (f"%{task_pattern}%",),
            ).fetchall()

            return [(row[0], row[1]) for row in rows]

    def get_stats(self) -> dict[str, int | float]:
        """Get memory statistics.

        Returns:
            Dictionary of statistics.
        """
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
            successes = conn.execute(
                "SELECT COUNT(*) FROM executions WHERE success = 1"
            ).fetchone()[0]

            return {
                "total_executions": total,
                "successful_executions": successes,
                "failed_executions": total - successes,
                "success_rate": successes / total if total > 0 else 0.0,
            }

    def clear(self) -> int:
        """Clear all execution memory.

        Returns:
            Number of records deleted.
        """
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
            conn.execute("DELETE FROM executions")
            return count

    def _row_to_record(self, row: sqlite3.Row) -> ExecutionRecord:
        """Convert database row to ExecutionRecord."""
        return ExecutionRecord(
            id=row["id"],
            task_hash=row["task_hash"],
            task_pattern=row["task_pattern"],
            task_summary=row["task_summary"],
            approach=row["approach"],
            success=bool(row["success"]),
            error_type=row["error_type"],
            error_message=row["error_message"],
            learnings=json.loads(row["learnings"]) if row["learnings"] else [],
            duration_seconds=row["duration_seconds"],
            attempts=row["attempts"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
