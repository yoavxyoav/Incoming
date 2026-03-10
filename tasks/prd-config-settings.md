# PRD: Centralized Configuration + Settings Popup

## Overview
All hardcoded configurables are scattered across `store.py`, `monitor.py`, and the frontend JS. This PRD centralizes them into `app/config.py`, exposes user-facing ones via a `GET /api/config` endpoint, and adds a settings popup in the dashboard where users can override values — persisted in `localStorage`.

**Architecture:** Backend is the source of truth. On load, the frontend fetches `/api/config` for defaults. Any user override is saved to `localStorage` and takes precedence. Technical/infra settings (MQTT, Apprise, poll interval) are backend-only and never shown in the UI.

**Region filter** is a frontend display concern — it filters what is shown, not what the backend processes. The backend `REGION` env var is independent.

---

## Goals
- Single place to find and change any configurable value
- No more magic constants buried in source files
- Users can tune alert behavior live from the browser without touching files
- Per-browser overrides persist across refreshes via `localStorage`
- Server restart not required for UI-facing changes

---

## Quality Gates

These commands must pass for every user story:
- `uv run pytest tests/unit/ -v` — unit tests
- `uv run mypy app/ --ignore-missing-imports` — type checking

---

## User Stories

### US-001: Centralize backend constants into config
**Description:** As a developer, I want all configurable values defined in one place so I can find and change them without hunting through source files.

**Acceptance Criteria:**
- [ ] `GROUP_WINDOW_SECONDS = 60` moved from `app/store.py` into `app/config.py` as `group_window_seconds: int = 60`
- [ ] `ALL_CLEAR_DISPLAY_MS` moved from `app/monitor.py` into `app/config.py` as `all_clear_display_seconds: int = 300`
- [ ] `MAX_GROUPS = 50` moved from `app/store.py` into `app/config.py` as `max_groups: int = 50`
- [ ] `include_test_alerts` already in config — verify it is used consistently
- [ ] All existing `.env` / pydantic-settings fields remain unchanged (no regressions)
- [ ] `app/store.py` and `app/monitor.py` import and use values from `settings` instead of local constants
- [ ] Unit tests for `AlertStore` that relied on `GROUP_WINDOW_SECONDS` import from `app.store` still pass (re-export the constant or update imports)

### US-002: Expose public config via REST endpoint
**Description:** As the frontend, I want to fetch the server's default configuration so I can use it as a baseline before applying any local overrides.

**Acceptance Criteria:**
- [ ] New endpoint `GET /api/config` exists and returns HTTP 200
- [ ] Response includes only user-facing fields (not MQTT credentials, not Apprise URLs, not internal paths):
  ```json
  {
    "region": "*",
    "include_test_alerts": false,
    "group_window_seconds": 60,
    "all_clear_display_seconds": 300,
    "max_groups": 50
  }
  ```
- [ ] Sensitive/infra fields (`mqtt_host`, `mqtt_pass`, `notifiers`, `lamas_path`, `poll_interval`, `host`, `port`) are explicitly excluded
- [ ] Endpoint is documented in `README.md` API table
- [ ] Unit test: `GET /api/config` returns the expected shape with default values

### US-003: Frontend loads config on startup
**Description:** As a user, I want the dashboard to use the server's configured defaults so behavior is consistent without me having to set anything.

**Acceptance Criteria:**
- [ ] On page load (before WS connect), frontend calls `GET /api/config` and stores result as `serverConfig`
- [ ] `group_window_seconds` and `all_clear_display_seconds` are read from config (not hardcoded in JS)
- [ ] `clear_after_ms` in `ended` WS messages is still used as the authoritative value (server already sends it); `/api/config` is the fallback for initial render
- [ ] `localStorage` is checked first; if a key exists there it overrides the server value
- [ ] A helper `getCfg(key)` returns: `localStorage.getItem('cfg_' + key) ?? serverConfig[key]`
- [ ] No visible change in behavior when no localStorage overrides are set

### US-004: Settings popup in the dashboard
**Description:** As a user, I want a settings panel in the dashboard where I can adjust alert behavior live without editing files.

**Acceptance Criteria:**
- [ ] A ⚙️ settings button is added to the header (next to existing sound/debug buttons)
- [ ] Clicking it opens a modal (same style as the existing sound modal)
- [ ] Modal contains the following fields:

  | Setting | Control | Key |
  |---|---|---|
  | Region filter | Text input (display filter only) | `region` |
  | Include test alerts | Toggle | `include_test_alerts` |
  | Group window | Number input (seconds) | `group_window_seconds` |
  | All-clear display | Number input (seconds) | `all_clear_display_seconds` |

- [ ] Each field shows the current effective value (localStorage override or server default)
- [ ] A "Reset to defaults" button per-row clears the localStorage key and reverts to server default
- [ ] Clicking Save writes changed values to `localStorage` and applies them immediately (no page reload)
- [ ] Changes to `all_clear_display_seconds` affect the next all-clear event only
- [ ] Region filter note: "Filters what is displayed — does not affect what the server processes"
- [ ] Modal is closeable via ✕ button and Escape key

### US-005: Sound defaults in unified settings popup
**Description:** As a user, I want my sound preferences to be part of the unified settings panel instead of a separate modal.

**Acceptance Criteria:**
- [ ] Sound type (siren/beep/alarm) and volume slider moved from standalone sound modal into unified settings modal
- [ ] Sound enabled toggle remains in the header (quick access)
- [ ] Standalone sound modal and its open/close functions are removed
- [ ] Sound settings saved to `localStorage` under `cfg_sound_type` and `cfg_sound_volume`
- [ ] On load, sound type and volume read via `getCfg()` with fallbacks `'siren'` and `0.7`

---

## Functional Requirements
- FR-1: `app/config.py` is the single source of truth for all default values
- FR-2: `GET /api/config` returns only non-sensitive, user-facing fields
- FR-3: Frontend `getCfg(key)` always checks `localStorage` before server default
- FR-4: Settings popup applies changes immediately without page reload
- FR-5: "Reset to defaults" removes the `localStorage` key and restores server default
- FR-6: MQTT, Apprise, poll interval, host, port, lamas settings are never exposed in the UI
- FR-7: Region filter in the popup is a display-only frontend filter, independent of the backend `REGION` setting

## Non-Goals
- Server-side config mutation (no `POST /api/config`)
- Multi-user settings sync across browsers
- Config versioning or migration
- Validating region input against known city names

## Technical Considerations
- `app/store.py` currently imports `GROUP_WINDOW_SECONDS` as a module-level constant — after moving to `settings`, `AlertStore` should read from `settings` at instantiation
- `tests/unit/test_store.py` imports `GROUP_WINDOW_SECONDS` from `app.store` — update import to `app.config` or re-export from `app.store`
- Existing sound modal HTML + JS (`openSoundModal`, `closeSoundModal`, `setSoundType`, `testSound`) to be merged into new settings modal

## Success Metrics
- Zero hardcoded magic numbers remain in `store.py` or `monitor.py`
- All unit tests pass
- Settings popup opens, saves, and resets without page reload
- Fresh browser with no localStorage gets identical behavior to current
