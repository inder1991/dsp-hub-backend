from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.dashboard import ApiModel


class SupportIssue(ApiModel):
    id: str
    title: str
    description: str
    estimated_minutes: int = Field(ge=1)
    guide_url: str | None = None


class SupportSpecialist(ApiModel):
    name: str
    role: str
    roster_status: Literal["available", "busy", "offline"]
    teams_url: str | None = None


class SupportServiceItem(ApiModel):
    id: str
    name: str
    description: str
    remedy_url: str | None = None
    specialist: SupportSpecialist
    issues: list[SupportIssue]


class SupportResponse(ApiModel):
    generated_at: datetime
    dsp_support: SupportSpecialist
    services: list[SupportServiceItem]
