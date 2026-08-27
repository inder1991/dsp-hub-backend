"""SQLAlchemy authentication entities aligned to the approved logical model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Principal(Base):
    __tablename__ = "principal"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'READ_ONLY')", name="ck_principal_role"),
        CheckConstraint(
            "authentication_source IN ('PING_SAML', 'LOCAL')",
            name="ck_principal_authentication_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(240))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    enterprise_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="READ_ONLY", index=True)
    authentication_source: Mapped[str] = mapped_column(String(24))
    authorization_version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    identities: Mapped[list[PrincipalIdentity]] = relationship(
        back_populates="principal", cascade="all, delete-orphan"
    )
    local_account: Mapped[LocalAccount | None] = relationship(
        back_populates="principal",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="LocalAccount.principal_id",
    )


class PrincipalIdentity(Base):
    __tablename__ = "principal_identity"
    __table_args__ = (
        UniqueConstraint("identity_provider", "external_object_id", name="uq_identity_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principal.id", ondelete="CASCADE"), index=True)
    identity_provider: Mapped[str] = mapped_column(String(80))
    external_object_id: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(320))
    issuer: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    principal: Mapped[Principal] = relationship(back_populates="identities")


class LocalAccount(Base):
    __tablename__ = "local_account"
    __table_args__ = (CheckConstraint("failed_attempts >= 0", name="ck_local_account_failed_attempts"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    principal_id: Mapped[str] = mapped_column(
        ForeignKey("principal.id", ondelete="CASCADE"), unique=True, index=True
    )
    normalized_username: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    account_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principal.id", ondelete="SET NULL"), nullable=True
    )
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    principal: Mapped[Principal] = relationship(back_populates="local_account", foreign_keys=[principal_id])


class SamlLoginTransaction(Base):
    __tablename__ = "saml_login_transaction"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    relay_state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    saml_request_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    login_nonce_hash: Mapped[str] = mapped_column(String(64))
    return_path: Mapped[str] = mapped_column(String(500), default="#home")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SamlAssertionReplay(Base):
    __tablename__ = "saml_assertion_replay"
    __table_args__ = (
        UniqueConstraint("issuer", "assertion_id_hash", name="uq_saml_assertion_replay"),
        Index("ix_saml_replay_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(500))
    assertion_id_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthExchangeCode(Base):
    __tablename__ = "auth_exchange_code"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principal.id", ondelete="CASCADE"), index=True)
    login_nonce_hash: Mapped[str] = mapped_column(String(64))
    return_path: Mapped[str] = mapped_column(String(500), default="#home")
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_session_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthRefreshSession(Base):
    __tablename__ = "auth_refresh_session"
    __table_args__ = (
        CheckConstraint(
            "authentication_provider IN ('PING_SAML', 'LOCAL')",
            name="ck_refresh_authentication_provider",
        ),
        CheckConstraint("authorization_version > 0", name="ck_refresh_authorization_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principal.id", ondelete="CASCADE"), index=True)
    session_family_id: Mapped[str] = mapped_column(String(36), index=True)
    session_secret_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_secret_hash: Mapped[str] = mapped_column(String(64))
    authentication_provider: Mapped[str] = mapped_column(String(24))
    authorization_version: Mapped[int] = mapped_column(Integer)
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("auth_refresh_session.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalPasswordAction(Base):
    __tablename__ = "local_password_action"
    __table_args__ = (
        CheckConstraint("action_type IN ('INITIAL_SETUP', 'RESET')", name="ck_password_action_type"),
        Index("ix_password_action_account_expiry", "local_account_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    local_account_id: Mapped[str] = mapped_column(ForeignKey("local_account.id", ondelete="CASCADE"))
    action_code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    action_type: Mapped[str] = mapped_column(String(40))
    issued_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principal.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthRateLimitBucket(Base):
    __tablename__ = "auth_rate_limit_bucket"
    __table_args__ = (
        UniqueConstraint("scope", "key_hash", "window_started_at", name="uq_auth_rate_bucket"),
        CheckConstraint("request_count >= 0", name="ck_auth_rate_request_count"),
        Index("ix_auth_rate_bucket_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(80))
    key_hash: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthIdempotencyKey(Base):
    __tablename__ = "auth_idempotency_key"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    operation: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthenticationAuditEvent(Base):
    __tablename__ = "authentication_audit_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    principal_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    target_principal_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
