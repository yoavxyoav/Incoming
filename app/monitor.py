import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app import geo
from app.config import settings
from app.logger import log, raw_log
from app.models import CATEGORY_LABELS, AlertEvent, OrefAlertRaw
from app.store import ConnectionManager, AlertStore

OREF_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def _build_event(raw: OrefAlertRaw) -> AlertEvent:
    categorized = geo.categorize(raw.data)
    return AlertEvent(
        id=raw.id,
        cat=raw.cat,
        cat_label=CATEGORY_LABELS.get(raw.cat, f"Category {raw.cat}"),
        title=raw.title,
        desc=raw.desc,
        areas=raw.data,
        categorized_areas=categorized,
        received_at=datetime.now(timezone.utc),
    )


def _filter_region(alert: OrefAlertRaw) -> bool:
    if settings.region == "*":
        return True
    return settings.region in alert.data


# Titles Oref sends to signal an event has ended or it's safe — not a real threat
ALL_CLEAR_TITLES: frozenset[str] = frozenset([
    "האירוע הסתיים",
    "הסתיים",
    "ניתן לצאת מהמרחב המוגן",
    "ניתן לחזור לשגרה",
    "ניתן לצאת",
    "כל הכוחות בשטח",
])


def _is_all_clear(alert: OrefAlertRaw) -> bool:
    return alert.title.strip() in ALL_CLEAR_TITLES


def _is_test(alert: OrefAlertRaw) -> bool:
    if settings.include_test_alerts:
        return False
    return any("בדיקה" in item for item in alert.data) or alert.cat in ("101", "102", "103")


async def _fetch_alert(client: httpx.AsyncClient) -> Optional[OrefAlertRaw]:
    try:
        resp = await client.get(OREF_URL, headers=OREF_HEADERS, timeout=5.0)
        resp.raise_for_status()
        text = resp.text.replace("\x00", "").strip()
        if not text or text.isspace():
            return None
        data = resp.json()
        if not data or not data.get("id"):
            return None
        return OrefAlertRaw(**data)
    except httpx.HTTPStatusError as exc:
        log.warning("Oref HTTP error: %s", exc)
    except Exception as exc:
        log.debug("Oref fetch error: %s", exc)
    return None


