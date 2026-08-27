"""Public authentication API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.dashboard import to_camel

PortalRole = Literal["ADMIN", "READ_ONLY"]
AuthProvider = Literal["PING_SAML", "LOCAL"]


class AuthModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProviderAvailability(AuthModel):
    ping_sso: bool
    local_account: bool = True


class AuthConfigResponse(AuthModel):
    providers: ProviderAvailability
    ping_status: Literal["configured", "not_configured", "incomplete"]
    ping_login_url: str = "/auth/login"
    local_login_url: str = "/auth/local/login"
    preauth_support_url: str | None = None


class CurrentPrincipal(AuthModel):
    id: str
    username: str
    display_name: str
    email: str | None = None
    enterprise_user_id: str | None = None
    role: PortalRole
    authentication_provider: AuthProvider
    authorization_version: int
    permissions: list[str]


class TokenPrincipal(AuthModel):
    id: str
    role: PortalRole
    authentication_provider: AuthProvider
    authorization_version: int
    session_id: str


class LoginRequest(AuthModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=1024)
    return_to: str = Field(default="#home", max_length=500)


class PasswordActionRequest(AuthModel):
    action_code: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=1, max_length=1024)


class ExchangeRequest(AuthModel):
    token_id: str = Field(min_length=32, max_length=256)


class AuthSessionResponse(AuthModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    return_path: str = "#home"
    principal: CurrentPrincipal
    must_change_password: bool = False


class LocalAccountCreate(AuthModel):
    username: str = Field(min_length=3, max_length=160)
    display_name: str = Field(min_length=1, max_length=240)
    email: str | None = Field(default=None, max_length=320)
    role: PortalRole = "READ_ONLY"
    account_expires_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


class LocalAccountUpdate(AuthModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=240)
    email: str | None = Field(default=None, max_length=320)
    role: PortalRole | None = None
    is_enabled: bool | None = None
    account_expires_at: datetime | None = None
    unlock: bool = False
    reason: str = Field(min_length=3, max_length=500)


class PasswordActionIssueRequest(AuthModel):
    reason: str = Field(min_length=3, max_length=500)


class LocalAccountView(AuthModel):
    id: str
    principal_id: str
    username: str
    display_name: str
    email: str | None = None
    role: PortalRole
    is_enabled: bool
    must_change_password: bool
    failed_attempts: int
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    account_expires_at: datetime | None = None
    created_at: datetime


class PasswordActionIssue(AuthModel):
    action_code: str
    action_type: Literal["INITIAL_SETUP", "RESET"]
    expires_at: datetime


class LocalAccountProvisionResponse(AuthModel):
    account: LocalAccountView
    password_action: PasswordActionIssue


class MessageResponse(AuthModel):
    message: str
