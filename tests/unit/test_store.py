from datetime import datetime, timedelta, timezone

import pytest

from app.models import AlertEvent
from app.store import AlertStore, GROUP_WINDOW_SECONDS


def make_alert(
    alert_id: str = "abc123",
    cat: str = "1",
    areas: list[str] | None = None,
    received_at: datetime | None = None,
) -> AlertEvent:
    areas = areas or ["תל אביב", "חולון"]
    return AlertEvent(
        id=alert_id,
        cat=cat,
        cat_label="Missiles / Rockets",
        title="ירי רקטות וטילים",
        desc="היכנסו למרחב המוגן",
        areas=areas,
        categorized_areas={"מרכז": areas},
        received_at=received_at or datetime.now(timezone.utc),
    )


def test_initial_state() -> None:
    s = AlertStore()
    assert s.current == []
    assert s.history == []


def test_set_and_get_alert() -> None:
    s = AlertStore()
    alert = make_alert("id1")
    s.set_alert(alert)
    assert len(s.current) == 1
    assert s.current[0].id == "id1"
    assert len(s.history) == 1


def test_is_new() -> None:
    s = AlertStore()
    assert s.is_new("id1") is True
    s.set_alert(make_alert("id1"))
    assert s.is_new("id1") is False
    assert s.is_new("id2") is True


def test_clear_with_active_alert() -> None:
    s = AlertStore()
    s.set_alert(make_alert("id1"))
    cleared = s.clear()
    assert cleared is True
    assert s.current == []


def test_clear_with_no_alert() -> None:
    s = AlertStore()
    cleared = s.clear()
    assert cleared is False


def test_history_respects_max() -> None:
    s = AlertStore(max_history=3)
    for i in range(5):
        s.set_alert(make_alert(f"id{i}"))
    assert len(s.history) == 3


def test_history_most_recent_first() -> None:
    s = AlertStore()
    s.set_alert(make_alert("first"))
    s.set_alert(make_alert("second"))
    assert s.history[0].id == "second"
    assert s.history[1].id == "first"


def test_clear_does_not_remove_history() -> None:
    s = AlertStore()
    s.set_alert(make_alert("id1"))
    s.clear()
    assert len(s.history) == 1


# ── Group tests ───────────────────────────────────────────────────────────────

def test_group_created_on_first_alert() -> None:
    s = AlertStore()
    s.set_alert(make_alert("id1"))
    assert len(s.groups) == 1
    assert s.groups[0].cat == "1"


def test_alerts_merged_within_window() -> None:
    s = AlertStore()
    t = datetime.now(timezone.utc)
    s.set_alert(make_alert("id1", areas=["תל אביב"], received_at=t))
    s.set_alert(make_alert("id2", areas=["חולון"], received_at=t + timedelta(seconds=10)))
    assert len(s.groups) == 1
    assert "תל אביב" in s.groups[0].areas
    assert "חולון" in s.groups[0].areas


def test_alerts_split_outside_window() -> None:
    s = AlertStore()
    t = datetime.now(timezone.utc)
    s.set_alert(make_alert("id1", received_at=t))
    s.set_alert(make_alert("id2", received_at=t + timedelta(seconds=GROUP_WINDOW_SECONDS + 1)))
    assert len(s.groups) == 2


def test_different_cat_creates_new_group() -> None:
    s = AlertStore()
    t = datetime.now(timezone.utc)
    s.set_alert(make_alert("id1", cat="1", received_at=t))
    s.set_alert(make_alert("id2", cat="2", received_at=t + timedelta(seconds=1)))
    assert len(s.groups) == 2


def test_group_time_range_updates() -> None:
    s = AlertStore()
    t = datetime.now(timezone.utc)
    s.set_alert(make_alert("id1", received_at=t))
    s.set_alert(make_alert("id2", received_at=t + timedelta(seconds=10)))
    g = s.groups[0]
    assert g.from_time == t
    assert (g.to_time - t).seconds == 10


def test_ended_group_not_merged() -> None:
    s = AlertStore()
    t = datetime.now(timezone.utc)
    s.set_alert(make_alert("id1", received_at=t), is_ended=True)
    s.set_alert(make_alert("id2", received_at=t + timedelta(seconds=1)))
    assert len(s.groups) == 2
    assert s.groups[1].is_ended is True
