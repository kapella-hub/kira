"""SQLite storage for run logs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import RunLog, RunLogEntry, RunMode


class RunLogStore:
    """Store for run logs using SQLite."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | None = None):
        """Initialize the run log store.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.kira/data/runs.db
        """
        if db_path is None:
            from ..core.config import Config

            db_path = Config.USER_DATA_DIR / "runs.db"

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Runs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    model TEXT,
                    working_dir TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    entry_count INTEGER DEFAULT 0,
                    total_duration REAL DEFAULT 0.0,
                    skills TEXT,
                    metadata TEXT
                )
            """)

            # Entries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS run_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    response TEXT,
                    model TEXT,
                    tokens_prompt INTEGER,
                    tokens_response INTEGER,
                    duration_seconds REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
                )
            """)

            # Indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entries_run ON run_entries(run_id)
            """)

    def start_run(
        self,
        session_id: str,
        mode: RunMode,
        model: str | None = None,
        working_dir: str | None = None,
        skills: list[str] | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Start a new run and return its ID.

        Args:
            session_id: Unique session identifier.
            mode: Run mode (REPL, CHAT, etc.)
            model: Model being used.
            working_dir: Working directory.
            skills: Active skills.
            metadata: Additional metadata.

        Returns:
            The new run's ID.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (
                    session_id, mode, model, working_dir, started_at,
                    skills, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    mode.value,
                    model,
                    working_dir or "",
                    datetime.utcnow().isoformat(),
                    json.dumps(skills or []),
                    json.dumps(metadata or {}),
                ),
            )
            return cursor.lastrowid or 0

    def end_run(self, run_id: int) -> None:
        """Mark a run as ended.

        Args:
            run_id: The run ID to end.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Calculate total duration from entries
            row = conn.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(duration_seconds), 0)
                FROM run_entries WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            entry_count, total_duration = row

            conn.execute(
                """
                UPDATE runs
                SET ended_at = ?, entry_count = ?, total_duration = ?
                WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), entry_count, total_duration, run_id),
            )

    def add_entry(
        self,
        run_id: int,
        prompt: str,
        response: str = "",
        model: str | None = None,
        tokens_prompt: int | None = None,
        tokens_response: int | None = None,
        duration_seconds: float = 0.0,
        metadata: dict | None = None,
    ) -> int:
        """Add an entry to a run.

        Args:
            run_id: The run to add to.
            prompt: User prompt.
            response: Agent response.
            model: Model used for this entry.
            tokens_prompt: Prompt token count.
            tokens_response: Response token count.
            duration_seconds: Time taken.
            metadata: Additional metadata.

        Returns:
            The new entry's ID.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO run_entries (
                    run_id, prompt, response, model,
                    tokens_prompt, tokens_response, duration_seconds,
                    created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    prompt,
                    response,
                    model,
                    tokens_prompt,
                    tokens_response,
                    duration_seconds,
                    datetime.utcnow().isoformat(),
                    json.dumps(metadata or {}),
                ),
            )

            # Update run's entry count
            conn.execute(
                """
                UPDATE runs SET entry_count = entry_count + 1 WHERE id = ?
                """,
                (run_id,),
            )

            return cursor.lastrowid or 0

    def update_entry_response(
        self,
        entry_id: int,
        response: str,
        duration_seconds: float = 0.0,
        tokens_response: int | None = None,
    ) -> None:
        """Update an entry's response (for streaming).

        Args:
            entry_id: Entry to update.
            response: Full response text.
            duration_seconds: Time taken.
            tokens_response: Response token count.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE run_entries
                SET response = ?, duration_seconds = ?, tokens_response = ?
                WHERE id = ?
                """,
                (response, duration_seconds, tokens_response, entry_id),
            )

    def get_run(self, run_id: int, include_entries: bool = False) -> RunLog | None:
        """Get a run by ID.

        Args:
            run_id: Run ID to fetch.
            include_entries: Whether to load entries.

        Returns:
            RunLog or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()

            if not row:
                return None

            run = self._row_to_run(row)

            if include_entries:
                run.entries = self.get_entries(run_id)

            return run

    def get_entries(self, run_id: int, limit: int = 100) -> list[RunLogEntry]:
        """Get entries for a run.

        Args:
            run_id: Run ID.
            limit: Maximum entries to return.

        Returns:
            List of entries.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM run_entries
                WHERE run_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()

            return [self._row_to_entry(row) for row in rows]

    def list_runs(
        self,
        mode: RunMode | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[RunLog]:
        """List runs with optional filtering.

        Args:
            mode: Filter by mode.
            limit: Maximum runs to return.
            offset: Offset for pagination.

        Returns:
            List of runs (without entries loaded).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if mode:
                rows = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE mode = ?
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (mode.value, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM runs
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()

            return [self._row_to_run(row) for row in rows]

    def get_latest_run(self, mode: RunMode | None = None) -> RunLog | None:
        """Get the most recent run.

        Args:
            mode: Filter by mode.

        Returns:
            Most recent RunLog or None.
        """
        runs = self.list_runs(mode=mode, limit=1)
        return runs[0] if runs else None

    def search_entries(
        self,
        query: str,
        limit: int = 20,
    ) -> list[tuple[RunLog, RunLogEntry]]:
        """Search entries by prompt content.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of (run, entry) tuples.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT e.*, r.session_id, r.mode, r.model as run_model,
                       r.working_dir, r.started_at as run_started
                FROM run_entries e
                JOIN runs r ON e.run_id = r.id
                WHERE e.prompt LIKE ? OR e.response LIKE ?
                ORDER BY e.created_at DESC
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()

            results = []
            for row in rows:
                entry = self._row_to_entry(row)
                run = RunLog(
                    id=row["run_id"],
                    session_id=row["session_id"],
                    mode=RunMode(row["mode"]),
                    model=row["run_model"],
                    working_dir=row["working_dir"],
                    started_at=datetime.fromisoformat(row["run_started"]),
                )
                results.append((run, entry))

            return results

    def count_runs(self, mode: RunMode | None = None) -> int:
        """Count total runs.

        Args:
            mode: Filter by mode.

        Returns:
            Count of runs.
        """
        with sqlite3.connect(self.db_path) as conn:
            if mode:
                row = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE mode = ?",
                    (mode.value,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
            return row[0]

    def count_entries(self) -> int:
        """Count total entries across all runs."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM run_entries").fetchone()
            return row[0]

    def get_stats(self) -> dict:
        """Get log statistics.

        Returns:
            Dictionary of statistics.
        """
        with sqlite3.connect(self.db_path) as conn:
            total_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            total_entries = conn.execute("SELECT COUNT(*) FROM run_entries").fetchone()[0]
            total_duration = conn.execute(
                "SELECT COALESCE(SUM(total_duration), 0) FROM runs"
            ).fetchone()[0]

            # By mode
            by_mode = {}
            for row in conn.execute("SELECT mode, COUNT(*) FROM runs GROUP BY mode").fetchall():
                by_mode[row[0]] = row[1]

            return {
                "total_runs": total_runs,
                "total_entries": total_entries,
                "total_duration": total_duration,
                "by_mode": by_mode,
            }

    def clear(
        self,
        before: datetime | None = None,
        mode: RunMode | None = None,
    ) -> int:
        """Clear runs matching criteria.

        Args:
            before: Delete runs started before this time.
            mode: Delete runs of this mode.

        Returns:
            Number of runs deleted.
        """
        with sqlite3.connect(self.db_path) as conn:
            conditions = []
            params = []

            if before:
                conditions.append("started_at < ?")
                params.append(before.isoformat())
            if mode:
                conditions.append("mode = ?")
                params.append(mode.value)

            if conditions:
                where = " WHERE " + " AND ".join(conditions)
            else:
                where = ""

            # Get count first
            count = conn.execute(f"SELECT COUNT(*) FROM runs{where}", params).fetchone()[0]

            # Delete entries (cascade should handle this, but be explicit)
            conn.execute(
                f"""
                DELETE FROM run_entries WHERE run_id IN (
                    SELECT id FROM runs{where}
                )
                """,
                params,
            )

            # Delete runs
            conn.execute(f"DELETE FROM runs{where}", params)

            return count

    def _row_to_run(self, row: sqlite3.Row) -> RunLog:
        """Convert a database row to a RunLog."""
        return RunLog(
            id=row["id"],
            session_id=row["session_id"],
            mode=RunMode(row["mode"]),
            model=row["model"],
            working_dir=row["working_dir"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=(datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None),
            entry_count=row["entry_count"],
            total_duration=row["total_duration"] or 0.0,
            skills=json.loads(row["skills"]) if row["skills"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_entry(self, row: sqlite3.Row) -> RunLogEntry:
        """Convert a database row to a RunLogEntry."""
        return RunLogEntry(
            id=row["id"],
            run_id=row["run_id"],
            prompt=row["prompt"],
            response=row["response"] or "",
            model=row["model"],
            tokens_prompt=row["tokens_prompt"],
            tokens_response=row["tokens_response"],
            duration_seconds=row["duration_seconds"] or 0.0,
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
