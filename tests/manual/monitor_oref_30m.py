"""
Monitor Oref API for 30 minutes, logging every unique response to understand
whether all events receive an explicit all-clear or if some end silently.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

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

ALL_CLEAR_TITLES = frozenset([
    "האירוע הסתיים",
    "הסתיים",
    "ניתן לצאת מהמרחב המוגן",
    "ניתן לחזור לשגרה",
    "ניתן לצאת",
    "כל הכוחות בשטח",
])

LOG_FILE = Path("logs/oref_monitor.log")
LOG_FILE.parent.mkdir(exist_ok=True)

def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def classify(data: dict | None) -> str:
    if data is None:
        return "EMPTY"
    title = data.get("title", "").strip()
    if title in ALL_CLEAR_TITLES:
        return "ALL_CLEAR"
    return "ALERT"


async def main() -> None:
    duration = 6 * 60 * 60  # 6 hours
    start = time.monotonic()
    poll_interval = 1.0

    last_id: str | None = None
    last_kind: str = "EMPTY"
    seen_events: list[dict] = []  # (time, kind, id, title, areas_count)

    # Track all cats seen as active in the current attack window
    # Maps cat → set of area names seen active for that cat
    active_cats: dict[str, set[str]] = {}

    print(f"[{ts()}] Starting 30-minute Oref monitor. Log: {LOG_FILE}")

    with LOG_FILE.open("w") as log:
        def write(msg: str) -> None:
            line = f"[{ts()}] {msg}"
            print(line)
            log.write(line + "\n")
            log.flush()

        write("=== Oref 30-minute monitor started ===")

        async with httpx.AsyncClient() as client:
            while time.monotonic() - start < duration:
                try:
                    resp = await client.get(OREF_URL, headers=OREF_HEADERS, timeout=5.0)
                    text = resp.text.replace("\x00", "").strip()

                    if not text or text.isspace():
                        data = None
                    else:
                        try:
                            data = resp.json()
                            if not data or not data.get("id"):
                                data = None
                        except Exception:
                            data = None

                    kind = classify(data)
                    alert_id = data.get("id") if data else None

                    # Only log on transitions or new IDs
                    if kind != last_kind or (alert_id and alert_id != last_id):
                        if kind == "EMPTY" and last_kind != "EMPTY":
                            write(
                                f"TRANSITION: {last_kind} → EMPTY "
                                f"(last id={last_id}) — "
                                f"NOTE: Oref went quiet WITHOUT explicit all-clear!"
                            )
                        elif kind == "ALL_CLEAR":
                            clear_areas = data.get("data", []) if data else []
                            write(
                                f"ALL_CLEAR — cat={data.get('cat')!r} "  # type: ignore[union-attr]
                                f"title={data.get('title')!r} "  # type: ignore[union-attr]
                                f"areas({len(clear_areas)})={clear_areas}"
                            )
                            write(
                                f"  Cats active at all-clear time: "
                                + (", ".join(f"cat={c} ({len(a)} areas)" for c, a in sorted(active_cats.items()))
                                   or "(none tracked)")
                            )
                            # Did the all-clear areas overlap with each active cat's areas?
                            clear_set = set(clear_areas)
                            for acat, aareas in sorted(active_cats.items()):
                                overlap = clear_set & aareas
                                write(
                                    f"  → cat={acat}: {len(overlap)}/{len(aareas)} active areas appear in all-clear"
                                    + (" ✓ FULL MATCH" if overlap == aareas else
                                       f" (partial: {sorted(overlap)})" if overlap else " ✗ NO OVERLAP")
                                )
                            active_cats.clear()  # reset after all-clear

                        elif kind == "ALERT":
                            title = data.get("title", "?")  # type: ignore[union-attr]
                            cat = data.get("cat", "?")  # type: ignore[union-attr]
                            areas = data.get("data", [])  # type: ignore[union-attr]
                            # Accumulate into active_cats
                            if cat not in active_cats:
                                active_cats[cat] = set()
                            active_cats[cat].update(areas)
                            write(
                                f"ALERT: cat={cat} title={title!r} areas={len(areas)} "
                                f"{'(NEW)' if alert_id != last_id else '(same id)'} "
                                f"| active cats now: {sorted(active_cats.keys())}"
                            )
                            seen_events.append({
                                "id": alert_id,
                                "title": title,
                                "cat": cat,
                                "areas": len(areas),
                                "time": ts(),
                                "got_all_clear": False,
                            })

                        if kind == "ALL_CLEAR" and seen_events:
                            # Mark most recent event as cleared
                            seen_events[-1]["got_all_clear"] = True

                        last_kind = kind
                        last_id = alert_id

                except Exception as exc:
                    write(f"FETCH ERROR: {exc}")

                await asyncio.sleep(poll_interval)

        elapsed = int(time.monotonic() - start)
        write(f"\n=== Summary after {elapsed}s ===")
        write(f"Total distinct events seen: {len(seen_events)}")
        for e in seen_events:
            cleared = "✓ got all-clear" if e["got_all_clear"] else "✗ NO all-clear — ended silently"
            write(f"  cat={e['cat']} id={e['id']} areas={e['areas']} → {cleared}")

        if seen_events:
            silent = [e for e in seen_events if not e["got_all_clear"]]
            write(
                f"\nConclusion: {len(silent)}/{len(seen_events)} events ended WITHOUT an explicit all-clear."
            )
            if silent:
                write("⚠ Some events go quiet without all-clear — auto-dismiss logic IS needed.")
            else:
                write("✓ All observed events received an explicit all-clear.")
        else:
            write("No alerts observed during this window.")


if __name__ == "__main__":
    asyncio.run(main())