async def poll_loop(store: AlertStore, manager: ConnectionManager) -> None:
    """Main async polling loop. Runs forever."""
    log.info("Starting Oref polling (region=%s, interval=%.1fs)", settings.region, settings.poll_interval)

    global _quiet_streak_reset
    quiet_streak: int = 0
    was_active: bool = False   # tracks transitions for raw log quiet markers

    async with httpx.AsyncClient() as client:
        while True:
            try:
                if _quiet_streak_reset:
                    quiet_streak = 0
                    _quiet_streak_reset = False

                raw = await _fetch_alert(client)

                if raw is None or _is_test(raw):
                    if was_active:
                        raw_log({"type": "quiet_start"})
                        was_active = False
                    quiet_streak += 1
                    poll_secs = settings.poll_interval or 1.0

                    # Tier 2: dismiss the active alert card after auto_clear_minutes of silence
                    grace_polls = max(1, round(settings.auto_clear_minutes * 60 / poll_secs))
                    if quiet_streak >= grace_polls:
                        active_snapshot = store.current  # snapshot before clearing
                        if active_snapshot:
                            now = datetime.now(timezone.utc)
                            store.clear()
                            store.end_all_active_groups(now, explicitly=False)
                            groups_payload = [g.model_dump(mode="json") for g in store.groups]
                            for ev in active_snapshot:
                                ended_payload = {
                                    **ev.model_dump(mode="json"),
                                    "clear_after_ms": settings.all_clear_display_seconds * 1000,
                                }
                                await manager.broadcast({"type": "ended", "payload": ended_payload})
                            await manager.broadcast({"type": "groups", "payload": groups_payload})
                elif _filter_region(raw):
                    raw_log({
                        "type": "all_clear" if _is_all_clear(raw) else "alert",
                        "id": raw.id,
                        "cat": raw.cat,
                        "title": raw.title,
                        "desc": raw.desc,
                        "areas": raw.data,
                    })
                    was_active = True
                    if store.is_new(raw.id):
                        event = _build_event(raw)
                        if _is_all_clear(raw):
                            # is_new(raw.id) already deduplicates same-event replays (Oref repeats
                            # the same ID across polls). We intentionally process every distinct
                            # all-clear ID so that sequential all-clears for *different* areas
                            # (each with a unique ID) are each handled independently.
                            active_snapshot = list(store._active.values())  # snapshot before any changes
                            ac_areas = set(event.areas)

                            # Same-cat clear
                            store.resolve_areas(raw.cat, event.areas, event.received_at)
                            store.mark_ended(event.id, raw.cat)
                            store.end_group_for_cat(raw.cat, event.received_at, explicitly=True)
                            store.clear(cat=raw.cat)

                            # Cross-cat clear: cat=10 is Oref's universal all-clear signal.
                            # 89% of cat=10 all-clears have area overlap with active cat=1/6 alerts.
                            # End any other active group whose areas overlap with the all-clear areas.
                            for ev in active_snapshot:
                                if ev.cat == raw.cat:
                                    continue
                                if ac_areas & set(ev.areas):
                                    store.resolve_areas(ev.cat, event.areas, event.received_at)
                                    store.end_group_for_cat(ev.cat, event.received_at, explicitly=True)
                                    store.clear(cat=ev.cat)
                                    log.info("Cross-cat all-clear: ended cat=%s via cat=%s all-clear", ev.cat, raw.cat)

                            groups_payload = [g.model_dump(mode="json") for g in store.groups]
                            for ev in active_snapshot:
                                if ev.cat != raw.cat and not (ac_areas & set(ev.areas)):
                                    continue
                                # For same-cat: use the original alert's areas so the frontend
                                # knows all areas are cleared (all-clear ends the whole event).
                                # For cross-cat: use the all-clear's areas (only those overlap).
                                cleared_areas = ev.areas if ev.cat == raw.cat else list(event.areas)
                                payload = {
                                    **ev.model_dump(mode="json"),
                                    "areas": cleared_areas,
                                    "clear_after_ms": settings.all_clear_display_seconds * 1000,
                                }
                                await manager.broadcast({"type": "ended", "payload": payload})
                            await manager.broadcast({"type": "groups", "payload": groups_payload})
                        else:
                            quiet_streak = 0
                            store.set_alert(event)
                            payload = event.model_dump(mode="json")
                            await manager.broadcast({"type": "alert", "payload": payload})
                            await manager.broadcast({"type": "groups", "payload": [g.model_dump(mode="json") for g in store.groups]})
                            await _notify(event)

            except Exception as exc:
                log.error("Unhandled monitor error: %s", exc)

            # Heartbeat — lets the frontend blink its LED every poll
            await manager.broadcast({"type": "tick", "payload": None})

            await asyncio.sleep(settings.poll_interval)


_quiet_streak_reset: bool = False


def reset_quiet_streak() -> None:
    """Signal the poll loop to reset quiet_streak (e.g. after a sim alert injection)."""
    global _quiet_streak_reset
    _quiet_streak_reset = True


_apprise_instance: Optional[Any] = None


def _get_apprise() -> Optional[Any]:
    """Return a shared Apprise instance (built once)."""
    global _apprise_instance
    if _apprise_instance is None:
        try:
            import apprise

            ap = apprise.Apprise()
            for url in settings.notifiers.split():
                ap.add(url)
            _apprise_instance = ap
        except ImportError:
            log.warning("apprise not installed; skipping notifications")
    return _apprise_instance


def _mqtt_publish(host: str, port: int, user: str, password: str, topic: str, areas: list[str]) -> None:
    """Blocking MQTT publish — call via asyncio.to_thread."""
    import paho.mqtt.client as mqtt

    mc = mqtt.Client()
    if user:
        mc.username_pw_set(user, password)
    mc.connect(host, port)
    mc.publish(f"{topic}/data", str(areas))
    mc.publish(topic, "on")
    mc.disconnect()


async def _notify(event: AlertEvent) -> None:
    """Send optional Apprise/MQTT notifications (best-effort)."""
    if settings.notifiers:
        try:
            ap = _get_apprise()
            if ap is not None:
                body = "באזורים הבאים:\n" + "\n".join(event.areas)
                await ap.async_notify(title=event.title, body=body)
        except Exception as exc:
            log.error("Apprise notification error: %s", exc)

    if settings.mqtt_host:
        try:
            await asyncio.to_thread(
                _mqtt_publish,
                settings.mqtt_host,
                settings.mqtt_port,
                settings.mqtt_user,
                settings.mqtt_pass,
                settings.mqtt_topic,
                event.areas,
            )
        except ImportError:
            log.warning("paho-mqtt not installed; skipping MQTT")
        except Exception as exc:
            log.error("MQTT publish error: %s", exc)
