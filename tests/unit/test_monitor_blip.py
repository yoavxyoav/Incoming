"""Tests for the quiet_streak / auto_clear_minutes blip-suppression logic."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import AlertEvent, AlertGroup
from app.monitor import poll_loop
from app.store import AlertStore


def _make_alert_event(cat: str = "1", alert_id: str = "test-id-1") -> AlertEvent:
    """Create a minimal AlertEvent for testing."""
    return AlertEvent(
        id=alert_id,
        cat=cat,
        cat_label="Missiles / Rockets",
        title="ירי רקטות וטילים",
        desc="היכנסו למרחב המוגן",
        areas=["Tel Aviv"],
        categorized_areas={"מרכז": ["Tel Aviv"]},
        received_at=datetime.now(timezone.utc),
    )


def _make_store(has_active: bool = True) -> MagicMock:
    store = MagicMock()
    store.clear.return_value = has_active
    store.is_new.return_value = False
    if has_active:
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {"cat": "1", "areas": ["Tel Aviv"]}
        store.current = [mock_event]
    else:
        store.current = []
    # Pre-configure groups with an ended group (explicitly_ended=False) so the
    # broadcast payload is inspectable in tests that check the groups message.
    mock_group = AlertGroup(
        cat="1",
        cat_label="Missiles / Rockets",
        title="Test",
        from_time=datetime.now(timezone.utc),
        to_time=datetime.now(timezone.utc),
        areas=["Tel Aviv"],
        categorized_areas={"מרכז": ["Tel Aviv"]},
        is_ended=True,
        explicitly_ended=False,
    )
    store.groups = [mock_group]
    return store


def _make_manager() -> MagicMock:
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    return manager


async def _run_n_empty_polls(n_empty: int, grace: int) -> tuple[MagicMock, MagicMock]:
    """Run poll_loop for exactly `n_empty` empty polls then cancel.

    `grace` is the number of polls before auto-clear fires.
    With poll_interval=0 the monitor falls back to 1.0s denominator, so
    auto_clear_minutes = grace / 60 produces exactly `grace` grace polls.
    """
    store = _make_store(has_active=True)
    manager = _make_manager()

    # grace_polls = round(auto_clear_minutes * 60 / poll_secs)
    # poll_secs falls back to 1.0 when poll_interval=0, so:
    auto_clear_minutes = grace / 60

    call_count = 0

    async def fake_fetch(_client: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count > n_empty:
            # Stop the loop after exactly n_empty calls
            raise asyncio.CancelledError()
        return None

    with (
        patch("app.monitor._fetch_alert", side_effect=fake_fetch),
        patch("app.monitor.settings.auto_clear_minutes", auto_clear_minutes),
        patch("app.monitor.settings.poll_interval", 0),
        patch("app.monitor.settings.region", "*"),
    ):
        try:
            await poll_loop(store, manager)
        except asyncio.CancelledError:
            pass

    return store, manager


@pytest.mark.asyncio
async def test_no_clear_before_grace_period() -> None:
    """2 empty polls with grace=3 must NOT trigger store.clear()."""
    store, manager = await _run_n_empty_polls(n_empty=2, grace=3)
    store.clear.assert_not_called()
    for call in manager.broadcast.call_args_list:
        msg = call.args[0] if call.args else {}
        assert msg.get("type") != "clear", "Unexpected clear broadcast before grace period"


@pytest.mark.asyncio
async def test_clear_fires_after_grace_period() -> None:
    """3 empty polls with grace=3 must trigger store.clear(), end_all_active_groups,
    and broadcast ended per cat + groups with explicitly_ended=False."""
    store, manager = await _run_n_empty_polls(n_empty=3, grace=3)
    store.clear.assert_called()
    store.end_all_active_groups.assert_called_once()
    broadcast_types = [
        (call.args[0] if call.args else {}).get("type")
        for call in manager.broadcast.call_args_list
    ]
    assert "ended" in broadcast_types, "Expected 'ended' WS broadcast per active cat after grace period"
    assert "groups" in broadcast_types, "Expected 'groups' WS broadcast after grace period"
    # The groups payload must contain the group with explicitly_ended=False (timeout, not Oref-confirmed)
    groups_calls = [
        call.args[0]
        for call in manager.broadcast.call_args_list
        if (call.args[0] if call.args else {}).get("type") == "groups"
    ]
    assert groups_calls, "Expected at least one groups broadcast"
    groups_payload = groups_calls[0]["payload"]
    assert len(groups_payload) > 0, "Expected non-empty groups payload"
    assert groups_payload[0]["explicitly_ended"] is False, (
        "Timeout-cleared group must have explicitly_ended=False"
    )


def test_explicit_all_clear_sets_explicitly_ended_true() -> None:
    """end_group_for_cat(explicitly=True) must mark group as explicitly ended by Oref."""
    s = AlertStore()
    s.set_alert(_make_alert_event())
    assert s.groups[0].is_ended is False

    now = datetime.now(timezone.utc)
    s.end_group_for_cat("1", now, explicitly=True)

    g = s.groups[0]
    assert g.is_ended is True
    assert g.explicitly_ended is True


def test_timeout_clear_sets_explicitly_ended_false() -> None:
    """end_all_active_groups(explicitly=False) must mark group as timeout-cleared (not Oref-confirmed)."""
    s = AlertStore()
    s.set_alert(_make_alert_event())
    assert s.groups[0].is_ended is False

    now = datetime.now(timezone.utc)
    s.end_all_active_groups(now, explicitly=False)

    g = s.groups[0]
    assert g.is_ended is True
    assert g.explicitly_ended is False


def test_non_ended_group_not_in_active_history() -> None:
    """A non-ended group must be absent from the history view (is_ended filter contract)."""
    s = AlertStore()
    s.set_alert(_make_alert_event())

    assert len(s.groups) == 1
    assert s.groups[0].is_ended is False

    # Frontend contract: history only shows groups where is_ended === true
    history_groups = [g for g in s.groups if g.is_ended]
    assert len(history_groups) == 0, "Non-ended group must not appear in history"
