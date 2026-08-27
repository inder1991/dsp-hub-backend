"""FastAPI authentication and role dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.db import get_db_session
from app.auth.db_models import AuthRefreshSession
from app.auth.repository import AuthRepository, as_utc
from app.auth.schemas import TokenPrincipal
from app.auth.service import build_token_service
from app.core.config import Settings, get_settings
from enterprise_auth.exceptions import AuthenticationConfigurationError, TokenRejected

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ResourceScope:
    """Current principal's visibility over user-owned portal resources."""

    is_admin: bool
    owner_keys: frozenset[str]


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
    session=Depends(get_db_session),
) -> TokenPrincipal:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        claims = build_token_service(settings).verify(credentials.credentials)
        token_principal = TokenPrincipal(
            id=str(claims["sub"]),
            session_id=str(claims["sid"]),
            role=str(claims["role"]),
            authentication_provider=str(claims["auth_provider"]),
            authorization_version=int(claims["authorization_version"]),
        )
        current = AuthRepository(session).get_principal(token_principal.id)
        refresh_session = session.get(AuthRefreshSession, token_principal.session_id)
        local_account_invalid = False
        if current is not None and token_principal.authentication_provider == "LOCAL":
            local_account = current.local_account
            local_account_invalid = bool(
                local_account is None
                or not local_account.is_enabled
                or local_account.must_change_password
                or (
                    local_account.account_expires_at is not None
                    and as_utc(local_account.account_expires_at) <= datetime.now(UTC)
                )
                or (
                    local_account.password_expires_at is not None
                    and as_utc(local_account.password_expires_at) <= datetime.now(UTC)
                )
            )
        if (
            current is None
            or not current.is_active
            or current.role != token_principal.role
            or current.authorization_version != token_principal.authorization_version
            or refresh_session is None
            or refresh_session.principal_id != token_principal.id
            or refresh_session.authentication_provider != token_principal.authentication_provider
            or refresh_session.authorization_version != token_principal.authorization_version
            or refresh_session.revoked_at is not None
            or as_utc(refresh_session.expires_at) <= datetime.now(UTC)
            or local_account_invalid
        ):
            raise TokenRejected("Access token authorization is no longer current")
        return token_principal
    except AuthenticationConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication keys are not configured") from exc
    except (TokenRejected, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc


def get_resource_scope(
    token_principal: Annotated[TokenPrincipal, Depends(get_current_principal)],
    session=Depends(get_db_session),
) -> ResourceScope:
    if token_principal.role == "ADMIN":
        return ResourceScope(is_admin=True, owner_keys=frozenset())
    current = AuthRepository(session).get_principal(token_principal.id)
    values = {token_principal.id}
    if current is not None:
        values.update(
            value for value in (current.username, current.enterprise_user_id, current.email) if value
        )
    expanded = set(values)
    for value in values:
        expanded.add(re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-"))
    return ResourceScope(is_admin=False, owner_keys=frozenset(expanded))


def require_role(required_role: Literal["ADMIN", "READ_ONLY"]):
    def dependency(
        principal: Annotated[TokenPrincipal, Depends(get_current_principal)],
    ) -> TokenPrincipal:
        if required_role == "ADMIN" and principal.role != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
        return principal

    return dependency


def require_admin(
    request: Request,
    token_principal: Annotated[TokenPrincipal, Depends(get_current_principal)],
    session=Depends(get_db_session),
) -> TokenPrincipal:
    repository = AuthRepository(session)
    current = repository.get_principal(token_principal.id)
    permitted = bool(
        current
        and current.is_active
        and current.role == "ADMIN"
        and current.authorization_version == token_principal.authorization_version
        and token_principal.role == "ADMIN"
    )
    if not permitted:
        repository.audit(
            "AUTHORIZATION_DENIED",
            "REJECTED",
            principal_id=token_principal.id,
            source_ip=request.client.host if request.client else None,
            correlation_id=getattr(request.state, "correlation_id", None),
            detail="CURRENT_ADMIN_AUTHORIZATION_REQUIRED",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current administrator authorization is required",
        )
    return token_principal
