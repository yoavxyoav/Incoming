from collections import deque
from typing import Optional

from fastapi import WebSocket

from app.logger import log
from app.models import AlertEvent


class AlertStore:
    """In-memory store for the current alert and recent history."""

    def __init__(self, max_history: int = 50) -> None:
        self._current: Optional[AlertEvent] = None
        self._history: deque[AlertEvent] = deque(maxlen=max_history)
        self._seen_ids: set[str] = set()

    def is_new(self, alert_id: str) -> bool:
        return alert_id not in self._seen_ids

    def set_alert(self, alert: AlertEvent) -> None:
        self._seen_ids.add(alert.id)
        self._current = alert
        self._history.appendleft(alert)
        log.info("New alert recorded id=%s title=%s areas=%d", alert.id, alert.title, len(alert.areas))

    def clear(self) -> bool:
        """Returns True if there was an active alert that got cleared."""
        if self._current is not None:
            log.info("Alert cleared (was id=%s)", self._current.id)
            self._current = None
            return True
        return False

    @property
    def current(self) -> Optional[AlertEvent]:
        return self._current

    @property
    def history(self) -> list[AlertEvent]:
        return list(self._history)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        log.info("WS client connected, total=%d", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        log.info("WS client disconnected, total=%d", len(self._clients))

    async def broadcast(self, data: dict[str, object]) -> None:
        dead: set[WebSocket] = set()
        for ws in set(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def count(self) -> int:
        return len(self._clients)


# Global singletons — injected into app state at startup
store = AlertStore()
manager = ConnectionManager()
