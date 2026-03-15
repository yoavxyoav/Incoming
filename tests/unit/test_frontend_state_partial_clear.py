"""
Tests for the partial-clear chip state reconstruction logic in the `state` WS handler.

The JS logic being tested (after activeAlerts[a.cat] = a):

    const g = groupsByCat[a.cat];
    if (g) {
      a._resolved_areas = g.resolved_areas || [];
      a._is_ended = g.resolved_areas && g.areas &&
                    g.resolved_areas.length === g.areas.length && g.areas.length > 0;
    } else {
      a._resolved_areas = [];
      a._is_ended = false;
    }
"""

from typing import Any


def apply_partial_clear_state(alert: dict[str, Any], group: dict[str, Any] | None) -> dict[str, Any]:
    """
    Mirror of the JS state reconstruction logic.

    Given an alert dict and its matching group (or None), mutates and returns
    the alert with _resolved_areas and _is_ended set.
    """
    if group is not None:
        alert["_resolved_areas"] = group.get("resolved_areas") or []
        resolved = group.get("resolved_areas") or []
        areas = group.get("areas") or []
        alert["_is_ended"] = bool(resolved and areas and len(resolved) == len(areas) and len(areas) > 0)
    else:
        alert["_resolved_areas"] = []
        alert["_is_ended"] = False
    return alert


def build_groups_by_cat(groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Mirror of: const groupsByCat = {}; for (const g of groups) groupsByCat[g.cat] = g;"""
    return {g["cat"]: g for g in groups}


# ---------------------------------------------------------------------------
# No matching group
# ---------------------------------------------------------------------------

def test_no_group_defaults_empty_resolved_not_ended():
    alert: dict[str, Any] = {"cat": "missiles", "areas": ["Tel Aviv", "Haifa"]}
    result = apply_partial_clear_state(alert, group=None)
    assert result["_resolved_areas"] == []
    assert result["_is_ended"] is False


def test_no_group_in_groups_list():
    alert: dict[str, Any] = {"cat": "missiles"}
    groups_by_cat = build_groups_by_cat([{"cat": "drones", "areas": ["X"], "resolved_areas": ["X"]}])
    group = groups_by_cat.get(alert["cat"])
    result = apply_partial_clear_state(alert, group)
    assert result["_resolved_areas"] == []
    assert result["_is_ended"] is False


# ---------------------------------------------------------------------------
# Group exists, no areas resolved yet
# ---------------------------------------------------------------------------

def test_group_with_no_resolved_areas():
    alert: dict[str, Any] = {"cat": "missiles"}
    group = {"cat": "missiles", "areas": ["Tel Aviv", "Haifa"], "resolved_areas": []}
    result = apply_partial_clear_state(alert, group)
    assert result["_resolved_areas"] == []
    assert result["_is_ended"] is False


def test_group_with_null_resolved_areas():
    """resolved_areas may be None/missing from older server payloads."""
    alert: dict[str, Any] = {"cat": "missiles"}
    group = {"cat": "missiles", "areas": ["Tel Aviv"], "resolved_areas": None}
    result = apply_partial_clear_state(alert, group)
    assert result["_resolved_areas"] == []
    assert result["_is_ended"] is False


# ---------------------------------------------------------------------------
# Partial clear (some areas resolved)
# ---------------------------------------------------------------------------

def test_partial_clear_sets_resolved_areas_not_ended():
    alert: dict[str, Any] = {"cat": "missiles"}
    group = {
        "cat": "missiles",
        "areas": ["Tel Aviv", "Haifa", "Petah Tikva"],
        "resolved_areas": ["Haifa"],
    }
    result = apply_partial_clear_state(alert, group)
    assert result["_resolved_areas"] == ["Haifa"]
    assert result["_is_ended"] is False


def test_partial_clear_multiple_resolved_not_ended():
    alert: dict[str, Any] = {"cat": "missiles"}
    group = {
        "cat": "missiles",
        "areas": ["A", "B", "C"],
        "resolved_areas": ["A", "B"],
    }
    result = apply_partial_clear_state(alert, group)
    assert result["_resolved_areas"] == ["A", "B"]
    assert result["_is_ended"] is False


# ---------------------------------------------------------------------------
# Full clear (all areas resolved)
# ---------------------------------------------------------------------------

def test_full_clear_sets_is_ended_true():
    alert: dict[str, Any] = {"cat": "missiles"}
    group = {
        "cat": "missiles",
        "areas": ["Tel Aviv", "Haifa"],
        "resolved_areas": ["Tel Aviv", "Haifa"],
    }
    result = apply_partial_clear_state(alert, group)
    assert set(result["_resolved_areas"]) == {"Tel Aviv", "Haifa"}
    assert result["_is_ended"] is True


def test_single_area_fully_resolved():
    alert: dict[str, Any] = {"cat": "drones"}
    group = {
        "cat": "drones",
        "areas": ["Eilat"],
        "resolved_areas": ["Eilat"],
    }
    result = apply_partial_clear_state(alert, group)
    assert result["_resolved_areas"] == ["Eilat"]
    assert result["_is_ended"] is True


# ---------------------------------------------------------------------------
# Edge: empty areas list (guard against divide-by-zero / vacuous true)
# ---------------------------------------------------------------------------

def test_group_with_empty_areas_list_not_ended():
    """If areas is empty, is_ended must be False even if resolved_areas is also empty."""
    alert: dict[str, Any] = {"cat": "missiles"}
    group = {"cat": "missiles", "areas": [], "resolved_areas": []}
    result = apply_partial_clear_state(alert, group)
    assert result["_is_ended"] is False


# ---------------------------------------------------------------------------
# Multiple cats in groups payload
# ---------------------------------------------------------------------------

def test_correct_group_selected_by_cat():
    alert_missiles: dict[str, Any] = {"cat": "missiles"}
    alert_drones: dict[str, Any] = {"cat": "drones"}
    groups = [
        {"cat": "missiles", "areas": ["A", "B"], "resolved_areas": ["A"]},
        {"cat": "drones",   "areas": ["X"],       "resolved_areas": ["X"]},
    ]
    groups_by_cat = build_groups_by_cat(groups)

    result_m = apply_partial_clear_state(alert_missiles, groups_by_cat.get("missiles"))
    assert result_m["_resolved_areas"] == ["A"]
    assert result_m["_is_ended"] is False

    result_d = apply_partial_clear_state(alert_drones, groups_by_cat.get("drones"))
    assert result_d["_resolved_areas"] == ["X"]
    assert result_d["_is_ended"] is True


# ---------------------------------------------------------------------------
# groupsByCat index helper
# ---------------------------------------------------------------------------

def test_build_groups_by_cat_indexes_correctly():
    groups = [
        {"cat": "missiles", "areas": [], "resolved_areas": []},
        {"cat": "drones",   "areas": [], "resolved_areas": []},
    ]
    idx = build_groups_by_cat(groups)
    assert "missiles" in idx
    assert "drones" in idx
    assert idx["missiles"]["cat"] == "missiles"


def test_build_groups_by_cat_empty_list():
    assert build_groups_by_cat([]) == {}
