"""Harden authentication state and local account governance.

Revision ID: f6c1d7a9b204
Revises: c8a59245527f
Create Date: 2026-08-26 23:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6c1d7a9b204"
down_revision: str | Sequence[str] | None = "c8a59245527f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint("ck_principal_role", "principal", "role IN ('ADMIN', 'READ_ONLY')")
    op.create_check_constraint(
        "ck_principal_authentication_source",
        "principal",
        "authentication_source IN ('PING_SAML', 'LOCAL')",
    )

    op.add_column("local_account", sa.Column("account_expires_at", sa.DateTime(timezone=True)))
    op.add_column("local_account", sa.Column("created_by_principal_id", sa.String(length=36)))
    op.create_foreign_key(
        "fk_local_account_created_by",
        "local_account",
        "principal",
        ["created_by_principal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_local_account_account_expires_at",
        "local_account",
        ["account_expires_at"],
    )
    op.create_check_constraint(
        "ck_local_account_failed_attempts",
        "local_account",
        "failed_attempts >= 0",
    )

    op.drop_constraint("uq_saml_assertion_replay", "saml_assertion_replay", type_="unique")
    op.alter_column(
        "saml_assertion_replay",
        "assertion_id",
        new_column_name="assertion_id_hash",
    )
    op.alter_column(
        "saml_assertion_replay",
        "assertion_id_hash",
        type_=sa.String(length=64),
        postgresql_using=(
            "md5('dsp-replay-1:' || assertion_id_hash) || md5('dsp-replay-2:' || assertion_id_hash)"
        ),
    )
    op.create_unique_constraint(
        "uq_saml_assertion_replay",
        "saml_assertion_replay",
        ["issuer", "assertion_id_hash"],
    )

    op.add_column(
        "auth_exchange_code",
        sa.Column("provider_session_expires_at", sa.DateTime(timezone=True)),
    )

    op.add_column("auth_refresh_session", sa.Column("session_family_id", sa.String(length=36)))
    op.add_column("auth_refresh_session", sa.Column("authorization_version", sa.Integer()))
    op.add_column(
        "auth_refresh_session",
        sa.Column("replaced_by_session_id", sa.String(length=36)),
    )
    op.execute("UPDATE auth_refresh_session SET session_family_id = id")
    op.execute(
        "UPDATE auth_refresh_session AS s "
        "SET authorization_version = p.authorization_version "
        "FROM principal AS p WHERE p.id = s.principal_id"
    )
    op.alter_column("auth_refresh_session", "session_family_id", nullable=False)
    op.alter_column("auth_refresh_session", "authorization_version", nullable=False)
    op.create_index(
        "ix_auth_refresh_session_session_family_id",
        "auth_refresh_session",
        ["session_family_id"],
    )
    op.create_foreign_key(
        "fk_auth_refresh_replaced_by",
        "auth_refresh_session",
        "auth_refresh_session",
        ["replaced_by_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_refresh_authentication_provider",
        "auth_refresh_session",
        "authentication_provider IN ('PING_SAML', 'LOCAL')",
    )
    op.create_check_constraint(
        "ck_refresh_authorization_version",
        "auth_refresh_session",
        "authorization_version > 0",
    )

    op.add_column("local_password_action", sa.Column("action_code_hash", sa.String(length=64)))
    op.add_column("local_password_action", sa.Column("action_type", sa.String(length=40)))
    op.add_column(
        "local_password_action",
        sa.Column("issued_by_principal_id", sa.String(length=36)),
    )
    op.add_column(
        "local_password_action",
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "local_password_action",
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "UPDATE local_password_action SET "
        "action_code_hash = md5('dsp-action-1:' || id) || md5('dsp-action-2:' || id), "
        "action_type = CASE WHEN action ILIKE '%CREATE%' THEN 'INITIAL_SETUP' ELSE 'RESET' END, "
        "issued_by_principal_id = performed_by_principal_id, "
        "expires_at = created_at + INTERVAL '15 minutes', "
        "consumed_at = created_at"
    )
    op.alter_column("local_password_action", "action_code_hash", nullable=False)
    op.alter_column("local_password_action", "action_type", nullable=False)
    op.alter_column("local_password_action", "expires_at", nullable=False)
    op.create_foreign_key(
        "fk_password_action_issued_by",
        "local_password_action",
        "principal",
        ["issued_by_principal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_local_password_action_action_code_hash",
        "local_password_action",
        ["action_code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_local_password_action_expires_at",
        "local_password_action",
        ["expires_at"],
    )
    op.create_index(
        "ix_password_action_account_expiry",
        "local_password_action",
        ["local_account_id", "expires_at"],
    )
    op.create_check_constraint(
        "ck_password_action_type",
        "local_password_action",
        "action_type IN ('INITIAL_SETUP', 'RESET')",
    )
    op.drop_constraint(
        "local_password_action_performed_by_principal_id_fkey",
        "local_password_action",
        type_="foreignkey",
    )
    op.drop_column("local_password_action", "performed_by_principal_id")
    op.drop_column("local_password_action", "action")

    op.create_table(
        "auth_rate_limit_bucket",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("request_count >= 0", name="ck_auth_rate_request_count"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "key_hash", "window_started_at", name="uq_auth_rate_bucket"),
    )
    op.create_index(
        "ix_auth_rate_bucket_expiry",
        "auth_rate_limit_bucket",
        ["expires_at"],
    )

    op.create_table(
        "auth_idempotency_key",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_idempotency_key_key_hash",
        "auth_idempotency_key",
        ["key_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_idempotency_key_expires_at",
        "auth_idempotency_key",
        ["expires_at"],
    )

    op.add_column(
        "authentication_audit_event",
        sa.Column("correlation_id", sa.String(length=80)),
    )
    op.add_column(
        "authentication_audit_event",
        sa.Column("target_principal_id", sa.String(length=36)),
    )
    op.add_column(
        "authentication_audit_event",
        sa.Column("idempotency_key_hash", sa.String(length=64)),
    )
    op.add_column("authentication_audit_event", sa.Column("before_state", sa.Text()))
    op.add_column("authentication_audit_event", sa.Column("after_state", sa.Text()))
    op.create_index(
        "ix_authentication_audit_event_correlation_id",
        "authentication_audit_event",
        ["correlation_id"],
    )
    op.create_index(
        "ix_authentication_audit_event_target_principal_id",
        "authentication_audit_event",
        ["target_principal_id"],
    )
    op.create_unique_constraint(
        "uq_auth_audit_idempotency_key_hash",
        "authentication_audit_event",
        ["idempotency_key_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_auth_audit_idempotency_key_hash",
        "authentication_audit_event",
        type_="unique",
    )
    op.drop_index(
        "ix_authentication_audit_event_target_principal_id",
        table_name="authentication_audit_event",
    )
    op.drop_index(
        "ix_authentication_audit_event_correlation_id",
        table_name="authentication_audit_event",
    )
    for column in (
        "after_state",
        "before_state",
        "idempotency_key_hash",
        "target_principal_id",
        "correlation_id",
    ):
        op.drop_column("authentication_audit_event", column)

    op.drop_index("ix_auth_idempotency_key_expires_at", table_name="auth_idempotency_key")
    op.drop_index("ix_auth_idempotency_key_key_hash", table_name="auth_idempotency_key")
    op.drop_table("auth_idempotency_key")
    op.drop_index("ix_auth_rate_bucket_expiry", table_name="auth_rate_limit_bucket")
    op.drop_table("auth_rate_limit_bucket")

    op.add_column("local_password_action", sa.Column("action", sa.String(length=40)))
    op.add_column(
        "local_password_action",
        sa.Column("performed_by_principal_id", sa.String(length=36)),
    )
    op.execute(
        "UPDATE local_password_action SET action = action_type, "
        "performed_by_principal_id = issued_by_principal_id"
    )
    op.alter_column("local_password_action", "action", nullable=False)
    op.create_foreign_key(
        "local_password_action_performed_by_principal_id_fkey",
        "local_password_action",
        "principal",
        ["performed_by_principal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("ck_password_action_type", "local_password_action", type_="check")
    op.drop_index("ix_password_action_account_expiry", table_name="local_password_action")
    op.drop_index("ix_local_password_action_expires_at", table_name="local_password_action")
    op.drop_index("ix_local_password_action_action_code_hash", table_name="local_password_action")
    op.drop_constraint("fk_password_action_issued_by", "local_password_action", type_="foreignkey")
    for column in (
        "consumed_at",
        "expires_at",
        "issued_by_principal_id",
        "action_type",
        "action_code_hash",
    ):
        op.drop_column("local_password_action", column)

    op.drop_constraint("ck_refresh_authorization_version", "auth_refresh_session", type_="check")
    op.drop_constraint("ck_refresh_authentication_provider", "auth_refresh_session", type_="check")
    op.drop_constraint("fk_auth_refresh_replaced_by", "auth_refresh_session", type_="foreignkey")
    op.drop_index("ix_auth_refresh_session_session_family_id", table_name="auth_refresh_session")
    op.drop_column("auth_refresh_session", "replaced_by_session_id")
    op.drop_column("auth_refresh_session", "authorization_version")
    op.drop_column("auth_refresh_session", "session_family_id")

    op.drop_column("auth_exchange_code", "provider_session_expires_at")

    op.drop_constraint("uq_saml_assertion_replay", "saml_assertion_replay", type_="unique")
    op.alter_column(
        "saml_assertion_replay",
        "assertion_id_hash",
        type_=sa.String(length=255),
    )
    op.alter_column(
        "saml_assertion_replay",
        "assertion_id_hash",
        new_column_name="assertion_id",
    )
    op.create_unique_constraint(
        "uq_saml_assertion_replay",
        "saml_assertion_replay",
        ["issuer", "assertion_id"],
    )

    op.drop_constraint("ck_local_account_failed_attempts", "local_account", type_="check")
    op.drop_index("ix_local_account_account_expires_at", table_name="local_account")
    op.drop_constraint("fk_local_account_created_by", "local_account", type_="foreignkey")
    op.drop_column("local_account", "created_by_principal_id")
    op.drop_column("local_account", "account_expires_at")

    op.drop_constraint("ck_principal_authentication_source", "principal", type_="check")
    op.drop_constraint("ck_principal_role", "principal", type_="check")
