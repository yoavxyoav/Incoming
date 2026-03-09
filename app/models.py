from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OrefAlertRaw(BaseModel):
    """Raw alert JSON from oref.org.il"""

    id: str
    cat: str
    title: str
    data: list[str]
    desc: str


CATEGORY_LABELS: dict[str, str] = {
    "1": "Missiles / Rockets",
    "2": "UAV",
    "3": "Earthquake",
    "4": "Tsunami",
    "5": "Hostile aircraft intrusion",
    "6": "Unconventional weapon",
    "13": "Nuclear event",
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


class WsMessage(BaseModel):
    """WebSocket message envelope"""

    type: str  # "state" | "alert" | "clear"
    payload: Optional[dict[str, object]] = None


class StatusResponse(BaseModel):
    current: Optional[AlertEvent]
    history: list[AlertEvent]
    connected_clients: int
