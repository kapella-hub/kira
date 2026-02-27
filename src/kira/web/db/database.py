"""Async SQLite connection manager (singleton pattern)."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

_db: aiosqlite.Connection | None = None
_db_path: str = ""


async def init_db(db_path: str) -> None:
    """Initialize the database connection and run schema."""
    global _db, _db_path
    _db_path = db_path

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")

    # Run schema
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text()
    await _db.executescript(schema_sql)
    await _db.commit()

    # Run migrations for existing databases
    await _run_migrations(_db)


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Add tables/columns that may be missing from older schemas."""
    # Migration: add automation columns to 'columns' table if missing
    cursor = await db.execute("PRAGMA table_info(columns)")
    existing = {row[1] for row in await cursor.fetchall()}
    new_cols = [
        ("agent_type", "TEXT DEFAULT ''"),
        ("agent_skill", "TEXT DEFAULT ''"),
        ("agent_model", "TEXT DEFAULT 'smart'"),
        ("auto_run", "INTEGER DEFAULT 0"),
        ("on_success_column_id", "TEXT DEFAULT ''"),
        ("on_failure_column_id", "TEXT DEFAULT ''"),
        ("max_loop_count", "INTEGER DEFAULT 3"),
        ("prompt_template", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in new_cols:
        if col_name not in existing:
            await db.execute(f"ALTER TABLE columns ADD COLUMN {col_name} {col_def}")

    # Migration: create workers table if missing
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='workers'"
    )
    if not await cursor.fetchone():
        await db.executescript("""
            CREATE TABLE workers (
                id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                hostname TEXT NOT NULL DEFAULT '',
                worker_version TEXT NOT NULL DEFAULT '',
                capabilities_json TEXT NOT NULL DEFAULT '["agent"]',
                status TEXT NOT NULL DEFAULT 'online'
                    CHECK (status IN ('online', 'offline', 'stale')),
                last_heartbeat TIMESTAMP,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_workers_user ON workers(user_id);
        """)

    # Migration: create tasks table if missing
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    if not await cursor.fetchone():
        await db.executescript("""
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
                task_type TEXT NOT NULL CHECK (task_type IN (
                    'agent_run', 'jira_import', 'jira_push', 'jira_sync',
                    'gitlab_link', 'gitlab_create_project', 'gitlab_push',
                    'board_plan', 'card_gen'
                )),
                board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                card_id TEXT REFERENCES cards(id) ON DELETE SET NULL,
                created_by TEXT NOT NULL REFERENCES users(id),
                assigned_to TEXT REFERENCES users(id),
                claimed_by_worker TEXT REFERENCES workers(id),
                agent_type TEXT DEFAULT '',
                agent_skill TEXT DEFAULT '',
                agent_model TEXT DEFAULT 'smart',
                prompt_text TEXT DEFAULT '',
                payload_json TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                    'pending', 'claimed', 'running', 'completed', 'failed', 'cancelled'
                )),
                priority INTEGER NOT NULL DEFAULT 0,
                source_column_id TEXT DEFAULT '',
                target_column_id TEXT DEFAULT '',
                failure_column_id TEXT DEFAULT '',
                loop_count INTEGER DEFAULT 0,
                max_loop_count INTEGER DEFAULT 3,
                error_summary TEXT DEFAULT '',
                output_comment_id TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                claimed_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_poll
                ON tasks(assigned_to, status) WHERE status IN ('pending', 'claimed');
            CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board_id, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_card
                ON tasks(card_id) WHERE card_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks(status, created_at) WHERE status = 'running';
        """)

    # Migration: remove jira fields from users if they exist (non-destructive: just ignore them)
    # SQLite doesn't support DROP COLUMN easily, so we leave them as dead columns

    # Migration: add gitlab columns to users if missing
    cursor = await db.execute("PRAGMA table_info(users)")
    user_cols = {row[1] for row in await cursor.fetchall()}
    if "gitlab_server" not in user_cols:
        await db.execute("ALTER TABLE users ADD COLUMN gitlab_server TEXT DEFAULT ''")
    if "gitlab_token_encrypted" not in user_cols:
        await db.execute("ALTER TABLE users ADD COLUMN gitlab_token_encrypted TEXT DEFAULT ''")

    # Migration: add 'board_plan' and 'card_gen' to tasks.task_type CHECK constraint
    # SQLite doesn't support ALTER CHECK, so we recreate the table if needed.
    cursor = await db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    row = await cursor.fetchone()
    if row and "card_gen" not in row[0]:
        # The table exists but lacks the card_gen type.
        # Recreate with the updated constraint.
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks_new (
                id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
                task_type TEXT NOT NULL CHECK (task_type IN (
                    'agent_run', 'jira_import', 'jira_push', 'jira_sync',
                    'gitlab_link', 'gitlab_create_project', 'gitlab_push',
                    'board_plan', 'card_gen'
                )),
                board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                card_id TEXT REFERENCES cards(id) ON DELETE SET NULL,
                created_by TEXT NOT NULL REFERENCES users(id),
                assigned_to TEXT REFERENCES users(id),
                claimed_by_worker TEXT REFERENCES workers(id),
                agent_type TEXT DEFAULT '',
                agent_skill TEXT DEFAULT '',
                agent_model TEXT DEFAULT 'smart',
                prompt_text TEXT DEFAULT '',
                payload_json TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                    'pending', 'claimed', 'running', 'completed', 'failed', 'cancelled'
                )),
                priority INTEGER NOT NULL DEFAULT 0,
                source_column_id TEXT DEFAULT '',
                target_column_id TEXT DEFAULT '',
                failure_column_id TEXT DEFAULT '',
                loop_count INTEGER DEFAULT 0,
                max_loop_count INTEGER DEFAULT 3,
                error_summary TEXT DEFAULT '',
                output_comment_id TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                claimed_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            );
            INSERT INTO tasks_new SELECT * FROM tasks;
            DROP TABLE tasks;
            ALTER TABLE tasks_new RENAME TO tasks;
            CREATE INDEX IF NOT EXISTS idx_tasks_poll
                ON tasks(assigned_to, status) WHERE status IN ('pending', 'claimed');
            CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board_id, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_card
                ON tasks(card_id) WHERE card_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks(status, created_at) WHERE status = 'running';
        """)

    # Migration: rename jira_payload_json -> payload_json in tasks table
    cursor = await db.execute("PRAGMA table_info(tasks)")
    task_cols = {row[1] for row in await cursor.fetchall()}
    if "jira_payload_json" in task_cols and "payload_json" not in task_cols:
        await db.execute("ALTER TABLE tasks RENAME COLUMN jira_payload_json TO payload_json")

    await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Get the active database connection."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
