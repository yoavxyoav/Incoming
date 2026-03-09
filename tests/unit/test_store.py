from datetime import datetime, timezone

import pytest

from app.models import AlertEvent
from app.store import AlertStore


def make_alert(alert_id: str = "abc123") -> AlertEvent:
    return AlertEvent(
        id=alert_id,
        cat="1",
        cat_label="Missiles / Rockets",
        title="ירי רקטות וטילים",
        desc="היכנסו למרחב המוגן",
        areas=["תל אביב", "חולון"],
        categorized_areas={"מרכז": ["תל אביב", "חולון"]},
        received_at=datetime.now(timezone.utc),
    )


def test_initial_state() -> None:
    s = AlertStore()
    assert s.current is None
    assert s.history == []


def test_set_and_get_alert() -> None:
    s = AlertStore()
    alert = make_alert("id1")
    s.set_alert(alert)
    assert s.current is not None
    assert s.current.id == "id1"
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
    assert s.current is None


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
