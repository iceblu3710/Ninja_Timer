"""In-process event bus for live browser updates."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def utc_sent_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LiveEvent:
    type: str
    data: dict[str, Any]
    sent_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "sent_at": self.sent_at,
            "data": self.data,
        }


class EventBus:
    """Fan out backend state changes to connected WebSocket clients."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def publish(self, event_type: str, data: dict[str, Any] | None = None) -> LiveEvent:
        event = LiveEvent(type=event_type, sent_at=utc_sent_at(), data=data or {})
        await self._broadcast(event)
        return event

    async def _broadcast(self, event: LiveEvent) -> None:
        async with self._lock:
            connections = list(self._connections)

        stale: list[WebSocket] = []
        payload = event.as_dict()
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception as exc:  # pragma: no cover - defensive cleanup path
                logger.debug("Dropping stale websocket connection: %s", exc)
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self._connections.discard(websocket)


event_bus = EventBus()
