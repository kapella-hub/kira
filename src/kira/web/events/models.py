"""SSE event models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    # Card events
    CARD_CREATED = "card_created"
    CARD_MOVED = "card_moved"
    CARD_UPDATED = "card_updated"
    CARD_DELETED = "card_deleted"
    # Column events
    COLUMN_CREATED = "column_created"
    COLUMN_UPDATED = "column_updated"
    COLUMN_DELETED = "column_deleted"
    COLUMN_REORDERED = "column_reordered"
    # Comment events
    COMMENT_ADDED = "comment_added"
    COMMENT_DELETED = "comment_deleted"
    # Task events (agent/jira operations)
    TASK_CREATED = "task_created"
    TASK_CLAIMED = "task_claimed"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    # Worker events
    WORKER_ONLINE = "worker_online"
    WORKER_OFFLINE = "worker_offline"
    # Board events
    BOARD_UPDATED = "board_updated"
    BOARD_DELETED = "board_deleted"
    # Misc
    USER_PRESENCE = "user_presence"
    HEARTBEAT = "heartbeat"


@dataclass
class Event:
    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    channel: str = ""
