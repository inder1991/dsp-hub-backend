"""Transactional PostgreSQL state for DSP authentication."""

from __future__ import annotations

import json
import unicodedata
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.db_models import (
    AuthenticationAuditEvent,
    AuthExchangeCode,
    AuthIdempotencyKey,
    AuthRateLimitBucket,
    AuthRefreshSession,
    LocalAccount,
    LocalPasswordAction,
    Principal,
    PrincipalIdentity,
    SamlAssertionReplay,
    SamlLoginTransaction,
)
from enterprise_auth.models import AuthenticatedIdentity


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().casefold()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_principal(self, principal_id: str) -> Principal | None:
        return self.session.get(Principal, principal_id)

    def local_account_by_username(self, username: str, *, for_update: bool = False) -> LocalAccount | None:
        query = select(LocalAccount).where(LocalAccount.normalized_username == normalize_username(username))
        if for_update:
            query = query.with_for_update()
        return self.session.scalar(query)

    def list_local_accounts(self) -> list[LocalAccount]:
        return list(
            self.session.scalars(
                select(LocalAccount).join(LocalAccount.principal).order_by(Principal.username)
            )
        )

    def count_active_admins(self, excluding_principal_id: str | None = None) -> int:
        query = (
            select(func.count())
            .select_from(Principal)
            .join(LocalAccount)
            .where(
                Principal.role == "ADMIN",
                Principal.is_active.is_(True),
                LocalAccount.is_enabled.is_(True),
            )
        )
        if excluding_principal_id:
            query = query.where(Principal.id != excluding_principal_id)
        return int(self.session.scalar(query) or 0)

    def create_local_account(
        self,
        *,
        username: str,
        display_name: str,
        email: str | None,
        password_hash: str,
        role: str,
        must_change_password: bool,
        performed_by: str | None,
        account_expires_at: datetime | None = None,
    ) -> LocalAccount:
        normalized = normalize_username(username)
        principal = Principal(
            username=normalized,
            display_name=display_name.strip(),
            email=email.strip() if email else None,
            role=role,
            authentication_source="LOCAL",
        )
        account = LocalAccount(
            principal=principal,
            normalized_username=normalized,
            password_hash=password_hash,
            must_change_password=must_change_password,
            created_by_principal_id=performed_by,
            account_expires_at=account_expires_at,
        )
        self.session.add(account)
        self.session.commit()
        self.session.refresh(account)
        return account

    def record_login_failure(
        self,
        account: LocalAccount | None,
        *,
        max_failures: int,
        lock_seconds: int,
    ) -> None:
        if account is not None:
            account.failed_attempts += 1
            if account.failed_attempts >= max_failures:
                account.locked_until = datetime.now(UTC) + timedelta(seconds=lock_seconds)
                account.failed_attempts = 0
        self.session.commit()

    def record_login_success(self, account: LocalAccount) -> None:
        account.failed_attempts = 0
        account.locked_until = None
        account.last_login_at = datetime.now(UTC)
        self.session.commit()

    def update_local_account(
        self,
        account: LocalAccount,
        *,
        display_name: str | None,
        email: str | None,
        role: str | None,
        is_enabled: bool | None,
        must_change_password: bool | None,
        account_expires_at: datetime | None,
        set_account_expiry: bool,
        unlock: bool,
    ) -> LocalAccount:
        if display_name is not None:
            account.principal.display_name = display_name.strip()
        if email is not None:
            account.principal.email = email.strip() or None
        if role is not None and role != account.principal.role:
            account.principal.role = role
            account.principal.authorization_version += 1
        if is_enabled is not None and is_enabled != account.is_enabled:
            account.is_enabled = is_enabled
            account.principal.is_active = is_enabled
            account.principal.authorization_version += 1
        if must_change_password is not None:
            account.must_change_password = must_change_password
        if set_account_expiry:
            account.account_expires_at = account_expires_at
        if unlock:
            account.failed_attempts = 0
            account.locked_until = None
        self.session.commit()
        self.session.refresh(account)
        return account

    def store_login_transaction(
        self,
        *,
        relay_state_hash: str,
        request_id: str,
        login_nonce_hash: str,
        return_path: str,
        expires_at: datetime,
    ) -> SamlLoginTransaction:
        transaction = SamlLoginTransaction(
            relay_state_hash=relay_state_hash,
            saml_request_id=request_id,
            login_nonce_hash=login_nonce_hash,
            return_path=return_path,
            expires_at=expires_at,
        )
        self.session.add(transaction)
        self.session.commit()
        return transaction

    def login_transaction(self, relay_state_hash: str) -> SamlLoginTransaction | None:
        return self.session.scalar(
            select(SamlLoginTransaction).where(
                SamlLoginTransaction.relay_state_hash == relay_state_hash,
                SamlLoginTransaction.consumed_at.is_(None),
            )
        )

    def consume_login_and_record_assertion(
        self,
        transaction_id: str,
        *,
        issuer: str,
        assertion_id: str,
        replay_expires_at: datetime,
    ) -> bool:
        transaction = self.session.scalar(
            select(SamlLoginTransaction).where(SamlLoginTransaction.id == transaction_id).with_for_update()
        )
        now = datetime.now(UTC)
        if (
            transaction is None
            or transaction.consumed_at is not None
            or as_utc(transaction.expires_at) <= now
        ):
            self.session.rollback()
            return False
        transaction.consumed_at = now
        self.session.add(
            SamlAssertionReplay(
                issuer=issuer,
                assertion_id_hash=assertion_id,
                expires_at=replay_expires_at,
            )
        )
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return False
        return True

    def _resolve_ping_principal(
        self,
        identity: AuthenticatedIdentity,
        *,
        admin_groups: list[str],
    ) -> Principal:
        principal_identity = self.session.scalar(
            select(PrincipalIdentity).where(
                PrincipalIdentity.identity_provider == identity.issuer,
                PrincipalIdentity.external_object_id == identity.durable_subject,
            )
        )
        role = "ADMIN" if set(identity.groups).intersection(admin_groups) else "READ_ONLY"
        if principal_identity:
            principal = principal_identity.principal
            principal_identity.subject = identity.subject
            principal_identity.last_authenticated_at = datetime.now(UTC)
            if principal.role != role:
                principal.role = role
                principal.authorization_version += 1
            principal.display_name = identity.display_name or principal.display_name
            principal.email = identity.email or principal.email
            principal.enterprise_user_id = identity.enterprise_user_id or principal.enterprise_user_id
            principal.is_active = True
            return principal

        username = normalize_username(identity.enterprise_user_id or identity.email or identity.subject)
        principal = Principal(
            username=username,
            display_name=identity.display_name or identity.subject,
            email=identity.email,
            enterprise_user_id=identity.enterprise_user_id,
            role=role,
            authentication_source="PING_SAML",
        )
        principal.identities.append(
            PrincipalIdentity(
                identity_provider=identity.issuer,
                external_object_id=identity.durable_subject,
                subject=identity.subject,
                issuer=identity.issuer,
            )
        )
        self.session.add(principal)
        self.session.flush()
        return principal

    def accept_saml_identity_and_create_exchange(
        self,
        transaction_id: str,
        *,
        identity: AuthenticatedIdentity,
        admin_groups: list[str],
        code_hash: str,
        assertion_id_hash: str,
        code_expires_at: datetime,
        replay_expires_at: datetime,
    ) -> tuple[Principal, SamlLoginTransaction] | None:
        """Consume the request, record replay state, resolve identity, and issue one code atomically."""
        transaction = self.session.scalar(
            select(SamlLoginTransaction).where(SamlLoginTransaction.id == transaction_id).with_for_update()
        )
        now = datetime.now(UTC)
        if (
            transaction is None
            or transaction.consumed_at is not None
            or as_utc(transaction.expires_at) <= now
        ):
            self.session.rollback()
            return None
        transaction.consumed_at = now
        self.session.add(
            SamlAssertionReplay(
                issuer=identity.issuer,
                assertion_id_hash=assertion_id_hash,
                expires_at=replay_expires_at,
            )
        )
        try:
            principal = self._resolve_ping_principal(identity, admin_groups=admin_groups)
            self.session.add(
                AuthExchangeCode(
                    code_hash=code_hash,
                    principal_id=principal.id,
                    login_nonce_hash=transaction.login_nonce_hash,
                    return_path=transaction.return_path,
                    authenticated_at=identity.authentication_time,
                    provider_session_expires_at=identity.provider_session_expires_at,
                    expires_at=code_expires_at,
                )
            )
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return None
        return principal, transaction

    def resolve_ping_principal(
        self,
        identity: AuthenticatedIdentity,
        *,
        admin_groups: list[str],
    ) -> Principal:
        principal = self._resolve_ping_principal(identity, admin_groups=admin_groups)
        self.session.commit()
        return principal

    def create_exchange_code(
        self,
        *,
        code_hash: str,
        principal_id: str,
        login_nonce_hash: str,
        return_path: str,
        authenticated_at: datetime,
        expires_at: datetime,
        provider_session_expires_at: datetime | None = None,
    ) -> None:
        self.session.add(
            AuthExchangeCode(
                code_hash=code_hash,
                principal_id=principal_id,
                login_nonce_hash=login_nonce_hash,
                return_path=return_path,
                authenticated_at=authenticated_at,
                provider_session_expires_at=provider_session_expires_at,
                expires_at=expires_at,
            )
        )
        self.session.commit()

    def consume_exchange_code(
        self,
        code_hash: str,
        login_nonce_hash: str,
    ) -> tuple[AuthExchangeCode | None, str]:
        code = self.session.scalar(
            select(AuthExchangeCode)
            .where(
                AuthExchangeCode.code_hash == code_hash,
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        if code is None:
            self.session.rollback()
            return None, "NOT_FOUND"
        if code.consumed_at is not None:
            self.session.rollback()
            return None, "REUSED"
        if as_utc(code.expires_at) <= now:
            code.consumed_at = now
            self.session.commit()
            return None, "EXPIRED"
        if code.login_nonce_hash != login_nonce_hash:
            code.consumed_at = now
            self.session.commit()
            return None, "BROWSER_MISMATCH"
        code.consumed_at = now
        self.session.commit()
        return code, "ACCEPTED"

    def create_refresh_session(
        self,
        *,
        principal_id: str,
        session_secret_hash: str,
        csrf_secret_hash: str,
        authentication_provider: str,
        authorization_version: int,
        authenticated_at: datetime,
        expires_at: datetime,
        session_family_id: str | None = None,
    ) -> AuthRefreshSession:
        record = AuthRefreshSession(
            principal_id=principal_id,
            session_family_id=session_family_id or str(uuid4()),
            session_secret_hash=session_secret_hash,
            csrf_secret_hash=csrf_secret_hash,
            authentication_provider=authentication_provider,
            authorization_version=authorization_version,
            authenticated_at=authenticated_at,
            expires_at=expires_at,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def refresh_session(self, secret_hash: str, *, for_update: bool = False) -> AuthRefreshSession | None:
        query = select(AuthRefreshSession).where(
            AuthRefreshSession.session_secret_hash == secret_hash,
        )
        if for_update:
            query = query.with_for_update()
        return self.session.scalar(query)

    def rotate_refresh_session(
        self,
        record: AuthRefreshSession,
        *,
        session_secret_hash: str,
        csrf_secret_hash: str,
        authorization_version: int,
    ) -> AuthRefreshSession:
        now = datetime.now(UTC)
        successor = AuthRefreshSession(
            principal_id=record.principal_id,
            session_family_id=record.session_family_id,
            session_secret_hash=session_secret_hash,
            csrf_secret_hash=csrf_secret_hash,
            authentication_provider=record.authentication_provider,
            authorization_version=authorization_version,
            authenticated_at=record.authenticated_at,
            expires_at=record.expires_at,
            last_used_at=now,
        )
        self.session.add(successor)
        self.session.flush()
        record.revoked_at = now
        record.replaced_by_session_id = successor.id
        record.last_used_at = datetime.now(UTC)
        self.session.commit()
        return successor

    def revoke_refresh_session(self, record: AuthRefreshSession) -> None:
        record.revoked_at = datetime.now(UTC)
        self.session.commit()

    def revoke_session_family(self, session_family_id: str) -> None:
        now = datetime.now(UTC)
        for record in self.session.scalars(
            select(AuthRefreshSession).where(
                AuthRefreshSession.session_family_id == session_family_id,
                AuthRefreshSession.revoked_at.is_(None),
            )
        ):
            record.revoked_at = now
        self.session.commit()

    def revoke_principal_sessions(self, principal_id: str) -> None:
        now = datetime.now(UTC)
        for record in self.session.scalars(
            select(AuthRefreshSession).where(
                AuthRefreshSession.principal_id == principal_id,
                AuthRefreshSession.revoked_at.is_(None),
            )
        ):
            record.revoked_at = now
        self.session.flush()

    def create_password_action(
        self,
        account: LocalAccount,
        *,
        action_code_hash: str,
        action_type: str,
        issued_by: str,
        expires_at: datetime,
    ) -> LocalPasswordAction:
        now = datetime.now(UTC)
        for outstanding in self.session.scalars(
            select(LocalPasswordAction).where(
                LocalPasswordAction.local_account_id == account.id,
                LocalPasswordAction.consumed_at.is_(None),
            )
        ):
            outstanding.consumed_at = now
        action = LocalPasswordAction(
            local_account_id=account.id,
            action_code_hash=action_code_hash,
            action_type=action_type,
            issued_by_principal_id=issued_by,
            expires_at=expires_at,
        )
        self.session.add(action)
        self.session.commit()
        return action

    def consume_password_action(
        self,
        action_code_hash: str,
        *,
        password_hash: str,
    ) -> LocalAccount | None:
        action = self.session.scalar(
            select(LocalPasswordAction)
            .where(LocalPasswordAction.action_code_hash == action_code_hash)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if action is None or action.consumed_at is not None or as_utc(action.expires_at) <= now:
            self.session.rollback()
            return None
        account = self.session.get(LocalAccount, action.local_account_id)
        if account is None:
            self.session.rollback()
            return None
        action.consumed_at = now
        account.password_hash = password_hash
        account.password_changed_at = now
        account.must_change_password = False
        account.failed_attempts = 0
        account.locked_until = None
        account.is_enabled = True
        account.principal.is_active = True
        account.principal.authorization_version += 1
        self.revoke_principal_sessions(account.principal_id)
        self.session.commit()
        return account

    def allow_rate_limit(
        self,
        *,
        scope: str,
        key_hash: str,
        limit: int,
    ) -> bool:
        now = datetime.now(UTC)
        window_started_at = now.replace(second=0, microsecond=0)
        bucket = self.session.scalar(
            select(AuthRateLimitBucket)
            .where(
                AuthRateLimitBucket.scope == scope,
                AuthRateLimitBucket.key_hash == key_hash,
                AuthRateLimitBucket.window_started_at == window_started_at,
            )
            .with_for_update()
        )
        if bucket is None:
            bucket = AuthRateLimitBucket(
                scope=scope,
                key_hash=key_hash,
                window_started_at=window_started_at,
                request_count=1,
                expires_at=window_started_at + timedelta(minutes=2),
            )
            self.session.add(bucket)
            try:
                self.session.commit()
                return True
            except IntegrityError:
                self.session.rollback()
                return self.allow_rate_limit(scope=scope, key_hash=key_hash, limit=limit)
        if bucket.request_count >= limit:
            self.session.rollback()
            return False
        bucket.request_count += 1
        self.session.commit()
        return True

    def reserve_idempotency_key(self, *, key_hash: str, operation: str) -> bool:
        self.session.add(
            AuthIdempotencyKey(
                key_hash=key_hash,
                operation=operation,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        try:
            self.session.commit()
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def cleanup_expired_auth_state(self, batch_size: int) -> dict[str, int]:
        now = datetime.now(UTC)
        models = (
            SamlLoginTransaction,
            SamlAssertionReplay,
            AuthExchangeCode,
            AuthRefreshSession,
            LocalPasswordAction,
            AuthRateLimitBucket,
            AuthIdempotencyKey,
        )
        deleted: dict[str, int] = {}
        for model in models:
            ids = list(
                self.session.scalars(select(model.id).where(model.expires_at <= now).limit(batch_size))
            )
            if ids:
                self.session.execute(delete(model).where(model.id.in_(ids)))
            deleted[model.__tablename__] = len(ids)
        self.session.commit()
        return deleted

    def audit(
        self,
        event_type: str,
        outcome: str,
        *,
        principal_id: str | None = None,
        username: str | None = None,
        source_ip: str | None = None,
        correlation_id: str | None = None,
        target_principal_id: str | None = None,
        idempotency_key_hash: str | None = None,
        detail: str | None = None,
        before_state: dict[str, object] | None = None,
        after_state: dict[str, object] | None = None,
    ) -> None:
        self.session.add(
            AuthenticationAuditEvent(
                event_type=event_type,
                outcome=outcome,
                principal_id=principal_id,
                username=username,
                source_ip=source_ip,
                correlation_id=correlation_id,
                target_principal_id=target_principal_id,
                idempotency_key_hash=idempotency_key_hash,
                detail=detail,
                before_state=json.dumps(before_state, sort_keys=True) if before_state else None,
                after_state=json.dumps(after_state, sort_keys=True) if after_state else None,
            )
        )
        self.session.commit()
