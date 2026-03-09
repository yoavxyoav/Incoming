import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

from app import geo
from app.config import settings
from app.logger import log
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
    return "בדיקה" in alert.data or alert.cat in ("101", "102", "103")


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

    async with httpx.AsyncClient() as client:
        while True:
            try:
                raw = await _fetch_alert(client)

                if raw and not _is_test(raw) and _filter_region(raw):
                    if store.is_new(raw.id):
                        event = _build_event(raw)
                        if _is_all_clear(raw):
                            # "האירוע הסתיים" — record in history but clear the active alert
                            store.set_alert(event)
                            store.clear()
                            payload = event.model_dump(mode="json")
                            await manager.broadcast({"type": "ended", "payload": payload})
                        else:
                            store.set_alert(event)
                            payload = event.model_dump(mode="json")
                            await manager.broadcast({"type": "alert", "payload": payload})
                            await _notify(event)
                else:
                    if store.clear():
                        await manager.broadcast({"type": "clear", "payload": None})

            except Exception as exc:
                log.error("Unhandled monitor error: %s", exc)

            # Heartbeat — lets the frontend blink its LED every poll
            await manager.broadcast({"type": "tick", "payload": None})

            await asyncio.sleep(settings.poll_interval)


async def _notify(event: AlertEvent) -> None:
    """Send optional Apprise/MQTT notifications (best-effort)."""
    if settings.notifiers:
        try:
            import apprise  # type: ignore[import-untyped]

            ap = apprise.Apprise()
            for url in settings.notifiers.split():
                ap.add(url)
            body = "באזורים הבאים:\n" + "\n".join(event.areas)
            await ap.async_notify(title=event.title, body=body)
        except ImportError:
            log.warning("apprise not installed; skipping notifications")
        except Exception as exc:
            log.error("Apprise notification error: %s", exc)

    if settings.mqtt_host:
        try:
            import paho.mqtt.client as mqtt  # type: ignore[import-untyped]

            topic = settings.mqtt_topic
            mc = mqtt.Client()
            if settings.mqtt_user:
                mc.username_pw_set(settings.mqtt_user, settings.mqtt_pass)
            mc.connect(settings.mqtt_host, settings.mqtt_port)
            mc.publish(f"{topic}/data", str(event.areas))
            mc.publish(topic, "on")
            mc.disconnect()
        except ImportError:
            log.warning("paho-mqtt not installed; skipping MQTT")
        except Exception as exc:
            log.error("MQTT publish error: %s", exc)
