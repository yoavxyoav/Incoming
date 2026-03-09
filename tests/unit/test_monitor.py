import pytest

from app.models import OrefAlertRaw
from app.monitor import _is_test, _filter_region, _build_event
from app import geo


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGION", "*")
    monkeypatch.setenv("INCLUDE_TEST_ALERTS", "false")


def make_raw(alert_id: str = "123", cat: str = "1", data: list[str] | None = None) -> OrefAlertRaw:
    return OrefAlertRaw(
        id=alert_id,
        cat=cat,
        title="ירי רקטות וטילים",
        data=data or ["תל אביב", "חולון"],
        desc="היכנסו למרחב המוגן",
    )


def test_is_not_test_for_regular_alert() -> None:
    raw = make_raw()
    assert _is_test(raw) is False


def test_is_test_for_drill_category() -> None:
    raw = make_raw(cat="101")
    assert _is_test(raw) is True


def test_is_test_for_hebrew_keyword() -> None:
    raw = make_raw(data=["בדיקה"])
    assert _is_test(raw) is True


def test_filter_region_wildcard() -> None:
    raw = make_raw(data=["אשדוד"])
    # wildcard always passes
    from app.config import settings
    old = settings.region
    settings.region = "*"
    assert _filter_region(raw) is True
    settings.region = old


def test_filter_region_specific_match() -> None:
    from app.config import settings
    old = settings.region
    settings.region = "אשדוד"
    raw = make_raw(data=["אשדוד", "אשקלון"])
    assert _filter_region(raw) is True
    settings.region = old


def test_filter_region_specific_no_match() -> None:
    from app.config import settings
    old = settings.region
    settings.region = "חיפה"
    raw = make_raw(data=["תל אביב"])
    assert _filter_region(raw) is False
    settings.region = old


def test_build_event_fields() -> None:
    geo._lamas = {}
    raw = make_raw("id42", cat="1", data=["תל אביב"])
    event = _build_event(raw)
    assert event.id == "id42"
    assert event.cat == "1"
    assert event.cat_label == "Missiles / Rockets"
    assert "תל אביב" in event.areas
    assert event.received_at is not None
