"""FastAPI dependency injection."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
import jwt
from fastapi import Depends, HTTPException, Request

from .db.database import get_db


async def _get_db() -> aiosqlite.Connection:
    return await get_db()


Db = Annotated[aiosqlite.Connection, Depends(_get_db)]


async def _get_current_user(request: Request) -> dict:
    """Extract and validate JWT from Authorization header.

    Also verifies the user still exists in the DB (handles stale tokens
    after server restart with re-seeded data).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        from .auth.service import decode_token

        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None

    # Verify user still exists in the DB
    db = await get_db()
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (payload["sub"],))
    if not await cursor.fetchone():
        raise HTTPException(status_code=401, detail="User not found. Please log in again.")

    return payload


CurrentUser = Annotated[dict, Depends(_get_current_user)]


async def verify_board_access(db: aiosqlite.Connection, board_id: str, user_id: str) -> None:
    """Raise 403 if user is not a member of the board."""
    cursor = await db.execute(
        "SELECT 1 FROM board_members WHERE board_id = ? AND user_id = ?",
        (board_id, user_id),
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=403, detail="Not a member of this board")


async def get_board_id_for_card(db: aiosqlite.Connection, card_id: str) -> str:
    """Look up the board_id for a card. Raises 404 if not found."""
    cursor = await db.execute("SELECT board_id FROM cards WHERE id = ?", (card_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Card not found")
    return row["board_id"]


async def get_board_id_for_column(db: aiosqlite.Connection, column_id: str) -> str:
    """Look up the board_id for a column. Raises 404 if not found."""
    cursor = await db.execute("SELECT board_id FROM columns WHERE id = ?", (column_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Column not found")
    return row["board_id"]


async def get_board_id_for_comment(db: aiosqlite.Connection, comment_id: str) -> str:
    """Look up the board_id for a comment via its card. Raises 404 if not found."""
    cursor = await db.execute(
        """SELECT c.board_id FROM card_comments cc
           JOIN cards c ON cc.card_id = c.id
           WHERE cc.id = ?""",
        (comment_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    return row["board_id"]
