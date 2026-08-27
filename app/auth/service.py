"""DSP identity resolution, local login, sessions, and account governance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.auth.db_models import LocalAccount, Principal
from app.auth.repository import AuthRepository, as_utc
from app.auth.schemas import CurrentPrincipal, LocalAccountView
from app.core.config import Settings
from enterprise_auth.crypto import hash_matches, new_opaque_value, sha256_hex
from enterprise_auth.exceptions import InvalidCredentials, PasswordChangeRequired
from enterprise_auth.passwords import PasswordService
from enterprise_auth.tokens import JwtTokenService


def build_token_service(settings: Settings) -> JwtTokenService:
    return JwtTokenService(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        algorithm=settings.jwt_algorithm,
        key_id=settings.jwt_key_id,
        signing_key=settings.jwt_signing_key_value,
        verification_key=settings.jwt_verification_key_value,
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )


def permissions_for(role: str) -> list[str]:
    permissions = ["portal:read"]
    if role == "ADMIN":
        permissions.extend(["portal:admin", "local-users:manage", "platform:manage"])
    return permissions


def current_principal(principal: Principal, provider: str | None = None) -> CurrentPrincipal:
    return CurrentPrincipal(
        id=principal.id,
        username=principal.username,
        display_name=principal.display_name,
        email=principal.email,
        enterprise_user_id=principal.enterprise_user_id,
        role=principal.role,
        authentication_provider=provider or principal.authentication_source,
        authorization_version=principal.authorization_version,
        permissions=permissions_for(principal.role),
    )


def local_account_view(account: LocalAccount) -> LocalAccountView:
    return LocalAccountView(
        id=account.id,
        principal_id=account.principal.id,
        username=account.principal.username,
        display_name=account.principal.display_name,
        email=account.principal.email,
        role=account.principal.role,
        is_enabled=account.is_enabled,
        must_change_password=account.must_change_password,
        failed_attempts=account.failed_attempts,
        locked_until=account.locked_until,
        last_login_at=account.last_login_at,
        account_expires_at=account.account_expires_at,
        created_at=account.created_at,
    )


class DspAuthenticationService:
    def __init__(self, repository: AuthRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self.passwords = PasswordService()

    def authenticate_local(self, username: str, password: str) -> tuple[Principal, bool]:
        account = self.repository.local_account_by_username(username, for_update=True)
        now = datetime.now(UTC)
        can_attempt = bool(
            account
            and account.is_enabled
            and account.principal.is_active
            and (account.locked_until is None or as_utc(account.locked_until) <= now)
            and (account.password_expires_at is None or as_utc(account.password_expires_at) > now)
            and (account.account_expires_at is None or as_utc(account.account_expires_at) > now)
        )
        valid_password = self.passwords.verify(account.password_hash if account else None, password)
        if not can_attempt or not valid_password:
            self.repository.record_login_failure(
                account if can_attempt else None,
                max_failures=self.settings.local_max_failures,
                lock_seconds=self.settings.local_lock_seconds,
            )
            raise InvalidCredentials("Username or password is incorrect")

        if self.passwords.needs_rehash(account.password_hash):
            account.password_hash = self.passwords.hash(password)
        self.repository.record_login_success(account)
        if account.must_change_password:
            raise PasswordChangeRequired("A password setup or reset action is required")
        return account.principal, account.must_change_password

    def create_session(
        self,
        principal: Principal,
        *,
        provider: str,
        authenticated_at: datetime | None = None,
        provider_session_expires_at: datetime | None = None,
    ) -> tuple[str, str, str, int]:
        authenticated_at = authenticated_at or datetime.now(UTC)
        session_secret = new_opaque_value()
        csrf_secret = new_opaque_value()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.session_ttl_seconds)
        if provider_session_expires_at is not None:
            expires_at = min(expires_at, as_utc(provider_session_expires_at))
        record = self.repository.create_refresh_session(
            principal_id=principal.id,
            session_secret_hash=sha256_hex(session_secret),
            csrf_secret_hash=sha256_hex(csrf_secret),
            authentication_provider=provider,
            authorization_version=principal.authorization_version,
            authenticated_at=authenticated_at,
            expires_at=expires_at,
        )
        token = build_token_service(self.settings).issue(
            principal_id=principal.id,
            session_id=record.id,
            role=principal.role,
            auth_provider=provider,
            authorization_version=principal.authorization_version,
        )
        return token.token, session_secret, csrf_secret, token.expires_in_seconds

    def refresh_session(
        self,
        session_secret: str,
        csrf_cookie: str,
        csrf_header: str,
    ) -> tuple[Principal, str, str, str, int]:
        record = self.repository.refresh_session(sha256_hex(session_secret), for_update=True)
        now = datetime.now(UTC)
        if record is not None and record.revoked_at is not None:
            self.repository.revoke_session_family(record.session_family_id)
            raise InvalidCredentials("Session reuse was detected")
        if (
            record is None
            or as_utc(record.expires_at) <= now
            or not csrf_cookie
            or csrf_cookie != csrf_header
            or not hash_matches(csrf_cookie, record.csrf_secret_hash)
        ):
            raise InvalidCredentials("Session could not be refreshed")
        principal = self.repository.get_principal(record.principal_id)
        if principal is None or not principal.is_active:
            raise InvalidCredentials("Session principal is unavailable")
        if record.authentication_provider == "LOCAL":
            account = principal.local_account
            if (
                account is None
                or not account.is_enabled
                or account.must_change_password
                or (account.account_expires_at is not None and as_utc(account.account_expires_at) <= now)
                or (account.password_expires_at is not None and as_utc(account.password_expires_at) <= now)
            ):
                self.repository.revoke_session_family(record.session_family_id)
                raise InvalidCredentials("Local account session is no longer eligible")
        if (
            record.authentication_provider == "PING_SAML"
            and principal.role == "ADMIN"
            and as_utc(record.authenticated_at) + timedelta(seconds=self.settings.admin_reauth_seconds) <= now
        ):
            self.repository.revoke_session_family(record.session_family_id)
            raise InvalidCredentials("Enterprise reauthentication is required")

        rotated_session = new_opaque_value()
        rotated_csrf = new_opaque_value()
        successor = self.repository.rotate_refresh_session(
            record,
            session_secret_hash=sha256_hex(rotated_session),
            csrf_secret_hash=sha256_hex(rotated_csrf),
            authorization_version=principal.authorization_version,
        )
        token = build_token_service(self.settings).issue(
            principal_id=principal.id,
            session_id=successor.id,
            role=principal.role,
            auth_provider=record.authentication_provider,
            authorization_version=principal.authorization_version,
        )
        return principal, token.token, rotated_session, rotated_csrf, token.expires_in_seconds

    def revoke_session(self, session_secret: str, csrf_cookie: str, csrf_header: str) -> None:
        record = self.repository.refresh_session(sha256_hex(session_secret), for_update=True)
        if (
            record is None
            or not csrf_cookie
            or csrf_cookie != csrf_header
            or not hash_matches(csrf_cookie, record.csrf_secret_hash)
        ):
            raise InvalidCredentials("Session could not be revoked")
        self.repository.revoke_refresh_session(record)
