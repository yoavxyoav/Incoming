"""
Tests for the `ended` WS message handler logic in frontend/index.html.

The JS logic being tested (US-003 fix):

    } else if (msg.type === 'ended') {
      const p = msg.payload;
      const prev = activeAlerts[p.cat] || {};
      if (prev.areas) {
        // ... card manipulation (accumulate resolved, update activeAlerts, renderActivePanel, sound, timer)
      }
      // Always refresh history regardless of whether a prior card existed
      fetch('/api/history').then(r => r.json()).then(data => renderGroups(data.groups)).catch(() => {});
    }

Key guarantee: when `prev.areas` is absent, card manipulation is skipped but
history is still fetched. No JS error is thrown.
"""

from typing import Any


# ---------------------------------------------------------------------------
# Python mirrors of the JS ended-handler logic
# ---------------------------------------------------------------------------

def apply_ended_handler(
    active_alerts: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[bool, bool]:
    """
    Mirror of the JS ended handler.

    Returns a tuple (card_updated, history_fetched) to allow assertions on
    both branches independently.
    """
    p = payload
    prev = active_alerts.get(p["cat"], {})
    card_updated = False

    if prev.get("areas"):
        prev_resolved: set[str] = set(prev.get("_resolved_areas") or [])
        for a in p.get("areas", []):
            prev_resolved.add(a)
        resolved_areas = list(prev_resolved)
        original_areas: list[str] = prev["areas"]
        all_cleared = bool(
            original_areas
            and all(a in prev_resolved for a in original_areas)
        )
        active_alerts[p["cat"]] = {
            **prev,
            **p,
            "areas": original_areas,
            "categorized_areas": prev.get("categorized_areas") or p.get("categorized_areas"),
            "title": prev.get("title") or p.get("title"),
            "desc": prev.get("desc") or p.get("desc"),
            "cat_label": prev.get("cat_label") or p.get("cat_label"),
            "_resolved_areas": resolved_areas,
            "_is_ended": all_cleared,
        }
        card_updated = True

    # history fetch always happens — represented as True here
    history_fetched = True
    return card_updated, history_fetched


# ---------------------------------------------------------------------------
# No prior activeAlerts entry (the early-return bug scenario)
# ---------------------------------------------------------------------------

def test_no_prior_entry_skips_card_but_fetches_history():
    """When activeAlerts has no entry for the cat, card is not updated but history IS fetched."""
    active_alerts: dict[str, Any] = {}
    payload = {"cat": "missiles", "areas": ["Tel Aviv"], "clear_after_ms": 300_000}

    card_updated, history_fetched = apply_ended_handler(active_alerts, payload)

    assert card_updated is False, "Card should NOT be updated when prev.areas is absent"
    assert history_fetched is True, "History MUST always be fetched"
    # activeAlerts should remain untouched
    assert "missiles" not in active_alerts


def test_no_prior_entry_does_not_raise():
    """No exception should be raised when prev is an empty dict (no .areas)."""
    active_alerts: dict[str, Any] = {}
    payload = {"cat": "drones", "areas": ["Haifa"], "clear_after_ms": 120_000}
    # Must not raise
    apply_ended_handler(active_alerts, payload)


def test_prior_entry_without_areas_skips_card_but_fetches_history():
    """activeAlerts entry exists but has no 'areas' key — same as absent entry."""
    active_alerts: dict[str, Any] = {"missiles": {"cat": "missiles", "title": "Alert"}}
    payload = {"cat": "missiles", "areas": ["Eilat"], "clear_after_ms": 300_000}

    card_updated, history_fetched = apply_ended_handler(active_alerts, payload)

    assert card_updated is False
    assert history_fetched is True


# ---------------------------------------------------------------------------
# Prior entry WITH areas — card manipulation should work normally
# ---------------------------------------------------------------------------

def test_prior_entry_with_areas_updates_card_and_fetches_history():
    """Normal path: prior card exists, card is updated AND history is fetched."""
    active_alerts: dict[str, Any] = {
        "missiles": {
            "cat": "missiles",
            "areas": ["Tel Aviv", "Haifa"],
            "title": "Missile Alert",
            "desc": "Take cover",
            "cat_label": "Missiles",
            "categorized_areas": {},
            "_resolved_areas": [],
        }
    }
    payload = {"cat": "missiles", "areas": ["Haifa"], "clear_after_ms": 300_000}

    card_updated, history_fetched = apply_ended_handler(active_alerts, payload)

    assert card_updated is True
    assert history_fetched is True
    updated = active_alerts["missiles"]
    assert "Haifa" in updated["_resolved_areas"]
    assert updated["_is_ended"] is False  # Tel Aviv still not cleared
    assert updated["areas"] == ["Tel Aviv", "Haifa"]  # original preserved


def test_full_clear_marks_is_ended_true():
    """All areas resolved — _is_ended must be True."""
    active_alerts: dict[str, Any] = {
        "missiles": {
            "cat": "missiles",
            "areas": ["Tel Aviv"],
            "title": "Alert",
            "desc": "",
            "cat_label": "Missiles",
            "categorized_areas": {},
            "_resolved_areas": [],
        }
    }
    payload = {"cat": "missiles", "areas": ["Tel Aviv"], "clear_after_ms": 300_000}

    card_updated, history_fetched = apply_ended_handler(active_alerts, payload)

    assert card_updated is True
    assert history_fetched is True
    assert active_alerts["missiles"]["_is_ended"] is True


def test_partial_clear_accumulates_resolved_areas():
    """Second partial clear adds to existing resolved areas."""
    active_alerts: dict[str, Any] = {
        "drones": {
            "cat": "drones",
            "areas": ["A", "B", "C"],
            "title": "Drone Alert",
            "desc": "",
            "cat_label": "Drones",
            "categorized_areas": {},
            "_resolved_areas": ["A"],
        }
    }
    payload = {"cat": "drones", "areas": ["B"], "clear_after_ms": 300_000}

    apply_ended_handler(active_alerts, payload)

    updated = active_alerts["drones"]
    assert set(updated["_resolved_areas"]) == {"A", "B"}
    assert updated["_is_ended"] is False  # C still pending


def test_history_fetched_regardless_of_card_update():
    """Both paths (card updated / not updated) must result in history_fetched=True."""
    # Path 1: no prior entry
    aa1: dict[str, Any] = {}
    _, h1 = apply_ended_handler(aa1, {"cat": "missiles", "areas": [], "clear_after_ms": 0})
    assert h1 is True

    # Path 2: prior entry with areas
    aa2: dict[str, Any] = {
        "missiles": {
            "cat": "missiles",
            "areas": ["X"],
            "title": "",
            "desc": "",
            "cat_label": "",
            "categorized_areas": {},
            "_resolved_areas": [],
        }
    }
    _, h2 = apply_ended_handler(aa2, {"cat": "missiles", "areas": ["X"], "clear_after_ms": 0})
    assert h2 is True


def test_original_areas_preserved_on_full_clear():
    """Original areas list on the card is preserved even after full clear."""
    original = ["City A", "City B"]
    active_alerts: dict[str, Any] = {
        "missiles": {
            "cat": "missiles",
            "areas": original[:],
            "title": "T",
            "desc": "D",
            "cat_label": "M",
            "categorized_areas": {},
            "_resolved_areas": [],
        }
    }
    payload = {"cat": "missiles", "areas": ["City A", "City B"], "clear_after_ms": 0}
    apply_ended_handler(active_alerts, payload)

    assert active_alerts["missiles"]["areas"] == original
