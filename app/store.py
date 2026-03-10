from collections import deque
from typing import Optional

from fastapi import WebSocket

from app.config import settings
from app.logger import log
from app.models import AlertEvent, AlertGroup

# Re-exported for backwards-compat with tests
GROUP_WINDOW_SECONDS = settings.group_window_seconds


def _merge_categorized(
    a: dict[str, list[str]], b: dict[str, list[str]]
) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = {}
    for area, cities in a.items():
        merged.setdefault(area, set()).update(cities)
    for area, cities in b.items():
        merged.setdefault(area, set()).update(cities)
    return {area: sorted(cities) for area, cities in sorted(merged.items())}


class AlertStore:
    """In-memory store for active alerts (one per category) and grouped history."""

    def __init__(self, max_history: int = 50) -> None:
        self._active: dict[str, AlertEvent] = {}   # cat → AlertEvent
        self._history: deque[AlertEvent] = deque(maxlen=max_history)
        self._seen_ids: set[str] = set()
        self._groups: list[AlertGroup] = []

    def is_new(self, alert_id: str) -> bool:
        return alert_id not in self._seen_ids

    def get_active_by_cat(self, cat: str) -> Optional[AlertEvent]:
        return self._active.get(cat)

    def set_alert(self, alert: AlertEvent, is_ended: bool = False) -> None:
        self._seen_ids.add(alert.id)
        if not is_ended:
            self._active[alert.cat] = alert
        self._history.appendleft(alert)
        self._update_groups(alert, is_ended)
        log.info("Alert recorded id=%s cat=%s is_ended=%s areas=%d", alert.id, alert.cat, is_ended, len(alert.areas))

    def _update_groups(self, event: AlertEvent, is_ended: bool) -> None:
        if self._groups and not self._groups[0].is_ended and not is_ended:
            last = self._groups[0]
            delta = (event.received_at - last.to_time).total_seconds()
            if last.cat == event.cat and delta <= settings.group_window_seconds:
                self._groups[0] = AlertGroup(
                    cat=last.cat,
                    cat_label=last.cat_label,
                    title=last.title,
                    from_time=last.from_time,
                    to_time=event.received_at,
                    areas=sorted(set(last.areas) | set(event.areas)),
                    categorized_areas=_merge_categorized(last.categorized_areas, event.categorized_areas),
                    is_ended=False,
                )
                return
        self._groups.insert(0, AlertGroup(
            cat=event.cat,
            cat_label=event.cat_label,
            title=event.title,
            from_time=event.received_at,
            to_time=event.received_at,
            areas=sorted(event.areas),
            categorized_areas=event.categorized_areas,
            is_ended=is_ended,
        ))
        if len(self._groups) > settings.max_groups:
            self._groups.pop()

    def clear(self, cat: Optional[str] = None) -> bool:
        """Clear one category (by cat) or all active alerts. Returns True if anything changed."""
        if cat is not None:
            if cat in self._active:
                log.info("Alert cleared cat=%s", cat)
                del self._active[cat]
                return True
            return False
        elif self._active:
            log.info("All alerts cleared (%d)", len(self._active))
            self._active.clear()
            return True
        return False

    @property
    def current(self) -> list[AlertEvent]:
        return list(self._active.values())

    @property
    def history(self) -> list[AlertEvent]:
        return list(self._history)

    @property
    def groups(self) -> list[AlertGroup]:
        return list(self._groups)


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
