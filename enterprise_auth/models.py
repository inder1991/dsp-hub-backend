"""Provider-neutral contracts produced and consumed by authentication code."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AuthenticatedIdentity(BaseModel):
    authentication_provider: str
    issuer: str
    subject: str
    durable_subject: str
    authentication_time: datetime
    assertion_expires_at: datetime | None = None
    provider_session_expires_at: datetime | None = None
    groups: list[str] = Field(default_factory=list)
    attributes: dict[str, list[str]] = Field(default_factory=dict)
    enterprise_user_id: str | None = None
    display_name: str | None = None
    email: str | None = None
    authentication_context: str | None = None
    assertion_id: str | None = None


class IssuedAccessToken(BaseModel):
    token: str
    expires_at: datetime
    expires_in_seconds: int
