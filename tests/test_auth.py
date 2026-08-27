from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.db import get_db_session
from app.auth.db_models import Base, Principal
from app.auth.dependencies import get_current_principal, require_admin
from app.auth.repository import AuthRepository
from app.core.config import Settings, get_settings
from app.main import app
from enterprise_auth.crypto import sha256_hex
from enterprise_auth.passwords import PasswordService
from enterprise_auth.saml import PingSamlService


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    settings = Settings(
        database_url="sqlite+pysqlite://",
        jwt_key_id="test-key",
        jwt_signing_key=private_pem,
        jwt_verification_key=public_pem,
        jwt_access_ttl_seconds=300,
    )

    def session_override() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    prior_principal_override = app.dependency_overrides.pop(get_current_principal, None)
    prior_admin_override = app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app, base_url="https://testserver") as client:
            client.headers.update({"Origin": "http://localhost:5173"})
            client.session_factory = session_factory  # type: ignore[attr-defined]
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)
        if prior_principal_override:
            app.dependency_overrides[get_current_principal] = prior_principal_override
        if prior_admin_override:
            app.dependency_overrides[require_admin] = prior_admin_override
        engine.dispose()


def create_account(client: TestClient, *, username: str, password: str, role: str) -> str:
    session_factory = client.session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        account = AuthRepository(session).create_local_account(
            username=username,
            display_name=f"{username.title()} User",
            email=f"{username}@example.test",
            password_hash=PasswordService().hash(password),
            role=role,
            must_change_password=False,
            performed_by=None,
        )
        return account.principal_id


def test_auth_config_derives_provider_availability_without_feature_flags(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "providers": {"pingSso": False, "localAccount": True},
        "pingStatus": "not_configured",
        "pingLoginUrl": "/auth/login",
        "localLoginUrl": "/auth/local/login",
        "preauthSupportUrl": None,
    }


def test_local_admin_login_session_refresh_and_protected_api(auth_client: TestClient) -> None:
    create_account(auth_client, username="admin", password="correct horse battery", role="ADMIN")

    login = auth_client.post(
        "/auth/local/login",
        json={"username": "ADMIN", "password": "correct horse battery"},
    )

    assert login.status_code == 200
    payload = login.json()
    assert payload["principal"]["role"] == "ADMIN"
    assert payload["principal"]["authenticationProvider"] == "LOCAL"
    assert "__Host-dsp_session" in login.headers["set-cookie"]
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "Secure" in login.headers["set-cookie"]

    protected = auth_client.get(
        "/api/v1/admin/control-plane",
        headers={"Authorization": f"Bearer {payload['accessToken']}"},
    )
    assert protected.status_code == 200

    csrf = auth_client.cookies.get("__Host-dsp_csrf")
    refreshed = auth_client.post("/auth/refresh", headers={"X-CSRF-Token": csrf or ""})
    assert refreshed.status_code == 200
    assert refreshed.json()["accessToken"] != payload["accessToken"]


def test_read_only_user_cannot_open_admin_control_plane(auth_client: TestClient) -> None:
    create_account(auth_client, username="reader", password="correct horse battery", role="READ_ONLY")
    login = auth_client.post(
        "/auth/local/login",
        json={"username": "reader", "password": "correct horse battery"},
    )

    response = auth_client.get(
        "/api/v1/admin/control-plane",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
    )

    assert response.status_code == 403


