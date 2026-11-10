"""In-process pub/sub that bridges worker threads to WebSocket clients."""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._subs.add((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = {s for s in self._subs if s[1] is not q}

    def publish(self, type_: str, data: Any = None) -> None:
        event = {"type": type_, "ts": time.time(), "data": data}
        with self._lock:
            subs = list(self._subs)
        for loop, q in subs:
            def put(q=q) -> None:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # slow consumer: drop rather than block producers
            try:
                loop.call_soon_threadsafe(put)
            except RuntimeError:
                self.unsubscribe(q)  # loop closed
