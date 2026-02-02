"""MemoryStore - Persistent context across kiro-cli sessions.

kiro-cli's built-in knowledge tool is session-scoped. We provide
cross-session memory that can be injected into prompts.

Storage: SQLite (simple, reliable, no dependencies)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .models import Memory, MemorySource, MemoryType

# Schema version for migrations
SCHEMA_VERSION = 2


class MemoryStore:
    """SQLite-backed memory persistence.

    Design:
    - Simple key-value with tags and importance
    - Full-text search via FTS5
    - Context window aware (can limit by importance/recency)
    - Memory types for categorization
    - Access tracking for relevance scoring
    - Decay calculation for automatic cleanup
    """

    DEFAULT_PATH = Path.home() / ".kira" / "memory.db"

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or self.DEFAULT_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema with migrations."""
        with self._connect() as conn:
            # Check current schema version
            try:
                cursor = conn.execute("SELECT version FROM schema_version")
                current_version = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                current_version = 0

            # Apply migrations
            if current_version < 1:
                self._migrate_v1(conn)
            if current_version < 2:
                self._migrate_v2(conn)

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        """Initial schema creation."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );
            INSERT OR REPLACE INTO schema_version (version) VALUES (1);

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                importance INTEGER DEFAULT 5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
            CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);

            -- Full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                key, content, tags,
                content='memories',
                content_rowid='id'
            );

            -- Keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, key, content, tags)
                VALUES (new.id, new.key, new.content, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, content, tags)
                VALUES('delete', old.id, old.key, old.content, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, content, tags)
                VALUES('delete', old.id, old.key, old.content, old.tags);
                INSERT INTO memories_fts(rowid, key, content, tags)
                VALUES (new.id, new.key, new.content, new.tags);
            END;
        """
        )

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        """Add memory types, source, and access tracking."""
        # Add new columns (SQLite doesn't support IF NOT EXISTS for ALTER)
        try:
            conn.execute("ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'semantic'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE memories ADD COLUMN source TEXT DEFAULT 'user'")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE memories ADD COLUMN access_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE memories ADD COLUMN last_accessed_at TEXT")
        except sqlite3.OperationalError:
            pass

        # Add new indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_access ON memories(access_count DESC)")

        # Update schema version
        conn.execute("UPDATE schema_version SET version = 2")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def store(
        self,
        key: str,
        content: str,
        tags: list[str] | None = None,
        importance: int = 5,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        source: MemorySource = MemorySource.USER,
    ) -> Memory:
        """Store or update a memory."""
        now = datetime.utcnow().isoformat()
        tags = tags or []

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (key, content, tags, importance, memory_type, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content = excluded.content,
                    tags = excluded.tags,
                    importance = excluded.importance,
                    memory_type = excluded.memory_type,
                    updated_at = excluded.updated_at
            """,
                (key, content, json.dumps(tags), importance, memory_type.value, source.value, now, now),
            )

            cursor = conn.execute("SELECT * FROM memories WHERE key = ?", (key,))
            row = cursor.fetchone()
            return self._row_to_memory(row)

    def get(self, key: str, track_access: bool = True) -> Memory | None:
        """Get a specific memory by key."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM memories WHERE key = ?", (key,))
            row = cursor.fetchone()

            if row and track_access:
                self._record_access(conn, row["id"])

            return self._row_to_memory(row) if row else None

    def _record_access(self, conn: sqlite3.Connection, memory_id: int) -> None:
        """Record that a memory was accessed."""
        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            UPDATE memories
            SET access_count = access_count + 1, last_accessed_at = ?
            WHERE id = ?
        """,
            (now, memory_id),
        )

    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        track_access: bool = True,
    ) -> list[Memory]:
        """Search memories using full-text search."""
        with self._connect() as conn:
            conditions = ["memories_fts MATCH ?"]
            params: list = [query]

            if tags:
                tag_filter = " OR ".join(f'tags LIKE \'%"{tag}"%\'' for tag in tags)
                conditions.append(f"({tag_filter})")

            if memory_types:
                type_values = [t.value for t in memory_types]
                type_placeholders = ",".join("?" * len(type_values))
                conditions.append(f"m.memory_type IN ({type_placeholders})")
                params.extend(type_values)

            where_clause = " AND ".join(conditions)
            params.append(limit)

            cursor = conn.execute(
                f"""
                SELECT m.* FROM memories m
                JOIN memories_fts fts ON m.id = fts.rowid
                WHERE {where_clause}
                ORDER BY m.importance DESC, m.updated_at DESC
                LIMIT ?
            """,
                params,
            )

            memories = [self._row_to_memory(row) for row in cursor.fetchall()]

            if track_access:
                for memory in memories:
                    if memory.id:
                        self._record_access(conn, memory.id)

            return memories

    def get_context(
        self,
        task: str | None = None,
        tags: list[str] | None = None,
        memory_types: list[MemoryType] | None = None,
        max_tokens: int = 2000,
        min_importance: int = 3,
        use_decay: bool = True,
        track_access: bool = True,
    ) -> str:
        """Get formatted context for prompt injection.

        Returns memories formatted for LLM consumption,
        respecting token budget.

        Args:
            task: Current task for relevance scoring (optional).
            tags: Filter by tags.
            memory_types: Filter by memory types.
            max_tokens: Maximum tokens for context.
            min_importance: Minimum importance threshold.
            use_decay: Apply time-based decay to importance.
            track_access: Record access for these memories.
        """
        with self._connect() as conn:
            conditions = ["importance >= ?"]
            params: list = [min_importance]

            if tags:
                tag_filter = " OR ".join(f'tags LIKE \'%"{tag}"%\'' for tag in tags)
                conditions.append(f"({tag_filter})")

            if memory_types:
                type_values = [t.value for t in memory_types]
                type_placeholders = ",".join("?" * len(type_values))
                conditions.append(f"memory_type IN ({type_placeholders})")
                params.extend(type_values)

            where_clause = " AND ".join(conditions)

            cursor = conn.execute(
                f"""
                SELECT * FROM memories
                WHERE {where_clause}
                ORDER BY importance DESC, updated_at DESC
            """,
                params,
            )

            # Build context respecting token budget (rough estimate: 4 chars = 1 token)
            memories_with_scores: list[tuple[Memory, float]] = []

            for row in cursor:
                memory = self._row_to_memory(row)
                if use_decay:
                    effective_importance = memory.decayed_importance
                else:
                    effective_importance = float(memory.importance)

                if effective_importance >= min_importance:
                    memories_with_scores.append((memory, effective_importance))

            # Sort by effective importance
            memories_with_scores.sort(key=lambda x: x[1], reverse=True)

            # Build context within token budget
            context_parts = []
            total_chars = 0
            max_chars = max_tokens * 4
            accessed_ids = []

            for memory, _ in memories_with_scores:
                formatted = memory.to_context()
                if total_chars + len(formatted) > max_chars:
                    break
                context_parts.append(formatted)
                total_chars += len(formatted)
                if memory.id:
                    accessed_ids.append(memory.id)

            # Record access for included memories
            if track_access and accessed_ids:
                now = datetime.utcnow().isoformat()
                for mem_id in accessed_ids:
                    conn.execute(
                        "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                        (now, mem_id),
                    )

            if not context_parts:
                return ""

            return "## Persistent Memory\n\n" + "\n".join(context_parts)

    def delete(self, key: str) -> bool:
        """Delete a memory by key."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def clear(
        self,
        tags: list[str] | None = None,
        memory_types: list[MemoryType] | None = None,
        source: MemorySource | None = None,
    ) -> int:
        """Clear memories, optionally filtered by tags, types, or source."""
        with self._connect() as conn:
            conditions = []
            params: list = []

            if tags:
                tag_filter = " OR ".join(f'tags LIKE \'%"{tag}"%\'' for tag in tags)
                conditions.append(f"({tag_filter})")

            if memory_types:
                type_values = [t.value for t in memory_types]
                type_placeholders = ",".join("?" * len(type_values))
                conditions.append(f"memory_type IN ({type_placeholders})")
                params.extend(type_values)

            if source:
                conditions.append("source = ?")
                params.append(source.value)

            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)
                cursor = conn.execute(f"DELETE FROM memories{where_clause}", params)
            else:
                cursor = conn.execute("DELETE FROM memories")

            return cursor.rowcount

    def list_all(
        self,
        tags: list[str] | None = None,
        memory_types: list[MemoryType] | None = None,
        source: MemorySource | None = None,
        limit: int = 100,
    ) -> list[Memory]:
        """List all memories, optionally filtered."""
        with self._connect() as conn:
            conditions = []
            params: list = []

            if tags:
                tag_filter = " OR ".join(f'tags LIKE \'%"{tag}"%\'' for tag in tags)
                conditions.append(f"({tag_filter})")

            if memory_types:
                type_values = [t.value for t in memory_types]
                type_placeholders = ",".join("?" * len(type_values))
                conditions.append(f"memory_type IN ({type_placeholders})")
                params.extend(type_values)

            if source:
                conditions.append("source = ?")
                params.append(source.value)

            params.append(limit)

            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)
            else:
                where_clause = ""

            cursor = conn.execute(
                f"""
                SELECT * FROM memories
                {where_clause}
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
            """,
                params,
            )

            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def count(
        self,
        tags: list[str] | None = None,
        memory_types: list[MemoryType] | None = None,
        source: MemorySource | None = None,
    ) -> int:
        """Count memories, optionally filtered."""
        with self._connect() as conn:
            conditions = []
            params: list = []

            if tags:
                tag_filter = " OR ".join(f'tags LIKE \'%"{tag}"%\'' for tag in tags)
                conditions.append(f"({tag_filter})")

            if memory_types:
                type_values = [t.value for t in memory_types]
                type_placeholders = ",".join("?" * len(type_values))
                conditions.append(f"memory_type IN ({type_placeholders})")
                params.extend(type_values)

            if source:
                conditions.append("source = ?")
                params.append(source.value)

            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)
            else:
                where_clause = ""

            cursor = conn.execute(f"SELECT COUNT(*) FROM memories{where_clause}", params)
            return cursor.fetchone()[0]

    def get_stats(self) -> dict:
        """Get memory statistics."""
        with self._connect() as conn:
            stats = {
                "total": 0,
                "by_type": {},
                "by_source": {},
                "by_importance": {},
                "avg_access_count": 0.0,
            }

            # Total count
            cursor = conn.execute("SELECT COUNT(*) FROM memories")
            stats["total"] = cursor.fetchone()[0]

            if stats["total"] == 0:
                return stats

            # By type
            cursor = conn.execute(
                "SELECT memory_type, COUNT(*) as cnt FROM memories GROUP BY memory_type"
            )
            for row in cursor:
                stats["by_type"][row["memory_type"]] = row["cnt"]

            # By source
            cursor = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM memories GROUP BY source"
            )
            for row in cursor:
                stats["by_source"][row["source"]] = row["cnt"]

            # By importance
            cursor = conn.execute(
                "SELECT importance, COUNT(*) as cnt FROM memories GROUP BY importance ORDER BY importance DESC"
            )
            for row in cursor:
                stats["by_importance"][row["importance"]] = row["cnt"]

            # Average access count
            cursor = conn.execute("SELECT AVG(access_count) FROM memories")
            stats["avg_access_count"] = cursor.fetchone()[0] or 0.0

            return stats

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Convert database row to Memory object."""
        # Handle optional new columns for backwards compatibility
        memory_type_str = row["memory_type"] if "memory_type" in row.keys() else "semantic"
        source_str = row["source"] if "source" in row.keys() else "user"
        access_count = row["access_count"] if "access_count" in row.keys() else 0
        last_accessed = row["last_accessed_at"] if "last_accessed_at" in row.keys() else None

        return Memory(
            id=row["id"],
            key=row["key"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            importance=row["importance"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            memory_type=MemoryType(memory_type_str),
            source=MemorySource(source_str),
            access_count=access_count,
            last_accessed_at=datetime.fromisoformat(last_accessed) if last_accessed else None,
        )
