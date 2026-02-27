"""Board service - business logic."""

from __future__ import annotations

import secrets

import aiosqlite

from ..events import Event, EventType, event_manager


async def list_boards(db: aiosqlite.Connection, user_id: str) -> list[dict]:
    """List boards the user is a member of."""
    cursor = await db.execute(
        """SELECT b.* FROM boards b
           JOIN board_members bm ON b.id = bm.board_id
           WHERE bm.user_id = ?
           ORDER BY b.updated_at DESC""",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def create_board(
    db: aiosqlite.Connection, name: str, description: str, owner_id: str
) -> dict:
    """Create a new board, add owner, and auto-share with all existing users."""
    board_id = secrets.token_hex(8)
    await db.execute(
        """INSERT INTO boards (id, name, description, owner_id)
           VALUES (?, ?, ?, ?)""",
        (board_id, name, description, owner_id),
    )
    await db.execute(
        "INSERT INTO board_members (board_id, user_id, role) VALUES (?, ?, 'owner')",
        (board_id, owner_id),
    )

    # Auto-share: add all other users as members
    cursor = await db.execute("SELECT id FROM users WHERE id != ?", (owner_id,))
    other_users = await cursor.fetchall()
    for user_row in other_users:
        await db.execute(
            "INSERT OR IGNORE INTO board_members (board_id, user_id, role) VALUES (?, ?, 'member')",
            (board_id, user_row["id"]),
        )

    await db.commit()

    cursor = await db.execute("SELECT * FROM boards WHERE id = ?", (board_id,))
    row = await cursor.fetchone()
    return dict(row)


async def add_user_to_all_boards(db: aiosqlite.Connection, user_id: str) -> None:
    """Add a user as member to all existing boards (called on login/register)."""
    cursor = await db.execute("SELECT id FROM boards")
    boards = await cursor.fetchall()
    for board_row in boards:
        await db.execute(
            "INSERT OR IGNORE INTO board_members (board_id, user_id, role) VALUES (?, ?, 'member')",
            (board_row["id"], user_id),
        )
    if boards:
        await db.commit()


# --- Member management ---


async def get_members(db: aiosqlite.Connection, board_id: str) -> list[dict]:
    """List all members of a board."""
    cursor = await db.execute(
        """SELECT bm.user_id, bm.role, u.username, u.display_name, u.avatar_url
           FROM board_members bm
           JOIN users u ON bm.user_id = u.id
           WHERE bm.board_id = ?""",
        (board_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def add_member(
    db: aiosqlite.Connection, board_id: str, user_id: str, role: str = "member"
) -> bool:
    """Add a member to a board. Returns False if already a member."""
    try:
        await db.execute(
            "INSERT INTO board_members (board_id, user_id, role) VALUES (?, ?, ?)",
            (board_id, user_id, role),
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def update_member_role(
    db: aiosqlite.Connection, board_id: str, user_id: str, role: str
) -> bool:
    """Update a member's role. Returns False if not a member."""
    cursor = await db.execute(
        "UPDATE board_members SET role = ? WHERE board_id = ? AND user_id = ?",
        (role, board_id, user_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def remove_member(db: aiosqlite.Connection, board_id: str, user_id: str) -> bool:
    """Remove a member from a board. Returns False if not a member."""
    cursor = await db.execute(
        "DELETE FROM board_members WHERE board_id = ? AND user_id = ?",
        (board_id, user_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_board(db: aiosqlite.Connection, board_id: str) -> dict | None:
    """Get a board by ID."""
    cursor = await db.execute("SELECT * FROM boards WHERE id = ?", (board_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_full_board(db: aiosqlite.Connection, board_id: str) -> dict | None:
    """Get board with all columns, cards, and members."""
    cursor = await db.execute("SELECT * FROM boards WHERE id = ?", (board_id,))
    board_row = await cursor.fetchone()
    if not board_row:
        return None

    board = dict(board_row)

    # Get columns
    col_cursor = await db.execute(
        "SELECT * FROM columns WHERE board_id = ? ORDER BY position", (board_id,)
    )
    columns_rows = await col_cursor.fetchall()

    # Get all cards for this board
    card_cursor = await db.execute(
        "SELECT * FROM cards WHERE board_id = ? ORDER BY position", (board_id,)
    )
    cards_rows = await card_cursor.fetchall()

    # Group cards by column
    cards_by_column: dict[str, list[dict]] = {}
    for card in cards_rows:
        card_dict = dict(card)
        col_id = card_dict["column_id"]
        cards_by_column.setdefault(col_id, []).append(card_dict)

    columns = []
    for col in columns_rows:
        col_dict = dict(col)
        col_dict["collapsed"] = bool(col_dict["collapsed"])
        col_dict["auto_run"] = bool(col_dict.get("auto_run", 0))
        col_dict["cards"] = cards_by_column.get(col_dict["id"], [])
        columns.append(col_dict)

    # Get members
    member_cursor = await db.execute(
        """SELECT bm.user_id, bm.role, u.username, u.display_name, u.avatar_url
           FROM board_members bm
           JOIN users u ON bm.user_id = u.id
           WHERE bm.board_id = ?""",
        (board_id,),
    )
    members = [dict(r) for r in await member_cursor.fetchall()]

    return {"board": board, "columns": columns, "members": members}


_BOARD_UPDATABLE_FIELDS = {"name", "description", "settings_json"}


async def update_board(db: aiosqlite.Connection, board_id: str, updates: dict) -> dict | None:
    """Update a board's fields."""
    sets = []
    values = []
    for key, val in updates.items():
        if val is not None and key in _BOARD_UPDATABLE_FIELDS:
            sets.append(f"{key} = ?")
            values.append(val)

    if not sets:
        return await get_board(db, board_id)

    sets.append("updated_at = CURRENT_TIMESTAMP")
    values.append(board_id)

    await db.execute(
        f"UPDATE boards SET {', '.join(sets)} WHERE id = ?",
        values,
    )
    await db.commit()

    board = await get_board(db, board_id)
    if board:
        await event_manager.publish_to_board(
            board_id, Event(event_type=EventType.BOARD_UPDATED, data=board)
        )
    return board


async def delete_board(db: aiosqlite.Connection, board_id: str) -> bool:
    """Delete a board and all related data (cascade)."""
    cursor = await db.execute("DELETE FROM boards WHERE id = ?", (board_id,))
    await db.commit()
    if cursor.rowcount > 0:
        await event_manager.publish_to_board(
            board_id,
            Event(event_type=EventType.BOARD_DELETED, data={"board_id": board_id}),
        )
        return True
    return False


# --- Column operations ---


async def create_column(
    db: aiosqlite.Connection,
    board_id: str,
    fields: dict,
) -> dict:
    """Create a new column in a board with all fields including automation config."""
    col_id = secrets.token_hex(8)

    # Get max position
    cursor = await db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM columns WHERE board_id = ?", (board_id,)
    )
    row = await cursor.fetchone()
    position = row[0] + 1

    name = fields.get("name", "New Column")
    color = fields.get("color", "#6366f1")
    wip_limit = fields.get("wip_limit", 0)
    agent_type = fields.get("agent_type", "")
    agent_skill = fields.get("agent_skill", "")
    agent_model = fields.get("agent_model", "smart")
    auto_run = int(fields.get("auto_run", False))
    on_success_column_id = fields.get("on_success_column_id", "")
    on_failure_column_id = fields.get("on_failure_column_id", "")
    max_loop_count = fields.get("max_loop_count", 3)
    prompt_template = fields.get("prompt_template", "")

    await db.execute(
        """INSERT INTO columns (id, board_id, name, position, color, wip_limit,
           agent_type, agent_skill, agent_model, auto_run,
           on_success_column_id, on_failure_column_id, max_loop_count, prompt_template)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            col_id,
            board_id,
            name,
            position,
            color,
            wip_limit,
            agent_type,
            agent_skill,
            agent_model,
            auto_run,
            on_success_column_id,
            on_failure_column_id,
            max_loop_count,
            prompt_template,
        ),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM columns WHERE id = ?", (col_id,))
    col = dict(await cursor.fetchone())
    col["collapsed"] = bool(col["collapsed"])
    col["auto_run"] = bool(col["auto_run"])

    await event_manager.publish_to_board(
        board_id, Event(event_type=EventType.COLUMN_CREATED, data=col)
    )
    return col


_COLUMN_UPDATABLE_FIELDS = {
    "name", "color", "wip_limit", "collapsed", "agent_type", "agent_skill",
    "agent_model", "auto_run", "on_success_column_id", "on_failure_column_id",
    "max_loop_count", "prompt_template",
}


async def update_column(db: aiosqlite.Connection, column_id: str, updates: dict) -> dict | None:
    """Update a column."""
    sets = []
    values = []
    for key, val in updates.items():
        if val is not None and key in _COLUMN_UPDATABLE_FIELDS:
            if key in ("collapsed", "auto_run"):
                val = int(val)
            sets.append(f"{key} = ?")
            values.append(val)

    if not sets:
        cursor = await db.execute("SELECT * FROM columns WHERE id = ?", (column_id,))
        row = await cursor.fetchone()
        if row:
            d = dict(row)
            d["collapsed"] = bool(d["collapsed"])
            return d
        return None

    values.append(column_id)
    await db.execute(f"UPDATE columns SET {', '.join(sets)} WHERE id = ?", values)
    await db.commit()

    cursor = await db.execute("SELECT * FROM columns WHERE id = ?", (column_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    col = dict(row)
    col["collapsed"] = bool(col["collapsed"])

    await event_manager.publish_to_board(
        col["board_id"], Event(event_type=EventType.COLUMN_UPDATED, data=col)
    )
    return col


async def delete_column(db: aiosqlite.Connection, column_id: str) -> bool:
    """Delete a column."""
    cursor = await db.execute("SELECT board_id FROM columns WHERE id = ?", (column_id,))
    row = await cursor.fetchone()
    if not row:
        return False

    board_id = row["board_id"]
    await db.execute("DELETE FROM columns WHERE id = ?", (column_id,))
    await db.commit()

    await event_manager.publish_to_board(
        board_id,
        Event(event_type=EventType.COLUMN_DELETED, data={"column_id": column_id}),
    )
    return True


async def reorder_columns(db: aiosqlite.Connection, board_id: str, column_ids: list[str]) -> None:
    """Reorder columns by setting position based on list order."""
    for position, col_id in enumerate(column_ids):
        await db.execute(
            "UPDATE columns SET position = ? WHERE id = ? AND board_id = ?",
            (position, col_id, board_id),
        )
    await db.commit()

    await event_manager.publish_to_board(
        board_id,
        Event(event_type=EventType.COLUMN_REORDERED, data={"column_ids": column_ids}),
    )
