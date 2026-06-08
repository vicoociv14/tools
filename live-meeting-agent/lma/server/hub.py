from __future__ import annotations

import asyncio
import logging
import queue
from typing import Optional

from ..brain.state import Segment

log = logging.getLogger(__name__)


class TranscriptHub:
    """Bridges Segments published from Brain worker threads to async WebSocket
    clients. `publish` is thread-safe; `add_subscriber` returns a queue the WS
    handler drains."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: set[queue.SimpleQueue] = set()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add_subscriber(self) -> "queue.SimpleQueue":
        q: queue.SimpleQueue = queue.SimpleQueue()
        self._subscribers.add(q)
        return q

    def remove_subscriber(self, q: "queue.SimpleQueue") -> None:
        self._subscribers.discard(q)

    def _fanout(self, seg: Segment) -> None:
        for q in list(self._subscribers):
            q.put_nowait(seg)

    def publish(self, seg: Segment) -> None:
        """Thread-safe: schedule a fan-out on the server event loop."""
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._fanout, seg)
        except RuntimeError:
            log.debug("hub publish after loop close", exc_info=True)
