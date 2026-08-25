from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


HealthLevel = Literal["operational", "degraded", "major_issue"]
ItemState = Literal[
    "operational",
    "degraded",
    "major_issue",
    "running",
    "completed",
    "healthy",
    "needs_attention",
    "informational",
    "action_required",
    "no_action",
]


class HealthService(ApiModel):
    id: str
    name: str
    state: ItemState
    status: str
    summary: Optional[str] = None


class HealthSummary(ApiModel):
    state: HealthLevel
    label: str
    affected_systems: int = Field(ge=0)
    services: list[HealthService]


class SystemStatus(HealthService):
    details_url: Optional[str] = None


class IncidentSummary(ApiModel):
    message: str
    url: Optional[str] = None


class Metric(ApiModel):
    label: str
    value: int = Field(ge=0)


class ResourceItem(ApiModel):
    id: str
    name: str
    type: str
    state: ItemState
    status: str


class MyDspSummary(ApiModel):
    metrics: list[Metric]
    active_resources: list[ResourceItem]


class ActivityItem(ApiModel):
    id: str
    name: str
    activity: str
    state: ItemState
    status: str
    occurred_at: str


class UpcomingChange(ApiModel):
    id: str
    date_label: str
    title: str
    impact: str
    state: ItemState
    status: str
    url: Optional[str] = None


class ExternalLinks(ApiModel):
    confluence_dsp: Optional[str] = None
    confluence_status: Optional[str] = None
    confluence_releases: Optional[str] = None
    remedy_tickets: Optional[str] = None
    remedy_requests: Optional[str] = None


class DashboardResponse(ApiModel):
    generated_at: datetime
    health: HealthSummary
    systems: list[SystemStatus]
    incident: IncidentSummary
    my_dsp: MyDspSummary
    recent_activity: list[ActivityItem]
    upcoming_changes: list[UpcomingChange]
    external_links: ExternalLinks


class ServiceHealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str = "dsp-portal-backend"
    environment: str
