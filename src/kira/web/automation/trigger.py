"""Automation trigger - creates tasks when cards enter auto_run columns."""

from __future__ import annotations

import aiosqlite

from ..tasks import service as task_service
from .prompt import render_prompt


async def maybe_trigger(
    db: aiosqlite.Connection,
    card: dict,
    column: dict,
    user_id: str,
) -> dict | None:
    """Check if column should auto-trigger an agent task on card entry.

    Returns created task dict, or None if no automation.
    """
    if not column.get("auto_run") or not column.get("agent_type"):
        return None

    # Check loop count (circuit breaker)
    loop_count = await _get_loop_count(db, card["id"], column["id"])
    max_loops = column.get("max_loop_count", 3)
    if loop_count >= max_loops:
        return None

    prompt = render_prompt(column.get("prompt_template", ""), card, column)
    assigned_to = card.get("assignee_id") or user_id

    task = await task_service.create_task(
        db,
        task_type="agent_run",
        board_id=card["board_id"],
        card_id=card["id"],
        created_by=user_id,
        assigned_to=assigned_to,
        agent_type=column.get("agent_type", ""),
        agent_skill=column.get("agent_skill", ""),
        agent_model=column.get("agent_model", "smart"),
        prompt_text=prompt,
        source_column_id=column["id"],
        target_column_id=column.get("on_success_column_id", ""),
        failure_column_id=column.get("on_failure_column_id", ""),
        loop_count=loop_count,
        max_loop_count=max_loops,
    )
    return task


async def _get_loop_count(db: aiosqlite.Connection, card_id: str, column_id: str) -> int:
    """Count how many tasks have been created for this card from this column."""
    cursor = await db.execute(
        """SELECT COUNT(*) FROM tasks
           WHERE card_id = ? AND source_column_id = ?""",
        (card_id, column_id),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0
