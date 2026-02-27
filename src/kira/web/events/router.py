"""SSE streaming endpoint."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from ..db.database import get_db
from .manager import event_manager
from .models import Event, EventType

router = APIRouter(prefix="/api/events", tags=["events"])

# Events where the data is a flat entity dict that must be wrapped under a key.
# Events NOT in this map already have the correct structure (e.g., {"card_id": "..."}).
_ENTITY_WRAP_KEY: dict[EventType, str] = {
    EventType.CARD_CREATED: "card",
    EventType.CARD_UPDATED: "card",
    EventType.COLUMN_CREATED: "column",
    EventType.COLUMN_UPDATED: "column",
    EventType.COMMENT_ADDED: "comment",
    EventType.TASK_CREATED: "task",
    EventType.TASK_CLAIMED: "task",
    EventType.TASK_CANCELLED: "task",
    EventType.WORKER_ONLINE: "worker",
    EventType.WORKER_OFFLINE: "worker",
    EventType.BOARD_UPDATED: "board",
}


def _format_event(event: Event) -> dict[str, Any]:
    """Format an Event into the JSON structure the frontend expects.

    All events are sent as unnamed SSE messages (no 'event:' field) so the
    browser's EventSource.onmessage handler receives them. The event type
    is included in the JSON payload as 'type'.
    """
    wrap_key = _ENTITY_WRAP_KEY.get(event.event_type)
    if wrap_key:
        return {"type": event.event_type.value, wrap_key: event.data}
    return {"type": event.event_type.value, **event.data}


@router.get("/stream")
async def event_stream(
    board_id: str = Query(..., description="Board ID to subscribe to"),
    token: str = Query("", description="JWT token (EventSource can't send headers)"),
):
    """SSE stream for real-time board updates.

    Uses token query param because EventSource API doesn't support custom headers.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        from ..auth.service import decode_token

        user = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None

    # Verify user exists and has board access
    db = await get_db()
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user["sub"],))
    if not await cursor.fetchone():
        raise HTTPException(status_code=401, detail="User not found")

    # Verify board membership
    cursor = await db.execute(
        "SELECT 1 FROM board_members WHERE board_id = ? AND user_id = ?",
        (board_id, user["sub"]),
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=403, detail="Not a member of this board")

    async def generate():
        channel = f"board:{board_id}"
        queue = await event_manager.subscribe(channel)
        try:
            # Send initial presence event
            await event_manager.publish_to_board(
                board_id,
                Event(
                    event_type=EventType.USER_PRESENCE,
                    data={"user_id": user["sub"], "action": "joined"},
                ),
            )

            while True:
                try:
                    event: Event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {"data": json.dumps(_format_event(event))}
                except TimeoutError:
                    # Send heartbeat as unnamed message
                    yield {
                        "data": json.dumps({"type": "heartbeat", "timestamp": time.time()}),
                    }
        finally:
            await event_manager.unsubscribe(channel, queue)
            await event_manager.publish_to_board(
                board_id,
                Event(
                    event_type=EventType.USER_PRESENCE,
                    data={"user_id": user["sub"], "action": "left"},
                ),
            )

    return EventSourceResponse(generate())
