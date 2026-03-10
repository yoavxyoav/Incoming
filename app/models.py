from datetime import datetime
from typing import Optional  # used by AlertEvent.categorized_areas via Pydantic

from pydantic import BaseModel


class OrefAlertRaw(BaseModel):
    """Raw alert JSON from oref.org.il"""

    id: str
    cat: str
    title: str
    data: list[str]
    desc: str


CATEGORY_LABELS: dict[str, str] = {
    "1":   "Missiles / Rockets",
    "2":   "UAV",
    "3":   "Earthquake",
    "4":   "Tsunami",
    "5":   "Hostile aircraft intrusion",
    "6":   "Unconventional weapon",
    "10":  "Rockets expected — prepare shelter",
    "13":  "Nuclear event",
    "101": "Drill - Missiles",
    "102": "Drill - UAV",
    "103": "Drill - Earthquake",
}


class AlertEvent(BaseModel):
    """Processed alert enriched with geo categorization"""

    id: str
    cat: str
    cat_label: str
    title: str
    desc: str
    areas: list[str]
    categorized_areas: dict[str, list[str]]
    received_at: datetime


class AlertGroup(BaseModel):
    """A time-windowed group of alerts with merged areas."""

    cat: str
    cat_label: str
    title: str
    from_time: datetime
    to_time: datetime
    areas: list[str]
    categorized_areas: dict[str, list[str]]
    is_ended: bool = False


class StatusResponse(BaseModel):
    current: list[AlertEvent]
    groups: list[AlertGroup]
    connected_clients: int
