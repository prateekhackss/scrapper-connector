"""
ConnectorOS Scout — SSE Broadcaster

Handles Server-Sent Events (SSE) to stream live pipeline logs to the frontend.

Thread-safe: uses the main asyncio event loop for all queue operations,
so it works even when called from background threads.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

# Shared state — must be set once at startup
_main_loop: asyncio.AbstractEventLoop | None = None
_subscribers: set[asyncio.Queue] = set()


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Call this once at application startup to capture the main event loop."""
    global _main_loop
    _main_loop = loop


def publish_event_sync(stage: str, message: str, level: str = "info") -> None:
    """Synchronous publish — safe to call from any thread."""
    if not _subscribers or _main_loop is None:
        return

    event_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "stage": stage,
        "message": message,
        "level": level,
    }
    payload = f"data: {json.dumps(event_data)}\n\n"

    def _put():
        dead = set()
        for queue in _subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead.add(queue)
        for q in dead:
            _subscribers.discard(q)

    # Schedule delivery on the main loop, thread-safe
    _main_loop.call_soon_threadsafe(_put)


async def publish_event(stage: str, message: str, level: str = "info") -> None:
    """
    Async publish — can be awaited from inside an async function.
    Works when called from the main event loop OR a background coroutine.
    """
    if not _subscribers:
        return

    event_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "stage": stage,
        "message": message,
        "level": level,
    }
    payload = f"data: {json.dumps(event_data)}\n\n"

    dead = set()
    for queue in _subscribers:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            dead.add(queue)
    for q in dead:
        _subscribers.discard(q)


async def event_generator() -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE events for a single connected client.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(queue)

    try:
        # Send initial connection confirmation
        init_event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "stage": "system",
            "message": "✔ Connected to real-time log stream.",
            "level": "info"
        }
        yield f"data: {json.dumps(init_event)}\n\n"

        while True:
            message = await queue.get()
            yield message
    except asyncio.CancelledError:
        raise
    finally:
        _subscribers.discard(queue)
