"""
Tests for US-004: filterInput `input` event listener behavior.

The JS logic being tested:

    filterInput.addEventListener('input', () => { filterBypassed.clear(); renderActivePanel(); });

Key guarantee: the `input` event does NOT call reevaluateSoundForActiveAlerts().
That function must only be called on:
  - Enter keydown (chip added)
  - chip x click
  - "clear all" click
  - sound-follows-filter toggle
"""

import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_html() -> str:
    with open("frontend/index.html", encoding="utf-8") as f:
        return f.read()


def _get_input_listener_body(html: str) -> str:
    """
    Extract the body of the filterInput 'input' event listener arrow function.
    Matches: filterInput.addEventListener('input', () => { ... });
    """
    pattern = r"filterInput\.addEventListener\('input',\s*\(\)\s*=>\s*\{([^}]*)\}\s*\)"
    m = re.search(pattern, html)
    assert m is not None, "Could not find filterInput 'input' addEventListener in HTML"
    return m.group(1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_input_listener_does_not_call_reevaluate_sound():
    """The input event listener must NOT call reevaluateSoundForActiveAlerts()."""
    html = _load_html()
    body = _get_input_listener_body(html)
    assert "reevaluateSoundForActiveAlerts" not in body, (
        "reevaluateSoundForActiveAlerts() must NOT be called from the filterInput 'input' event"
    )


def test_input_listener_calls_filter_bypassed_clear():
    """The input event listener must call filterBypassed.clear()."""
    html = _load_html()
    body = _get_input_listener_body(html)
    assert "filterBypassed.clear()" in body, (
        "filterBypassed.clear() must be called in the filterInput 'input' event"
    )


def test_input_listener_calls_render_active_panel():
    """The input event listener must call renderActivePanel()."""
    html = _load_html()
    body = _get_input_listener_body(html)
    assert "renderActivePanel()" in body, (
        "renderActivePanel() must be called in the filterInput 'input' event"
    )


def test_reevaluate_called_on_enter_keydown():
    """reevaluateSoundForActiveAlerts() must still be called when Enter adds a chip."""
    html = _load_html()
    # The Enter keydown block contains both renderFilterChips and reevaluateSoundForActiveAlerts
    pattern = r"filterInput\.addEventListener\('keydown'.*?}\s*\)\s*;"
    m = re.search(pattern, html, re.DOTALL)
    assert m is not None, "Could not find filterInput keydown listener"
    block = m.group(0)
    assert "reevaluateSoundForActiveAlerts" in block, (
        "reevaluateSoundForActiveAlerts() must be called in the Enter keydown handler"
    )


def test_reevaluate_called_on_chip_remove():
    """reevaluateSoundForActiveAlerts() must be called when a chip's x is clicked."""
    html = _load_html()
    # Chip remove click handler contains removeFilter or splice + reevaluateSoundForActiveAlerts
    assert "reevaluateSoundForActiveAlerts" in html, (
        "reevaluateSoundForActiveAlerts() must exist in HTML (called by chip x click)"
    )
    # More specifically, find removeFilter or chip click context
    pattern = r"(removeFilter|activeFilters\.splice).*?reevaluateSoundForActiveAlerts"
    m = re.search(pattern, html, re.DOTALL)
    assert m is not None, (
        "reevaluateSoundForActiveAlerts() must follow a chip removal operation"
    )
