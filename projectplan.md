# Oref Alert Monitor — Project Plan

_Last updated: 2026-03-09_

## Goal
Build a better version of [Redalert](https://github.com/t0mer/Redalert/) — a real-time Israeli civil defense alert monitor — with a live web dashboard, proper async architecture, and optional MQTT/notification support.

## Improvements over Original
| Original | Ours |
|---|---|
| Threading-based polling | async/await (asyncio) |
| MQTT required to run | MQTT fully optional |
| No web interface | Live WebSocket dashboard |
| Growing `alerts` list (memory leak) | Bounded deque + seen-id set |
| No REST API | `/api/status`, `/api/history`, `/health` |
| No type hints | Full type hints + mypy |
| loguru | Structured JSON logger (stdlib) |
| Single monolithic script | Modular package (`app/`) |

## Architecture

```
frontend/index.html  (WebSocket client)
        ↕ WS /ws
app/main.py          (FastAPI)
        ↕ shared store
app/monitor.py       (async polling loop, 1s interval)
        → httpx → oref.org.il/WarningMessages/alert/alerts.json
        → geo.py   (lamas.json city→area lookup)
        → optional: MQTT publish, Apprise notify
app/store.py         (AlertStore + ConnectionManager)
app/models.py        (pydantic models)
app/config.py        (pydantic-settings, .env)
app/logger.py        (JSON structured logger → logs/oref.log)
```

## Todo List

- [x] Project structure + pyproject.toml
- [x] pydantic-settings config (`.env` support)
- [x] Structured JSON logger (`logs/oref.log`)
- [x] `geo.py` — lamas.json loader + city→area categorization
- [x] `store.py` — AlertStore + WebSocket ConnectionManager
- [x] `monitor.py` — async Oref API polling loop
- [x] `main.py` — FastAPI app with `/ws`, `/api/status`, `/api/history`, `/health`
- [x] `frontend/index.html` — live dark dashboard (Tailwind, vanilla JS)
- [x] Unit tests — geo, store, monitor (22/22 passing)
- [x] Integration test — real Oref API
- [x] Dockerfile + docker-compose.yaml
- [x] `.env.example` + `.gitignore`
- [ ] `README.md`
- [ ] `FOR_YOAV.md`
- [ ] mypy static type check pass
- [ ] Smoke test: `uv run uvicorn app.main:app`

## Key Files
| File | Purpose |
|---|---|
| `app/main.py` | FastAPI entry point, WebSocket endpoint |
| `app/monitor.py` | Background polling, alert dedup, notifications |
| `app/store.py` | In-memory state, WS broadcast |
| `app/geo.py` | lamas.json → city-to-area mapping |
| `app/models.py` | OrefAlertRaw, AlertEvent, WsMessage |
| `app/config.py` | All env-var settings |
| `frontend/index.html` | Single-file dashboard |
| `data/lamas.json` | Auto-downloaded on first run |

## Data Sources
- **Active alerts**: `https://www.oref.org.il/WarningMessages/alert/alerts.json`
- **Headers required**: `Referer`, `User-Agent`, `X-Requested-With: XMLHttpRequest`
- **Response when quiet**: empty string `""` or `{}`
- **Response when alert**: `{"id":"...","cat":"1","title":"...","data":[...],"desc":"..."}`
- **lamas.json**: area→cities mapping, auto-downloaded from Redalert GitHub

## Alert Categories
| cat | Meaning |
|---|---|
| 1 | Missiles / Rockets |
| 2 | UAV |
| 3 | Earthquake |
| 4 | Tsunami |
| 101-103 | Drills (filtered by default) |

## Running Locally
```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload
# open http://localhost:8000
```

## Running with Docker
```bash
docker compose up --build
```

## Review
_2026-03-09_ — Initial implementation complete. 22/22 unit tests passing. Architecture is clean, async, and modular. MQTT and Apprise are optional extras that load lazily. The frontend uses vanilla JS with Tailwind CDN — no build step needed.