def test_invalid_local_password_is_not_distinguishable_from_unknown_user(
    auth_client: TestClient,
) -> None:
    create_account(auth_client, username="reader", password="correct horse battery", role="READ_ONLY")

    wrong = auth_client.post(
        "/auth/local/login",
        json={"username": "reader", "password": "incorrect password"},
    )
    unknown = auth_client.post(
        "/auth/local/login",
        json={"username": "nobody", "password": "incorrect password"},
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_admin_can_create_a_governed_read_only_local_account(auth_client: TestClient) -> None:
    create_account(auth_client, username="admin", password="correct horse battery", role="ADMIN")
    login = auth_client.post(
        "/auth/local/login",
        json={"username": "admin", "password": "correct horse battery"},
    )
    bearer = {
        "Authorization": f"Bearer {login.json()['accessToken']}",
        "X-Idempotency-Key": "create-analyst-one-0001",
    }

    created = auth_client.post(
        "/auth/admin/local-users",
        headers=bearer,
        json={
            "username": "analyst.one",
            "displayName": "Analyst One",
            "email": "analyst.one@example.test",
            "role": "READ_ONLY",
            "reason": "Provision a read-only analyst account",
        },
    )

    assert created.status_code == 201
    assert created.json()["account"]["role"] == "READ_ONLY"
    assert created.json()["account"]["mustChangePassword"] is True
    assert created.json()["passwordAction"]["actionType"] == "INITIAL_SETUP"


def test_ping_exchange_code_is_bound_to_the_originating_browser_and_single_use(
    auth_client: TestClient,
) -> None:
    principal_id = create_account(
        auth_client,
        username="reader",
        password="correct horse battery",
        role="READ_ONLY",
    )
    token_id = "exchange-token-with-at-least-thirty-two-characters"
    session_factory = auth_client.session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        AuthRepository(session).create_exchange_code(
            code_hash=sha256_hex(token_id),
            principal_id=principal_id,
            login_nonce_hash=sha256_hex("origin-browser"),
            return_path="#jobs",
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )

    auth_client.cookies.set("__Host-dsp_login", "different-browser")
    rejected = auth_client.post("/auth/exchange", json={"tokenId": token_id})
    assert rejected.status_code == 401

    # A browser mismatch burns the code. A new login transaction is required.
    auth_client.cookies.set("__Host-dsp_login", "origin-browser")
    consumed = auth_client.post("/auth/exchange", json={"tokenId": token_id})
    assert consumed.status_code == 401

    second_token_id = "second-exchange-token-with-at-least-thirty-two-characters"
    with session_factory() as session:
        AuthRepository(session).create_exchange_code(
            code_hash=sha256_hex(second_token_id),
            principal_id=principal_id,
            login_nonce_hash=sha256_hex("origin-browser"),
            return_path="#jobs",
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )
    accepted = auth_client.post("/auth/exchange", json={"tokenId": second_token_id})
    assert accepted.status_code == 200
    assert accepted.json()["returnPath"] == "#jobs"

    replayed = auth_client.post("/auth/exchange", json={"tokenId": second_token_id})
    assert replayed.status_code == 401


def test_admin_authorization_is_revoked_when_database_role_changes(auth_client: TestClient) -> None:
    principal_id = create_account(
        auth_client,
        username="admin",
        password="correct horse battery",
        role="ADMIN",
    )
    login = auth_client.post(
        "/auth/local/login",
        json={"username": "admin", "password": "correct horse battery"},
    )
    token = login.json()["accessToken"]

    session_factory = auth_client.session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        principal = session.get(Principal, principal_id)
        assert principal is not None
        principal.role = "READ_ONLY"
        principal.authorization_version += 1
        session.commit()

    response = auth_client.get(
        "/api/v1/admin/control-plane",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_admin_provisions_one_time_password_setup_action(auth_client: TestClient) -> None:
    create_account(auth_client, username="admin", password="correct horse battery", role="ADMIN")
    login = auth_client.post(
        "/auth/local/login",
        json={"username": "admin", "password": "correct horse battery"},
    )
    created = auth_client.post(
        "/auth/admin/local-users",
        headers={
            "Authorization": f"Bearer {login.json()['accessToken']}",
            "X-Idempotency-Key": "provision-new-reader-0001",
        },
        json={
            "username": "new.reader",
            "displayName": "New Reader",
            "role": "READ_ONLY",
            "reason": "Approved local support account",
        },
    )
    assert created.status_code == 201
    first_action_code = created.json()["passwordAction"]["actionCode"]
    account_id = created.json()["account"]["id"]
    reset = auth_client.post(
        f"/auth/admin/local-users/{account_id}/password-action",
        headers={
            "Authorization": f"Bearer {login.json()['accessToken']}",
            "X-Idempotency-Key": "reset-new-reader-0001",
        },
        json={"reason": "Replace the original setup code"},
    )
    assert reset.status_code == 201
    action_code = reset.json()["actionCode"]

    superseded = auth_client.post(
        "/auth/local/password-action",
        json={"actionCode": first_action_code, "newPassword": "a strong local password"},
    )
    completed = auth_client.post(
        "/auth/local/password-action",
        json={"actionCode": action_code, "newPassword": "a strong local password"},
    )
    replayed = auth_client.post(
        "/auth/local/password-action",
        json={"actionCode": action_code, "newPassword": "another strong password"},
    )
    signed_in = auth_client.post(
        "/auth/local/login",
        json={"username": "new.reader", "password": "a strong local password"},
    )

    assert superseded.status_code == 400
    assert completed.status_code == 200
    assert replayed.status_code == 400
    assert signed_in.status_code == 200


def test_logout_revokes_the_access_token_session_immediately(auth_client: TestClient) -> None:
    create_account(auth_client, username="reader", password="correct horse battery", role="READ_ONLY")
    login = auth_client.post(
        "/auth/local/login",
        json={"username": "reader", "password": "correct horse battery"},
    )
    token = login.json()["accessToken"]
    csrf = auth_client.cookies.get("__Host-dsp_csrf") or ""

    signed_out = auth_client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    protected = auth_client.get(
        "/api/v1/home",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert signed_out.status_code == 200
    assert protected.status_code == 401


def test_local_account_expiry_invalidates_an_existing_access_token(auth_client: TestClient) -> None:
    principal_id = create_account(
        auth_client,
        username="reader",
        password="correct horse battery",
        role="READ_ONLY",
    )
    login = auth_client.post(
        "/auth/local/login",
        json={"username": "reader", "password": "correct horse battery"},
    )
    token = login.json()["accessToken"]

    session_factory = auth_client.session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        principal = session.get(Principal, principal_id)
        assert principal is not None and principal.local_account is not None
        principal.local_account.account_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    protected = auth_client.get(
        "/api/v1/home",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert protected.status_code == 401


def test_authentication_posts_reject_unapproved_origins(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/local/login",
        headers={"Origin": "https://attacker.example"},
        json={"username": "admin", "password": "admin"},
    )
    assert response.status_code == 403


def test_local_login_is_rate_limited_in_postgresql_state(auth_client: TestClient) -> None:
    responses = [
        auth_client.post(
            "/auth/local/login",
            json={"username": "unknown-user", "password": "incorrect password"},
        )
        for _ in range(11)
    ]

    assert all(response.status_code == 401 for response in responses[:10])
    assert responses[-1].status_code == 429
    assert responses[-1].headers["Retry-After"] == "60"


def test_saml_authentication_time_comes_from_authn_instant() -> None:
    class AssertionNode:
        def get(self, key: str) -> str | None:
            return "2026-08-26T08:15:30Z" if key == "AuthnInstant" else None

    class ValidatedResponse:
        def _query_assertion(self, _query: str) -> list[AssertionNode]:
            return [AssertionNode()]

    class Auth:
        validated_response = ValidatedResponse()

    authentication_time = PingSamlService._authentication_time(Auth())  # type: ignore[arg-type]

    assert authentication_time == datetime(2026, 8, 26, 8, 15, 30, tzinfo=UTC)
