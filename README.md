# Oref Alert Monitor

Real-time Israeli civil defense alert monitor with a live web dashboard.

Polls the [Pikud HaOref](https://www.oref.org.il) API every second and pushes alerts instantly to all connected browsers via WebSocket.

## Features

- **Live dashboard** — dark UI, real-time alerts, geographic area breakdown, session history
- **WebSocket push** — zero-latency browser updates, auto-reconnect
- **Geo categorization** — cities grouped by region (powered by lamas.json)
- **Alert deduplication** — each alert fires exactly once per session
- **REST API** — `/api/status`, `/api/history`, `/health`
- **Optional MQTT** — publish to Home Assistant or any MQTT broker
- **Optional notifications** — Apprise (Telegram, Slack, etc.)
- **Region filter** — monitor one city or all (`REGION=*`)
- **Docker-ready**

## Quick Start

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000

## Docker

```bash
docker compose up --build
```

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `REGION` | `*` | City name to filter, or `*` for all |
| `INCLUDE_TEST_ALERTS` | `false` | Include drill alerts |
| `POLL_INTERVAL` | `1.0` | Seconds between API checks |
| `MQTT_HOST` | _(empty)_ | MQTT broker host (disabled if empty) |
| `MQTT_PORT` | `1883` | MQTT port |
| `NOTIFIERS` | _(empty)_ | Space-separated Apprise URLs |
| `PORT` | `8000` | HTTP server port |

## API

| Endpoint | Description |
|---|---|
| `GET /` | Web dashboard |
| `GET /health` | `{"status":"ok"}` |
| `GET /api/status` | Current alert + history + client count |
| `GET /api/history` | Recent alert history |
| `WS /ws` | Real-time WebSocket stream |

## WebSocket Messages

```json
// On connect: current state
{"type": "state", "payload": {"current": {...} | null, "history": [...]}}

// New alert
{"type": "alert", "payload": {"id": "...", "title": "...", "areas": [...], ...}}

// Alert cleared
{"type": "clear", "payload": null}
```

## Home Assistant MQTT

```yaml
sensor:
  - platform: mqtt
    name: "Red Alert"
    state_topic: "/redalert"
  - platform: mqtt
    name: "Red Alert Areas"
    state_topic: "/redalert/data"
```

## Tests

```bash
uv run pytest tests/unit/ -v           # unit tests
uv run pytest tests/integration/ -v   # hits real Oref API
```
