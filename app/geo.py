import json
import re
from pathlib import Path

import httpx

from app.logger import log

_lamas: dict[str, set[str]] = {}


def _standardize(name: str) -> str:
    return re.sub(r"[\(\)'\"]+", "", name).strip()


def _load_from_dict(raw: dict[str, object]) -> dict[str, set[str]]:
    if "areas" not in raw:
        raise ValueError("lamas.json missing 'areas' key")
    areas = raw["areas"]
    if not isinstance(areas, dict):
        raise ValueError("lamas.json 'areas' must be a dict")
    result: dict[str, set[str]] = {}
    for area, cities in areas.items():
        if isinstance(cities, dict):
            result[str(area)] = {_standardize(c) for c in cities.keys()}
        else:
            result[str(area)] = set()
    return result


def load(lamas_path: str, lamas_url: str) -> None:
    """Load lamas geographic data; download from GitHub if not present."""
    global _lamas
    path = Path(lamas_path)

    raw: dict[str, object] | None = None

    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            log.info("Loaded lamas.json from %s", path)
        except Exception as exc:
            log.warning("Failed to parse local lamas.json: %s", exc)

    if raw is None:
        log.info("Downloading lamas.json from %s", lamas_url)
        try:
            resp = httpx.get(lamas_url, timeout=10)
            resp.raise_for_status()
            raw = resp.json()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            log.info("Saved lamas.json to %s", path)
        except Exception as exc:
            log.error("Could not download lamas.json: %s", exc)
            _lamas = {}
            return

    try:
        _lamas = _load_from_dict(raw)  # type: ignore[arg-type]
        log.info("Loaded %d geographic areas", len(_lamas))
    except Exception as exc:
        log.error("Invalid lamas.json structure: %s", exc)
        _lamas = {}


def categorize(cities: list[str]) -> dict[str, list[str]]:
    """Map each city to its geographic area. Unknown → 'Other'."""
    standardized = [_standardize(c) for c in cities]
    result: dict[str, list[str]] = {}
    for original, std in zip(cities, standardized):
        matched = False
        for area, area_cities in _lamas.items():
            if std in area_cities:
                result.setdefault(area, []).append(original)
                matched = True
                break
        if not matched:
            result.setdefault("Other", []).append(original)
    return {area: sorted(places) for area, places in sorted(result.items())}
