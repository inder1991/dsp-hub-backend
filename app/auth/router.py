"""Public provider routes, application sessions, and local-user administration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import parse_qs, quote, urlparse

from fastapi import APIRouter, Cookie, Depends, Form, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.db import get_db_session
from app.auth.db_models import LocalAccount
from app.auth.dependencies import get_current_principal, require_admin
from app.auth.repository import AuthRepository, as_utc, normalize_username
from app.auth.schemas import (
    AuthConfigResponse,
    AuthSessionResponse,
    CurrentPrincipal,
    ExchangeRequest,
    LocalAccountCreate,
    LocalAccountProvisionResponse,
    LocalAccountUpdate,
    LocalAccountView,
    LoginRequest,
    MessageResponse,
    PasswordActionIssue,
    PasswordActionIssueRequest,
    PasswordActionRequest,
    ProviderAvailability,
    TokenPrincipal,
)
from app.auth.service import DspAuthenticationService, current_principal, local_account_view
from app.core.config import Settings, get_settings
from enterprise_auth.crypto import new_opaque_value, sha256_hex
from enterprise_auth.exceptions import (
    AuthenticationConfigurationError,
    InvalidCredentials,
    PasswordChangeRequired,
    SamlResponseRejected,
)
from enterprise_auth.saml import PingSamlService

router = APIRouter(prefix="/auth", tags=["authentication"])

SESSION_COOKIE = "__Host-dsp_session"
LOGIN_COOKIE = "__Host-dsp_login"
CSRF_COOKIE = "__Host-dsp_csrf"


def _repository(session: Annotated[Session, Depends(get_db_session)]) -> AuthRepository:
    return AuthRepository(session)


def _service(
    repository: Annotated[AuthRepository, Depends(_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DspAuthenticationService:
    return DspAuthenticationService(repository, settings)


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def _enforce_rate_limit(
    repository: AuthRepository,
    *,
    scope: str,
    key: str,
    limit: int,
) -> None:
    if not repository.allow_rate_limit(scope=scope, key_hash=sha256_hex(key), limit=limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication requests. Try again shortly.",
            headers={"Retry-After": "60"},
        )


def _set_session_cookies(response: Response, session_secret: str, csrf_secret: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_secret,
        max_age=max_age,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_secret,
        max_age=max_age,
        secure=True,
        httponly=False,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="strict", path="/")
    response.delete_cookie(CSRF_COOKIE, secure=True, httponly=False, samesite="strict", path="/")
    response.delete_cookie(LOGIN_COOKIE, secure=True, httponly=True, samesite="lax", path="/")


def _safe_return_path(value: str) -> str:
    if value.startswith("#") and not value.startswith("#//"):
        return value[:500]
    if value.startswith("/") and not value.startswith("//"):
        return f"#{value.lstrip('/')}"[:500]
    return "#home"


def _relay_secret(relay_state: str) -> str:
    parsed = urlparse(relay_state)
    if parsed.query:
        value = parse_qs(parsed.query).get("state", [""])[0]
        if value:
            return value
    return relay_state


def _login_error_redirect(settings: Settings, request: Request, error_code: str) -> RedirectResponse:
    correlation = quote(_correlation_id(request) or "")
    target = settings.frontend_base_url.rstrip("/")
    return RedirectResponse(
        f"{target}/#login?authError={quote(error_code)}&correlationId={correlation}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _account_state(account: LocalAccount) -> dict[str, object]:
    return local_account_view(account).model_dump(mode="json")


def _reserve_admin_operation(
    repository: AuthRepository,
    *,
    admin: TokenPrincipal,
    operation: str,
    idempotency_key: str | None,
) -> str:
    if not idempotency_key or len(idempotency_key) < 16 or len(idempotency_key) > 200:
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key must contain between 16 and 200 characters",
        )
    key_hash = sha256_hex(f"{admin.id}:{operation}:{idempotency_key}")
    if not repository.reserve_idempotency_key(key_hash=key_hash, operation=operation):
        raise HTTPException(status_code=409, detail="This administrator operation was already submitted")
    return key_hash


def _issue_password_action(
    repository: AuthRepository,
    settings: Settings,
    account: LocalAccount,
    *,
    issued_by: str,
    action_type: str,
) -> PasswordActionIssue:
    action_code = new_opaque_value()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.local_password_action_ttl_seconds)
    repository.create_password_action(
        account,
        action_code_hash=sha256_hex(action_code),
        action_type=action_type,
        issued_by=issued_by,
        expires_at=expires_at,
    )
    return PasswordActionIssue(
        action_code=action_code,
        action_type=action_type,
        expires_at=expires_at,
    )


@router.get("/config", response_model=AuthConfigResponse)
def auth_config(settings: Annotated[Settings, Depends(get_settings)]) -> AuthConfigResponse:
    ping_status = (
        "configured"
        if settings.ping_configured
        else "incomplete"
        if settings.ping_configuration_started
        else "not_configured"
    )
    return AuthConfigResponse(
        providers=ProviderAvailability(ping_sso=settings.ping_configured),
        ping_status=ping_status,
        preauth_support_url=settings.preauth_support_url or None,
    )


@router.get("/login")
def ping_login(
    request: Request,
    repository: Annotated[AuthRepository, Depends(_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    return_to: Annotated[str, Query(alias="returnTo")] = "#home",
) -> RedirectResponse:
    if not settings.ping_configured:
        return _login_error_redirect(settings, request, "PING_UNAVAILABLE")
    _enforce_rate_limit(
        repository,
        scope="PING_LOGIN_IP",
        key=_request_ip(request),
        limit=settings.auth_rate_limit_per_minute,
    )
    nonce = new_opaque_value()
    relay_secret = new_opaque_value()
    relay_url = f"{settings.saml_acs_url}?state={quote(relay_secret)}"
    try:
        saml = PingSamlService(settings)
        redirect_url, request_id = saml.begin(saml.request_data(request), relay_url)
    except (AuthenticationConfigurationError, SamlResponseRejected, OSError) as exc:
        repository.audit(
            "PING_LOGIN",
            "FAILED",
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail=type(exc).__name__,
        )
        return _login_error_redirect(settings, request, "PING_UNAVAILABLE")

    repository.store_login_transaction(
        relay_state_hash=sha256_hex(relay_secret),
        request_id=request_id,
        login_nonce_hash=sha256_hex(nonce),
        return_path=_safe_return_path(return_to),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.login_transaction_ttl_seconds),
    )
    response = RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        LOGIN_COOKIE,
        nonce,
        max_age=settings.login_transaction_ttl_seconds,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/saml/acs")
async def saml_acs(
    request: Request,
    repository: Annotated[AuthRepository, Depends(_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    saml_response: Annotated[str, Form(alias="SAMLResponse")],
    relay_state: Annotated[str, Form(alias="RelayState")],
) -> RedirectResponse:
    del saml_response  # The SAML library reads the request form; never retain or log the assertion.
    if not settings.ping_configured:
        return _login_error_redirect(settings, request, "PING_UNAVAILABLE")
    _enforce_rate_limit(
        repository,
        scope="PING_ACS_IP",
        key=_request_ip(request),
        limit=settings.auth_rate_limit_per_minute,
    )
    relay_secret = _relay_secret(relay_state)
    transaction = repository.login_transaction(sha256_hex(relay_secret))
    if transaction is None or as_utc(transaction.expires_at) <= datetime.now(UTC):
        repository.audit(
            "PING_SAML",
            "REJECTED",
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail="LOGIN_TRANSACTION_INVALID",
        )
        return _login_error_redirect(settings, request, "LOGIN_EXPIRED")
    form = {key: str(value) for key, value in (await request.form()).items()}
    try:
        saml = PingSamlService(settings)
        identity = saml.validate(saml.request_data(request, form), request_id=transaction.saml_request_id)
    except (AuthenticationConfigurationError, SamlResponseRejected, OSError) as exc:
        repository.audit(
            "PING_SAML",
            "REJECTED",
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail=type(exc).__name__,
        )
        return _login_error_redirect(settings, request, "PING_RESPONSE_REJECTED")

    approved_groups = {
        group.casefold() for group in (*settings.access_group_list, *settings.admin_group_list)
    }
    if not approved_groups.intersection(group.casefold() for group in identity.groups):
        repository.audit(
            "PING_ACCESS",
            "DENIED",
            username=identity.enterprise_user_id or identity.subject,
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail="NO_APPROVED_ACCESS_GROUP",
        )
        return _login_error_redirect(settings, request, "ACCESS_NOT_APPROVED")

    now = datetime.now(UTC)
    if identity.assertion_expires_at is None or as_utc(identity.assertion_expires_at) <= now:
        return _login_error_redirect(settings, request, "PING_RESPONSE_EXPIRED")
    if (
        identity.provider_session_expires_at is not None
        and as_utc(identity.provider_session_expires_at) <= now
    ):
        return _login_error_redirect(settings, request, "PING_SESSION_EXPIRED")

    token_id = new_opaque_value()
    accepted = repository.accept_saml_identity_and_create_exchange(
        transaction.id,
        identity=identity,
        admin_groups=settings.admin_group_list,
        code_hash=sha256_hex(token_id),
        assertion_id_hash=sha256_hex(identity.assertion_id or ""),
        code_expires_at=now + timedelta(seconds=settings.auth_code_ttl_seconds),
        replay_expires_at=as_utc(identity.assertion_expires_at)
        + timedelta(seconds=settings.saml_clock_skew_seconds),
    )
    if accepted is None:
        repository.audit(
            "PING_SAML",
            "REJECTED",
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail="REPLAY_OR_TRANSACTION_REUSE",
        )
        return _login_error_redirect(settings, request, "PING_RESPONSE_REUSED")
    principal, _ = accepted
    repository.audit(
        "PING_SAML",
        "SUCCEEDED",
        principal_id=principal.id,
        username=principal.username,
        source_ip=_request_ip(request),
        correlation_id=_correlation_id(request),
    )
    return RedirectResponse(
        f"{settings.frontend_base_url.rstrip('/')}/#auth/callback?token_id={quote(token_id)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/exchange", response_model=AuthSessionResponse)
def exchange(
    payload: ExchangeRequest,
    request: Request,
    response: Response,
    repository: Annotated[AuthRepository, Depends(_repository)],
    service: Annotated[DspAuthenticationService, Depends(_service)],
    login_nonce: Annotated[str | None, Cookie(alias=LOGIN_COOKIE)] = None,
) -> AuthSessionResponse:
    _enforce_rate_limit(
        repository,
        scope="TOKEN_EXCHANGE_IP",
        key=_request_ip(request),
        limit=service.settings.auth_rate_limit_per_minute,
    )
    code, outcome = repository.consume_exchange_code(
        sha256_hex(payload.token_id),
        sha256_hex(login_nonce or ""),
    )
    if code is None:
        repository.audit(
            "TOKEN_EXCHANGE",
            "REJECTED",
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail=outcome,
        )
        raise HTTPException(status_code=401, detail="Login code is invalid or expired")
    principal = repository.get_principal(code.principal_id)
    if principal is None or not principal.is_active:
        raise HTTPException(status_code=401, detail="Login principal is unavailable")
    try:
        access_token, session_secret, csrf_secret, expires_in = service.create_session(
            principal,
            provider="PING_SAML",
            authenticated_at=code.authenticated_at,
            provider_session_expires_at=code.provider_session_expires_at,
        )
    except AuthenticationConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication keys are not configured") from exc
    repository.audit(
        "TOKEN_EXCHANGE",
        "SUCCEEDED",
        principal_id=principal.id,
        source_ip=_request_ip(request),
        correlation_id=_correlation_id(request),
    )
    _set_session_cookies(response, session_secret, csrf_secret, service.settings.session_ttl_seconds)
    response.delete_cookie(LOGIN_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    return AuthSessionResponse(
        access_token=access_token,
        expires_in=expires_in,
        return_path=code.return_path,
        principal=current_principal(principal, "PING_SAML"),
    )


@router.post("/local/login", response_model=AuthSessionResponse)
def local_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    repository: Annotated[AuthRepository, Depends(_repository)],
    service: Annotated[DspAuthenticationService, Depends(_service)],
) -> AuthSessionResponse:
    normalized_username = normalize_username(payload.username)
    rate_key = f"{_request_ip(request)}:{normalized_username}"
    _enforce_rate_limit(
        repository,
        scope="LOCAL_LOGIN_IP",
        key=_request_ip(request),
        limit=service.settings.auth_rate_limit_per_minute,
    )
    _enforce_rate_limit(
        repository,
        scope="LOCAL_LOGIN",
        key=rate_key,
        limit=service.settings.local_auth_rate_limit_per_minute,
    )
    try:
        principal, _ = service.authenticate_local(payload.username, payload.password)
        access_token, session_secret, csrf_secret, expires_in = service.create_session(
            principal,
            provider="LOCAL",
        )
    except PasswordChangeRequired as exc:
        repository.audit(
            "LOCAL_LOGIN",
            "ACTION_REQUIRED",
            username=normalized_username,
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail="PASSWORD_ACTION_REQUIRED",
        )
        raise HTTPException(status_code=403, detail="Password setup or reset is required") from exc
    except InvalidCredentials as exc:
        repository.audit(
            "LOCAL_LOGIN",
            "REJECTED",
            username=normalized_username,
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
        )
        raise HTTPException(status_code=401, detail="Username or password is incorrect") from exc
    except AuthenticationConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication keys are not configured") from exc
    repository.audit(
        "LOCAL_LOGIN",
        "SUCCEEDED",
        principal_id=principal.id,
        username=principal.username,
        source_ip=_request_ip(request),
        correlation_id=_correlation_id(request),
    )
    _set_session_cookies(response, session_secret, csrf_secret, service.settings.session_ttl_seconds)
    return AuthSessionResponse(
        access_token=access_token,
        expires_in=expires_in,
        return_path=_safe_return_path(payload.return_to),
        principal=current_principal(principal, "LOCAL"),
    )


@router.post("/local/password-action", response_model=MessageResponse)
def complete_password_action(
    payload: PasswordActionRequest,
    request: Request,
    repository: Annotated[AuthRepository, Depends(_repository)],
    service: Annotated[DspAuthenticationService, Depends(_service)],
) -> MessageResponse:
    _enforce_rate_limit(
        repository,
        scope="PASSWORD_ACTION_IP",
        key=_request_ip(request),
        limit=service.settings.local_auth_rate_limit_per_minute,
    )
    if len(payload.new_password) < service.settings.local_password_min_length:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Password must contain at least {service.settings.local_password_min_length} characters"
            ),
        )
    account = repository.consume_password_action(
        sha256_hex(payload.action_code),
        password_hash=service.passwords.hash(payload.new_password),
    )
    if account is None:
        raise HTTPException(status_code=400, detail="Password action is invalid or expired")
    repository.audit(
        "LOCAL_PASSWORD_ACTION",
        "SUCCEEDED",
        principal_id=account.principal_id,
        username=account.normalized_username,
        source_ip=_request_ip(request),
        correlation_id=_correlation_id(request),
    )
    return MessageResponse(message="Password updated. Sign in with the new password.")


@router.post("/refresh", response_model=AuthSessionResponse)
def refresh(
    request: Request,
    response: Response,
    repository: Annotated[AuthRepository, Depends(_repository)],
    service: Annotated[DspAuthenticationService, Depends(_service)],
    session_secret: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthSessionResponse:
    try:
        principal, token, rotated_session, rotated_csrf, expires_in = service.refresh_session(
            session_secret or "", csrf_cookie or "", csrf_header or ""
        )
    except (InvalidCredentials, AuthenticationConfigurationError) as exc:
        repository.audit(
            "SESSION_REFRESH",
            "REJECTED",
            source_ip=_request_ip(request),
            correlation_id=_correlation_id(request),
            detail=type(exc).__name__,
        )
        raise HTTPException(status_code=401, detail="Session could not be refreshed") from exc
    repository.audit(
        "SESSION_REFRESH",
        "SUCCEEDED",
        principal_id=principal.id,
        source_ip=_request_ip(request),
        correlation_id=_correlation_id(request),
    )
    _set_session_cookies(response, rotated_session, rotated_csrf, service.settings.session_ttl_seconds)
    return AuthSessionResponse(
        access_token=token,
        expires_in=expires_in,
        principal=current_principal(principal),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    repository: Annotated[AuthRepository, Depends(_repository)],
    service: Annotated[DspAuthenticationService, Depends(_service)],
    session_secret: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> MessageResponse:
    outcome = "SUCCEEDED"
    if session_secret:
        try:
            service.revoke_session(session_secret, csrf_cookie or "", csrf_header or "")
        except InvalidCredentials:
            outcome = "INVALID_SESSION"
    repository.audit(
        "LOGOUT",
        outcome,
        source_ip=_request_ip(request),
        correlation_id=_correlation_id(request),
    )
    _clear_auth_cookies(response)
    return MessageResponse(message="Signed out")


@router.get("/me", response_model=CurrentPrincipal)
def me(
    token_principal: Annotated[TokenPrincipal, Depends(get_current_principal)],
    repository: Annotated[AuthRepository, Depends(_repository)],
) -> CurrentPrincipal:
    principal = repository.get_principal(token_principal.id)
    if (
        principal is None
        or not principal.is_active
        or principal.authorization_version != token_principal.authorization_version
    ):
        raise HTTPException(status_code=401, detail="Principal is unavailable")
    return current_principal(principal, token_principal.authentication_provider)


@router.get("/admin/local-users", response_model=list[LocalAccountView])
def list_local_users(
    _admin: Annotated[TokenPrincipal, Depends(require_admin)],
    repository: Annotated[AuthRepository, Depends(_repository)],
) -> list[LocalAccountView]:
    return [local_account_view(account) for account in repository.list_local_accounts()]


@router.post(
    "/admin/local-users",
    response_model=LocalAccountProvisionResponse,
    status_code=201,
)
def create_local_user(
    payload: LocalAccountCreate,
    request: Request,
    admin: Annotated[TokenPrincipal, Depends(require_admin)],
    repository: Annotated[AuthRepository, Depends(_repository)],
    service: Annotated[DspAuthenticationService, Depends(_service)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> LocalAccountProvisionResponse:
    operation = f"CREATE_LOCAL_USER:{normalize_username(payload.username)}"
    key_hash = _reserve_admin_operation(
        repository,
        admin=admin,
        operation=operation,
        idempotency_key=idempotency_key,
    )
    try:
        account = repository.create_local_account(
            username=payload.username,
            display_name=payload.display_name,
            email=payload.email,
            password_hash=service.passwords.hash(new_opaque_value()),
            role=payload.role,
            must_change_password=True,
            performed_by=admin.id,
            account_expires_at=payload.account_expires_at,
        )
    except IntegrityError as exc:
        repository.session.rollback()
        raise HTTPException(status_code=409, detail="Local username already exists") from exc
    action = _issue_password_action(
        repository,
        service.settings,
        account,
        issued_by=admin.id,
        action_type="INITIAL_SETUP",
    )
    repository.audit(
        "LOCAL_ACCOUNT_CREATE",
        "SUCCEEDED",
        principal_id=admin.id,
        target_principal_id=account.principal_id,
        idempotency_key_hash=key_hash,
        correlation_id=_correlation_id(request),
        detail=payload.reason,
        after_state=_account_state(account),
    )
    return LocalAccountProvisionResponse(account=local_account_view(account), password_action=action)


@router.post(
    "/admin/local-users/{account_id}/password-action",
    response_model=PasswordActionIssue,
    status_code=201,
)
def issue_local_password_action(
    account_id: str,
    payload: PasswordActionIssueRequest,
    request: Request,
    admin: Annotated[TokenPrincipal, Depends(require_admin)],
    repository: Annotated[AuthRepository, Depends(_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PasswordActionIssue:
    account = repository.session.get(LocalAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Local account not found")
    key_hash = _reserve_admin_operation(
        repository,
        admin=admin,
        operation=f"RESET_LOCAL_PASSWORD:{account_id}",
        idempotency_key=idempotency_key,
    )
    action = _issue_password_action(
        repository,
        settings,
        account,
        issued_by=admin.id,
        action_type="RESET",
    )
    account.must_change_password = True
    account.principal.authorization_version += 1
    repository.revoke_principal_sessions(account.principal_id)
    repository.session.commit()
    repository.audit(
        "LOCAL_PASSWORD_RESET_ISSUED",
        "SUCCEEDED",
        principal_id=admin.id,
        target_principal_id=account.principal_id,
        idempotency_key_hash=key_hash,
        correlation_id=_correlation_id(request),
        detail=payload.reason,
    )
    return action


@router.patch("/admin/local-users/{account_id}", response_model=LocalAccountView)
def update_local_user(
    account_id: str,
    payload: LocalAccountUpdate,
    request: Request,
    admin: Annotated[TokenPrincipal, Depends(require_admin)],
    repository: Annotated[AuthRepository, Depends(_repository)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> LocalAccountView:
    account = repository.session.get(LocalAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Local account not found")
    removes_admin = account.principal.role == "ADMIN" and (
        payload.role == "READ_ONLY" or payload.is_enabled is False
    )
    if removes_admin and repository.count_active_admins(excluding_principal_id=account.principal_id) == 0:
        raise HTTPException(status_code=409, detail="The final active administrator cannot be removed")
    key_hash = _reserve_admin_operation(
        repository,
        admin=admin,
        operation=f"UPDATE_LOCAL_USER:{account_id}",
        idempotency_key=idempotency_key,
    )
    before = _account_state(account)
    account = repository.update_local_account(
        account,
        display_name=payload.display_name,
        email=payload.email,
        role=payload.role,
        is_enabled=payload.is_enabled,
        must_change_password=None,
        account_expires_at=payload.account_expires_at,
        set_account_expiry="account_expires_at" in payload.model_fields_set,
        unlock=payload.unlock,
    )
    if payload.role is not None or payload.is_enabled is not None:
        repository.revoke_principal_sessions(account.principal_id)
        repository.session.commit()
    repository.audit(
        "LOCAL_ACCOUNT_UPDATE",
        "SUCCEEDED",
        principal_id=admin.id,
        target_principal_id=account.principal_id,
        idempotency_key_hash=key_hash,
        correlation_id=_correlation_id(request),
        detail=payload.reason,
        before_state=before,
        after_state=_account_state(account),
    )
    return local_account_view(account)
