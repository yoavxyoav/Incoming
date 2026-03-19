"""Tests for the quiet_streak / clear_grace_polls blip-suppression logic."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.monitor import poll_loop


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
    return store


def _make_manager() -> MagicMock:
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    return manager


async def _run_n_empty_polls(n_empty: int, grace: int) -> tuple[MagicMock, MagicMock]:
    """Run poll_loop for exactly `n_empty` empty polls then cancel."""
    store = _make_store(has_active=True)
    manager = _make_manager()

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
        patch("app.monitor.settings.clear_grace_polls", grace),
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
    """3 empty polls with grace=3 must trigger store.clear() and broadcast ended per cat + groups."""
    store, manager = await _run_n_empty_polls(n_empty=3, grace=3)
    store.clear.assert_called()
    store.end_all_active_groups.assert_called_once()
    broadcast_types = [
        (call.args[0] if call.args else {}).get("type")
        for call in manager.broadcast.call_args_list
    ]
    assert "ended" in broadcast_types, "Expected 'ended' WS broadcast per active cat after grace period"
    assert "groups" in broadcast_types, "Expected 'groups' WS broadcast after grace period"
