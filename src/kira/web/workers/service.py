"""Worker service - business logic."""

from __future__ import annotations

import json
import secrets

import aiosqlite

from ..events import Event, EventType, event_manager


async def register_worker(
    db: aiosqlite.Connection,
    user_id: str,
    hostname: str = "",
    worker_version: str = "",
    capabilities: list[str] | None = None,
) -> dict:
    """Register or re-register a worker for a user.

    Uses upsert on the UNIQUE(user_id) constraint.
    """
    caps = capabilities or ["agent"]
    caps_json = json.dumps(caps)
    worker_id = secrets.token_hex(8)

    # Upsert: insert or update on conflict
    await db.execute(
        """INSERT INTO workers (id, user_id, hostname, worker_version, capabilities_json,
           status, last_heartbeat)
           VALUES (?, ?, ?, ?, ?, 'online', CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
               hostname = excluded.hostname,
               worker_version = excluded.worker_version,
               capabilities_json = excluded.capabilities_json,
               status = 'online',
               last_heartbeat = CURRENT_TIMESTAMP""",
        (worker_id, user_id, hostname, worker_version, caps_json),
    )
    await db.commit()

    # Fetch the actual worker (may be existing row if upserted)
    cursor = await db.execute("SELECT * FROM workers WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    worker = dict(row)

    # Publish worker online event to all boards the user is a member of
    board_cursor = await db.execute(
        "SELECT board_id FROM board_members WHERE user_id = ?", (user_id,)
    )
    board_rows = await board_cursor.fetchall()
    for br in board_rows:
        await event_manager.publish_to_board(
            br["board_id"],
            Event(
                event_type=EventType.WORKER_ONLINE,
                data={"worker_id": worker["id"], "user_id": user_id},
            ),
        )

    return worker


async def heartbeat(
    db: aiosqlite.Connection,
    worker_id: str,
    user_id: str,
    running_task_ids: list[str] | None = None,
) -> dict:
    """Process worker heartbeat. Returns cancel list for any cancelled tasks."""
    running_task_ids = running_task_ids or []

    await db.execute(
        """UPDATE workers SET last_heartbeat = CURRENT_TIMESTAMP,
           status = 'online' WHERE id = ? AND user_id = ?""",
        (worker_id, user_id),
    )
    await db.commit()

    # Check if any running tasks have been cancelled
    cancel_ids: list[str] = []
    if running_task_ids:
        placeholders = ",".join("?" for _ in running_task_ids)
        cursor = await db.execute(
            f"SELECT id FROM tasks WHERE id IN ({placeholders}) AND status = 'cancelled'",
            running_task_ids,
        )
        rows = await cursor.fetchall()
        cancel_ids = [r["id"] for r in rows]

    return {"status": "ok", "cancel_task_ids": cancel_ids}


async def get_workers(db: aiosqlite.Connection) -> list[dict]:
    """List all workers."""
    cursor = await db.execute("SELECT * FROM workers ORDER BY registered_at DESC")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_worker_for_user(db: aiosqlite.Connection, user_id: str) -> dict | None:
    """Get worker for a specific user."""
    cursor = await db.execute("SELECT * FROM workers WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_worker(db: aiosqlite.Connection, worker_id: str) -> dict | None:
    """Get a worker by ID."""
    cursor = await db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def mark_stale_workers(db: aiosqlite.Connection) -> int:
    """Mark workers as stale (>90s) or offline (>300s).

    Also fails any running tasks assigned to offline workers.
    Returns number of workers whose status changed.
    """
    changed = 0

    # Mark stale: last_heartbeat > 90 seconds ago, currently online
    cursor = await db.execute(
        """UPDATE workers SET status = 'stale'
           WHERE status = 'online'
           AND last_heartbeat < datetime('now', '-90 seconds')""",
    )
    changed += cursor.rowcount

    # Mark offline: last_heartbeat > 300 seconds ago, currently online or stale
    cursor = await db.execute(
        """UPDATE workers SET status = 'offline'
           WHERE status IN ('online', 'stale')
           AND last_heartbeat < datetime('now', '-300 seconds')""",
    )
    offline_count = cursor.rowcount
    changed += offline_count

    if offline_count > 0:
        # Fail running tasks for offline workers
        await db.execute(
            """UPDATE tasks SET status = 'failed',
               error_summary = 'Worker went offline',
               completed_at = CURRENT_TIMESTAMP
               WHERE status IN ('claimed', 'running')
               AND claimed_by_worker IN (
                   SELECT id FROM workers WHERE status = 'offline'
               )""",
        )

        # Update card agent_status for those failed tasks
        await db.execute(
            """UPDATE cards SET agent_status = 'failed'
               WHERE id IN (
                   SELECT card_id FROM tasks
                   WHERE status = 'failed'
                   AND error_summary = 'Worker went offline'
                   AND card_id IS NOT NULL
               )""",
        )

        # Publish offline events
        offline_cursor = await db.execute(
            "SELECT id, user_id FROM workers WHERE status = 'offline'"
        )
        offline_workers = await offline_cursor.fetchall()
        for w in offline_workers:
            board_cursor = await db.execute(
                "SELECT board_id FROM board_members WHERE user_id = ?", (w["user_id"],)
            )
            for br in await board_cursor.fetchall():
                await event_manager.publish_to_board(
                    br["board_id"],
                    Event(
                        event_type=EventType.WORKER_OFFLINE,
                        data={"worker_id": w["id"], "user_id": w["user_id"]},
                    ),
                )

    await db.commit()
    return changed
