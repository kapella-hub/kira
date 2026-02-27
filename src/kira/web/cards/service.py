"""Card service - business logic."""

from __future__ import annotations

import secrets

import aiosqlite

from ..events import Event, EventType, event_manager


def is_card_locked(card: dict) -> bool:
    """A card is locked when an agent is actively working on it."""
    return card.get("agent_status", "") in ("pending", "running")


async def get_card(db: aiosqlite.Connection, card_id: str) -> dict | None:
    cursor = await db.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def create_card(
    db: aiosqlite.Connection,
    column_id: str,
    title: str,
    user_id: str,
    description: str = "",
    assignee_id: str | None = None,
    priority: str = "medium",
    labels: str = "[]",
    due_date: str | None = None,
) -> dict:
    card_id = secrets.token_hex(8)

    # Get board_id from column
    cursor = await db.execute("SELECT board_id FROM columns WHERE id = ?", (column_id,))
    col_row = await cursor.fetchone()
    if not col_row:
        raise ValueError(f"Column {column_id} not found")
    board_id = col_row["board_id"]

    # Get next position
    cursor = await db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM cards WHERE column_id = ?", (column_id,)
    )
    pos_row = await cursor.fetchone()
    position = pos_row[0] + 1

    await db.execute(
        """INSERT INTO cards (id, column_id, board_id, title, description, position,
           assignee_id, priority, labels, due_date, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            card_id,
            column_id,
            board_id,
            title,
            description,
            position,
            assignee_id,
            priority,
            labels,
            due_date,
            user_id,
        ),
    )
    await db.commit()

    card = await get_card(db, card_id)
    await event_manager.publish_to_board(
        board_id, Event(event_type=EventType.CARD_CREATED, data=card)
    )
    return card


_CARD_UPDATABLE_FIELDS = {
    "title",
    "description",
    "assignee_id",
    "priority",
    "labels",
    "due_date",
    "column_id",
    "position",
    "agent_status",
    "jira_key",
    "jira_sync_status",
}


async def update_card(db: aiosqlite.Connection, card_id: str, updates: dict) -> dict | None:
    card = await get_card(db, card_id)
    if not card:
        return None

    sets = []
    values = []
    for key, val in updates.items():
        if val is not None and key in _CARD_UPDATABLE_FIELDS:
            sets.append(f"{key} = ?")
            values.append(val)

    if not sets:
        return card

    sets.append("updated_at = CURRENT_TIMESTAMP")
    values.append(card_id)

    await db.execute(f"UPDATE cards SET {', '.join(sets)} WHERE id = ?", values)
    await db.commit()

    card = await get_card(db, card_id)
    await event_manager.publish_to_board(
        card["board_id"], Event(event_type=EventType.CARD_UPDATED, data=card)
    )
    return card


async def delete_card(db: aiosqlite.Connection, card_id: str) -> bool:
    card = await get_card(db, card_id)
    if not card:
        return False

    board_id = card["board_id"]
    await db.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    await db.commit()

    await event_manager.publish_to_board(
        board_id,
        Event(event_type=EventType.CARD_DELETED, data={"card_id": card_id}),
    )
    return True


async def move_card(
    db: aiosqlite.Connection,
    card_id: str,
    column_id: str,
    position: int,
    user_id: str | None = None,
    skip_automation: bool = False,
) -> dict | None:
    card = await get_card(db, card_id)
    if not card:
        return None

    from_column = card["column_id"]

    # Shift cards in the target column to make room
    await db.execute(
        "UPDATE cards SET position = position + 1 WHERE column_id = ? AND position >= ?",
        (column_id, position),
    )

    # Move the card
    await db.execute(
        """UPDATE cards SET column_id = ?, position = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (column_id, position, card_id),
    )

    # Compact positions in the source column if it changed
    if from_column != column_id:
        await _compact_positions(db, from_column)

    await db.commit()

    card = await get_card(db, card_id)
    await event_manager.publish_to_board(
        card["board_id"],
        Event(
            event_type=EventType.CARD_MOVED,
            data={
                "card_id": card_id,
                "from_column": from_column,
                "to_column": column_id,
                "position": position,
                "card": card,
            },
        ),
    )

    # Trigger automation if card moved to a new column
    if from_column != column_id and not skip_automation:
        cursor = await db.execute("SELECT * FROM columns WHERE id = ?", (column_id,))
        col_row = await cursor.fetchone()
        if col_row:
            col_dict = dict(col_row)
            col_dict["auto_run"] = bool(col_dict.get("auto_run", 0))
            from ..automation.trigger import maybe_trigger

            await maybe_trigger(db, card, col_dict, user_id or card.get("created_by", ""))

    return card


async def reorder_cards(db: aiosqlite.Connection, column_id: str, card_ids: list[str]) -> None:
    for position, cid in enumerate(card_ids):
        await db.execute(
            "UPDATE cards SET position = ? WHERE id = ? AND column_id = ?",
            (position, cid, column_id),
        )
    await db.commit()

    # Get board_id for the event
    cursor = await db.execute("SELECT board_id FROM columns WHERE id = ?", (column_id,))
    col_row = await cursor.fetchone()
    if col_row:
        await event_manager.publish_to_board(
            col_row["board_id"],
            Event(
                event_type=EventType.CARD_UPDATED,
                data={"column_id": column_id, "card_ids": card_ids},
            ),
        )


async def _compact_positions(db: aiosqlite.Connection, column_id: str) -> None:
    """Reorder card positions in a column to be sequential from 0."""
    cursor = await db.execute(
        "SELECT id FROM cards WHERE column_id = ? ORDER BY position", (column_id,)
    )
    rows = await cursor.fetchall()
    for i, row in enumerate(rows):
        await db.execute("UPDATE cards SET position = ? WHERE id = ?", (i, row["id"]))


# --- Comments ---


async def get_comments(db: aiosqlite.Connection, card_id: str) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM card_comments WHERE card_id = ? ORDER BY created_at",
        (card_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def create_comment(
    db: aiosqlite.Connection, card_id: str, user_id: str, content: str
) -> dict:
    comment_id = secrets.token_hex(8)

    await db.execute(
        "INSERT INTO card_comments (id, card_id, user_id, content) VALUES (?, ?, ?, ?)",
        (comment_id, card_id, user_id, content),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM card_comments WHERE id = ?", (comment_id,))
    comment = dict(await cursor.fetchone())

    # Get board_id for event
    card = await get_card(db, card_id)
    if card:
        await event_manager.publish_to_board(
            card["board_id"],
            Event(event_type=EventType.COMMENT_ADDED, data=comment),
        )
    return comment


async def delete_comment(db: aiosqlite.Connection, comment_id: str) -> bool:
    # Get card_id for event
    cursor = await db.execute(
        """SELECT cc.card_id, c.board_id FROM card_comments cc
           JOIN cards c ON cc.card_id = c.id WHERE cc.id = ?""",
        (comment_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return False

    board_id = row["board_id"]
    await db.execute("DELETE FROM card_comments WHERE id = ?", (comment_id,))
    await db.commit()

    await event_manager.publish_to_board(
        board_id,
        Event(event_type=EventType.COMMENT_DELETED, data={"comment_id": comment_id}),
    )
    return True
