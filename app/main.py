import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app import geo
from app.config import settings
from app.logger import log
from app.models import StatusResponse
from app.monitor import OREF_HEADERS, OREF_URL, poll_loop
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
        history=store.history,
        connected_clients=manager.count,
    )


@app.get("/api/history")
async def history() -> dict[str, object]:
    return {"alerts": [a.model_dump(mode="json") for a in store.history]}


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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    # Send current state immediately on connect
    state: dict[str, object] = {
        "type": "state",
        "payload": {
            "current": store.current.model_dump(mode="json") if store.current else None,
            "history": [a.model_dump(mode="json") for a in store.history],
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
