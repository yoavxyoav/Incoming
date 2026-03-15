"""
Tests for the frontend state handler auto-dismiss timer logic.

The JS logic in the `state` WS handler is:
    remaining = ALERT_MAX_MS - (Date.now() - new Date(alert.received_at).getTime())
    if remaining <= 0: showClear(cat) immediately
    else: setTimeout(showClear, remaining)

These tests validate the time-remaining calculation that determines whether
an active alert on page load should be dismissed immediately or after a delay.
"""

import time
from datetime import datetime, timedelta, timezone


ALERT_MAX_MS = 20 * 60 * 1000  # 20 minutes in milliseconds


def compute_remaining_ms(received_at_iso: str, now_ms: int | None = None) -> int:
    """
    Mirror of the JS logic:
        remaining = ALERT_MAX_MS - (Date.now() - new Date(received_at).getTime())
    Returns remaining milliseconds; negative means already expired.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    received_ms = int(
        datetime.fromisoformat(received_at_iso.replace("Z", "+00:00")).timestamp() * 1000
    )
    return ALERT_MAX_MS - (now_ms - received_ms)


def test_fresh_alert_has_nearly_full_remaining():
    """Alert received just now should have ~20 minutes remaining."""
    now = datetime.now(timezone.utc)
    received_at = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    remaining = compute_remaining_ms(received_at, now_ms)
    # Should be very close to ALERT_MAX_MS (within 100ms of test execution)
    assert remaining > ALERT_MAX_MS - 100
    assert remaining <= ALERT_MAX_MS


def test_alert_received_19_minutes_ago_has_short_remaining():
    """Alert received 19 minutes ago should have ~1 minute remaining."""
    now = datetime.now(timezone.utc)
    received_at = (now - timedelta(minutes=19)).isoformat()
    now_ms = int(now.timestamp() * 1000)
    remaining = compute_remaining_ms(received_at, now_ms)
    one_minute_ms = 60 * 1000
    assert remaining > 0
    assert abs(remaining - one_minute_ms) < 100  # within 100ms


def test_alert_received_exactly_20_minutes_ago_is_zero():
    """Alert received exactly 20 minutes ago should have 0 remaining."""
    now = datetime.now(timezone.utc)
    received_at = (now - timedelta(minutes=20)).isoformat()
    now_ms = int(now.timestamp() * 1000)
    remaining = compute_remaining_ms(received_at, now_ms)
    assert remaining == 0


def test_alert_received_21_minutes_ago_is_negative():
    """Alert received 21 minutes ago → negative remaining → dismiss immediately."""
    now = datetime.now(timezone.utc)
    received_at = (now - timedelta(minutes=21)).isoformat()
    now_ms = int(now.timestamp() * 1000)
    remaining = compute_remaining_ms(received_at, now_ms)
    assert remaining < 0


def test_should_dismiss_immediately_when_remaining_le_zero():
    """The JS condition `if (remaining <= 0) showClear(cat)` fires for expired alerts."""
    now = datetime.now(timezone.utc)
    test_cases = [
        (now - timedelta(minutes=20), True),   # exactly expired
        (now - timedelta(minutes=25), True),   # well past expiry
        (now - timedelta(minutes=19, seconds=59), False),  # 1s left — timer, not immediate
        (now, False),                           # brand new — timer
    ]
    for received_dt, expect_immediate in test_cases:
        received_at = received_dt.isoformat()
        now_ms = int(now.timestamp() * 1000)
        remaining = compute_remaining_ms(received_at, now_ms)
        is_immediate = remaining <= 0
        assert is_immediate == expect_immediate, (
            f"received_at={received_at}: expected immediate={expect_immediate}, "
            f"got remaining={remaining}ms"
        )


def test_remaining_is_bounded_by_alert_max_ms():
    """Remaining should never exceed ALERT_MAX_MS (clocks can't go backwards in practice)."""
    now = datetime.now(timezone.utc)
    received_at = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    remaining = compute_remaining_ms(received_at, now_ms)
    assert remaining <= ALERT_MAX_MS


def test_z_suffix_iso_string_parses_correctly():
    """received_at strings with 'Z' suffix (UTC) should parse the same as +00:00."""
    now = datetime.now(timezone.utc)
    received_at_z = now.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    received_at_offset = now.isoformat()
    now_ms = int(now.timestamp() * 1000)
    r1 = compute_remaining_ms(received_at_z, now_ms)
    r2 = compute_remaining_ms(received_at_offset, now_ms)
    assert abs(r1 - r2) < 10  # within 10ms (microsecond rounding)
