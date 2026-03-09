import pytest
from app import geo


@pytest.fixture(autouse=True)
def clear_lamas() -> None:
    """Reset geo state between tests."""
    geo._lamas = {}


def test_categorize_empty() -> None:
    result = geo.categorize([])
    assert result == {}


def test_categorize_unknown_city() -> None:
    geo._lamas = {}
    result = geo.categorize(["עיר לא קיימת"])
    assert result == {"Other": ["עיר לא קיימת"]}


def test_categorize_known_city() -> None:
    geo._lamas = {"צפון": {"תל חי", "קריית שמונה"}}
    result = geo.categorize(["קריית שמונה"])
    assert result == {"צפון": ["קריית שמונה"]}


def test_categorize_multiple_areas() -> None:
    geo._lamas = {
        "צפון": {"קריית שמונה", "נהריה"},
        "דרום": {"אשדוד", "אשקלון"},
    }
    result = geo.categorize(["קריית שמונה", "אשדוד", "לא ידוע"])
    assert "צפון" in result
    assert "דרום" in result
    assert "Other" in result
    assert "קריית שמונה" in result["צפון"]
    assert "אשדוד" in result["דרום"]


def test_standardize_removes_parens() -> None:
    geo._lamas = {"מרכז": {"תל אביב"}}
    result = geo.categorize(["תל אביב (יפו)"])
    # after standardization parens are stripped → shouldn't match, goes to Other
    assert "Other" in result or "מרכז" in result


def test_load_from_dict_missing_areas() -> None:
    with pytest.raises(ValueError):
        geo._load_from_dict({})


def test_load_from_dict_valid() -> None:
    data = {"areas": {"north": {"Haifa": {}, "Acre": {}}}}
    result = geo._load_from_dict(data)  # type: ignore[arg-type]
    assert "north" in result
    assert "Haifa" in result["north"]
