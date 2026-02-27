"""EventManager - in-memory pub/sub for SSE events."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict

from .models import Event


class EventManager:
    """In-memory pub/sub for SSE events."""

    def __init__(self) -> None:
        self._channels: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def subscribe(self, channel: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._channels[channel].add(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        self._channels[channel].discard(queue)
        if not self._channels[channel]:
            del self._channels[channel]

    async def publish(self, channel: str, event: Event) -> None:
        for queue in list(self._channels.get(channel, [])):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    async def publish_to_board(self, board_id: str, event: Event) -> None:
        """Convenience: publish to board:{board_id} channel."""
        event.channel = f"board:{board_id}"
        await self.publish(f"board:{board_id}", event)


# Singleton instance
event_manager = EventManager()
