import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app import geo
from app.config import settings
from app.logger import log
from app.models import OrefAlertRaw, StatusResponse
from app.monitor import OREF_HEADERS, OREF_URL, _build_event, poll_loop
from app.store import manager, store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await geo.load(settings.lamas_path, settings.lamas_url)
    task = asyncio.create_task(poll_loop(store, manager))
    log.info("Oref monitor started")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    log.info("Oref monitor stopped")


app = FastAPI(title="Incoming", lifespan=lifespan)

# Serve frontend
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(str(_frontend / "index.html"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return StatusResponse(
        current=store.current,
        groups=store.groups,
        connected_clients=manager.count,
    )


@app.get("/api/config")
async def public_config() -> dict[str, object]:
    """User-facing configuration defaults. Sensitive/infra fields are excluded."""
    return {
        "region": settings.region,
        "include_test_alerts": settings.include_test_alerts,
        "group_window_seconds": settings.group_window_seconds,
        "all_clear_display_seconds": settings.all_clear_display_seconds,
        "max_groups": settings.max_groups,
    }


@app.get("/api/history")
async def history() -> dict[str, object]:
    return {"groups": [g.model_dump(mode="json") for g in store.groups]}


@app.get("/api/raw")
async def raw_alert() -> dict[str, object]:
    """Fetch and return the live Oref JSON exactly as received — for the debug panel."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(OREF_URL, headers=OREF_HEADERS, timeout=5.0)
            text = resp.text.replace("\x00", "").strip()
            parsed: object = None
            if text:
                try:
                    parsed = resp.json()
                except Exception:
                    parsed = None
            return {
                "status_code": resp.status_code,
                "url": OREF_URL,
                "raw": text or "(empty — no active alert)",
                "parsed": parsed,
            }
    except Exception as exc:
        return {"error": str(exc)}


_LOCALHOST = {"127.0.0.1", "::1", "localhost"}


def _require_localhost(request: Request) -> None:
    host = (request.client.host if request.client else "")
    if host not in _LOCALHOST:
        raise HTTPException(status_code=403, detail="simulation only available from localhost")


_SIM_CATS = {
    "1":  ("ירי רקטות וטילים",   "היכנסו למרחב המוגן"),
    "2":  ("חדירת כטב\"מ",        "היכנסו למרחב המוגן"),
    "10": ("חדירת מחבלים",        "היכנסו למרחב המוגן ונעלו את הדלת"),
}
_SIM_AREAS = ["תל אביב - מרכז העיר", "רמת גן", "גבעתיים", "בני ברק", "פתח תקווה"]


@app.post("/api/sim/alert")
async def sim_alert(request: Request, cat: str = "1") -> dict[str, object]:
    """Inject a simulated alert."""
    _require_localhost(request)
    if cat not in _SIM_CATS:
        raise HTTPException(status_code=400, detail=f"unknown cat; choose from {list(_SIM_CATS)}")
    title, desc = _SIM_CATS[cat]
    raw = OrefAlertRaw(
        id=f"sim_{cat}_{int(time.time())}",
        cat=cat,
        title=title,
        desc=desc,
        data=_SIM_AREAS,
    )
    event = _build_event(raw)
    store.set_alert(event)
    await manager.broadcast({"type": "alert", "payload": event.model_dump(mode="json")})
    await manager.broadcast({"type": "groups", "payload": [g.model_dump(mode="json") for g in store.groups]})
    log.info("Simulated alert injected cat=%s", cat)
    return {"status": "ok", "cat": cat, "title": title}


@app.post("/api/sim/all-clear")
async def sim_all_clear(request: Request, cat: str = "1") -> dict[str, object]:
    """Inject a simulated all-clear for a given cat."""
    _require_localhost(request)
    active = store.get_active_by_cat(cat)
    areas = active.areas if active else _SIM_AREAS
    raw = OrefAlertRaw(
        id=f"sim_clear_{cat}_{int(time.time())}",
        cat=cat,
        title="ניתן לצאת מהמרחב המוגן",
        desc="האירוע הסתיים באזורכם",
        data=areas,
    )
    event = _build_event(raw)
    store.set_alert(event, is_ended=True)
    store.clear(cat=cat)
    store.resolve_areas(event.cat, event.areas, event.received_at)
    payload = {**event.model_dump(mode="json"), "clear_after_ms": settings.all_clear_display_seconds * 1000}
    await manager.broadcast({"type": "ended", "payload": payload})
    await manager.broadcast({"type": "groups", "payload": [g.model_dump(mode="json") for g in store.groups]})
    log.info("Simulated all-clear injected cat=%s", cat)
    return {"status": "ok", "cat": cat}


@app.post("/api/sim/partial-clear")
async def sim_partial_clear(request: Request, cat: str = "1", n: int = 2) -> dict[str, object]:
    """Inject a simulated partial all-clear (first n areas only) — card stays red, chips split."""
    _require_localhost(request)
    active = store.get_active_by_cat(cat)
    all_areas = active.areas if active else _SIM_AREAS
    areas = all_areas[:n]
    raw = OrefAlertRaw(
        id=f"sim_partial_{cat}_{int(time.time())}",
        cat=cat,
        title="ניתן לצאת מהמרחב המוגן",
        desc="האירוע הסתיים באזורכם",
        data=areas,
    )
    event = _build_event(raw)
    # Only resolve these areas — do NOT clear the active alert from store
    store.resolve_areas(event.cat, event.areas, event.received_at)
    payload = {**event.model_dump(mode="json"), "clear_after_ms": settings.all_clear_display_seconds * 1000}
    await manager.broadcast({"type": "ended", "payload": payload})
    await manager.broadcast({"type": "groups", "payload": [g.model_dump(mode="json") for g in store.groups]})
    log.info("Simulated partial all-clear injected cat=%s areas=%d", cat, len(areas))
    return {"status": "ok", "cat": cat, "cleared_areas": areas}


@app.post("/api/history/clear")
async def clear_history(request: Request) -> dict[str, object]:
    """Clear the alert history groups (localhost only)."""
    _require_localhost(request)
    store.clear_groups()
    await manager.broadcast({"type": "groups", "payload": []})
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    # Send current state immediately on connect
    state: dict[str, object] = {
        "type": "state",
        "payload": {
            "current": [a.model_dump(mode="json") for a in store.current],
            "groups": [g.model_dump(mode="json") for g in store.groups],
        },
    }
    try:
        await ws.send_json(state)
        while True:
            # Keep alive — browser pings; we just wait for disconnect
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
