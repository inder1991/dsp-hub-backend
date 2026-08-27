"""Asymmetrically signed, short-lived DSP access tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError

from enterprise_auth.crypto import new_opaque_value
from enterprise_auth.exceptions import AuthenticationConfigurationError, TokenRejected
from enterprise_auth.models import IssuedAccessToken


class JwtTokenService:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        algorithm: str,
        key_id: str,
        signing_key: str,
        verification_key: str,
        ttl_seconds: int,
    ) -> None:
        if not algorithm.startswith(("RS", "PS", "ES")):
            raise AuthenticationConfigurationError("JWT algorithm must use an asymmetric key")
        if not signing_key or not verification_key or not key_id:
            raise AuthenticationConfigurationError(
                "JWT signing key, verification key, and key id are required"
            )
        self._issuer = issuer
        self._audience = audience
        self._algorithm = algorithm
        self._key_id = key_id
        self._signing_key = signing_key
        self._verification_key = verification_key
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        principal_id: str,
        session_id: str,
        role: str,
        auth_provider: str,
        authorization_version: int,
    ) -> IssuedAccessToken:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        claims = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": principal_id,
            "sid": session_id,
            "jti": new_opaque_value(),
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "role": role,
            "auth_provider": auth_provider,
            "authorization_version": authorization_version,
        }
        encoded = jwt.encode(
            claims,
            self._signing_key,
            algorithm=self._algorithm,
            headers={"kid": self._key_id},
        )
        return IssuedAccessToken(
            token=encoded,
            expires_at=expires_at,
            expires_in_seconds=self._ttl_seconds,
        )

    def verify(self, token: str) -> dict[str, object]:
        try:
            if jwt.get_unverified_header(token).get("kid") != self._key_id:
                raise TokenRejected("Access token key identifier is not accepted")
            return jwt.decode(
                token,
                self._verification_key,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "nbf",
                        "sub",
                        "sid",
                        "iss",
                        "aud",
                        "role",
                        "auth_provider",
                        "authorization_version",
                    ]
                },
            )
        except InvalidTokenError as exc:
            raise TokenRejected("Access token is invalid or expired") from exc
