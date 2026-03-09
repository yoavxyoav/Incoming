"""
Integration test — hits the real Oref API.
Run manually: uv run pytest tests/integration/ -v -s
"""
import pytest
import httpx

OREF_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
}


@pytest.mark.integration
def test_oref_api_reachable() -> None:
    resp = httpx.get(OREF_URL, headers=HEADERS, timeout=10)
    assert resp.status_code == 200


@pytest.mark.integration
def test_oref_response_is_valid() -> None:
    """Response is either empty (no alert) or a valid JSON alert object."""
    resp = httpx.get(OREF_URL, headers=HEADERS, timeout=10)
    text = resp.text.replace("\x00", "").strip()
    if not text:
        return  # no active alert — valid
    data = resp.json()
    assert "id" in data
    assert "data" in data
    assert isinstance(data["data"], list)
