"""Ping-compatible SAML request creation and response validation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.constants import OneLogin_Saml2_Constants
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from enterprise_auth.exceptions import AuthenticationConfigurationError, SamlResponseRejected
from enterprise_auth.models import AuthenticatedIdentity


class _InspectableSamlAuth(OneLogin_Saml2_Auth):
    """Retain only the validated response object long enough to read AuthnInstant."""

    validated_response: Any | None = None

    def store_valid_response(self, response: Any) -> None:
        super().store_valid_response(response)
        self.validated_response = response


class PingSamlService:
    """A provider adapter; DSP claim-to-role policy remains outside this class."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        OneLogin_Saml2_Constants.ALLOWED_CLOCK_DRIFT = max(
            0,
            int(settings.saml_clock_skew_seconds),
        )
        self._saml_settings = self._build_settings()

    def request_data(self, request: Any, form: dict[str, str] | None = None) -> dict[str, Any]:
        # Build the public request identity from the registered ACS rather than
        # trusting caller-controlled Host/X-Forwarded-* headers.
        public_url = urlparse(self._settings.saml_acs_url)
        scheme = public_url.scheme
        return {
            "https": "on" if scheme == "https" else "off",
            "http_host": public_url.hostname,
            "server_port": str(public_url.port or (443 if scheme == "https" else 80)),
            "script_name": request.url.path,
            "get_data": dict(request.query_params),
            "post_data": form or {},
        }

    def begin(self, request_data: dict[str, Any], relay_state: str) -> tuple[str, str]:
        auth = _InspectableSamlAuth(request_data, self._saml_settings)
        redirect_url = auth.login(return_to=relay_state)
        request_id = auth.get_last_request_id()
        if not request_id:
            raise SamlResponseRejected("Could not create a SAML request identifier")
        return redirect_url, request_id

    def validate(
        self,
        request_data: dict[str, Any],
        *,
        request_id: str,
    ) -> AuthenticatedIdentity:
        auth = _InspectableSamlAuth(request_data, self._saml_settings)
        auth.process_response(request_id=request_id)
        errors = auth.get_errors()
        if errors or not auth.is_authenticated():
            detail = auth.get_last_error_reason() or ", ".join(errors) or "authentication failed"
            raise SamlResponseRejected(detail)
        if auth.get_last_response_in_response_to() != request_id:
            raise SamlResponseRejected("Ping response does not match the originating request")

        attributes = {key: [str(value) for value in values] for key, values in auth.get_attributes().items()}
        durable_subject = self._one(attributes, self._settings.saml_durable_subject_attribute)
        if not durable_subject:
            raise SamlResponseRejected("Ping response is missing the configured durable subject claim")
        assertion_id = auth.get_last_assertion_id()
        if not assertion_id:
            raise SamlResponseRejected("Ping response is missing an assertion identifier")
        groups = attributes.get(self._settings.saml_groups_attribute, [])
        if not groups:
            raise SamlResponseRejected("Ping response is missing the configured group claim")

        authentication_time = self._authentication_time(auth)
        assertion_expires_at = self._epoch_datetime(auth.get_last_assertion_not_on_or_after())
        if assertion_expires_at is None:
            raise SamlResponseRejected("Ping assertion is missing its validity expiry")
        provider_session_expires_at = self._epoch_datetime(auth.get_session_expiration())

        given_name = self._one(attributes, self._settings.saml_given_name_attribute)
        family_name = self._one(attributes, self._settings.saml_family_name_attribute)
        display_name = " ".join(part for part in (given_name, family_name) if part) or None
        contexts = auth.get_last_authn_contexts() or []
        return AuthenticatedIdentity(
            authentication_provider="PING_SAML",
            issuer=self._settings.saml_expected_issuer,
            subject=auth.get_nameid(),
            durable_subject=durable_subject,
            assertion_id=assertion_id,
            authentication_time=authentication_time,
            assertion_expires_at=assertion_expires_at,
            provider_session_expires_at=provider_session_expires_at,
            authentication_context=contexts[0] if contexts else None,
            groups=groups,
            attributes=attributes,
            enterprise_user_id=self._one(attributes, self._settings.saml_employee_id_attribute),
            email=self._one(attributes, self._settings.saml_email_attribute),
            display_name=display_name,
        )

    @staticmethod
    def _authentication_time(auth: _InspectableSamlAuth) -> datetime:
        response = auth.validated_response
        if response is None:
            raise SamlResponseRejected("Ping response could not be inspected after validation")
        nodes = response._query_assertion("/saml:AuthnStatement[@AuthnInstant]")  # noqa: SLF001
        if len(nodes) != 1:
            raise SamlResponseRejected("Ping assertion must contain one authentication instant")
        value = nodes[0].get("AuthnInstant")
        if not value:
            raise SamlResponseRejected("Ping assertion is missing its authentication instant")
        try:
            epoch = OneLogin_Saml2_Utils.parse_SAML_to_time(value)
        except (TypeError, ValueError) as exc:
            raise SamlResponseRejected("Ping authentication instant is invalid") from exc
        return datetime.fromtimestamp(epoch, UTC)

    @staticmethod
    def _epoch_datetime(value: int | None) -> datetime | None:
        return datetime.fromtimestamp(value, UTC) if value is not None else None

    @staticmethod
    def _one(attributes: dict[str, list[str]], key: str) -> str | None:
        values = attributes.get(key) or []
        return values[0] if values else None

    def _build_settings(self) -> dict[str, Any]:
        direct = bool(self._settings.saml_idp_sso_url and self._idp_certificate())
        metadata = bool(self._settings.saml_idp_metadata_url or self._settings.saml_idp_metadata_path)
        if not direct and not metadata:
            raise AuthenticationConfigurationError(
                "Ping requires an SSO URL and certificate, or an IdP metadata URL/path"
            )

        settings: dict[str, Any] = {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": self._settings.saml_sp_entity_id,
                "assertionConsumerService": {
                    "url": self._settings.saml_acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "x509cert": self._read_value(
                    self._settings.saml_sp_certificate,
                    self._settings.saml_sp_certificate_path,
                ),
                "privateKey": self._read_value(
                    self._settings.saml_sp_private_key,
                    self._settings.saml_sp_private_key_path,
                ),
            },
            "security": self._security_settings(),
        }
        if direct:
            settings["idp"] = {
                "entityId": self._settings.saml_expected_issuer,
                "singleSignOnService": {
                    "url": self._settings.saml_idp_sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": self._idp_certificate(),
            }
        elif self._settings.saml_idp_metadata_url:
            settings = OneLogin_Saml2_IdPMetadataParser.merge_settings(
                settings,
                OneLogin_Saml2_IdPMetadataParser.parse_remote(
                    self._settings.saml_idp_metadata_url,
                    validate_cert=True,
                ),
            )
        else:
            metadata_xml = Path(self._settings.saml_idp_metadata_path).read_text(encoding="utf-8")
            settings = OneLogin_Saml2_IdPMetadataParser.merge_settings(
                settings,
                OneLogin_Saml2_IdPMetadataParser.parse(metadata_xml),
            )
        metadata_issuer = settings.get("idp", {}).get("entityId")
        if metadata_issuer != self._settings.saml_expected_issuer:
            raise AuthenticationConfigurationError(
                "Ping metadata issuer does not match the configured expected issuer"
            )
        return settings

    def _security_settings(self) -> dict[str, Any]:
        profile = self._settings.saml_signature_profile.lower()
        if profile not in {"response", "assertion", "both"}:
            raise AuthenticationConfigurationError(
                "SAML signature profile must be response, assertion, or both"
            )
        has_sp_key = bool(
            self._read_value(
                self._settings.saml_sp_private_key,
                self._settings.saml_sp_private_key_path,
            )
        )
        return {
            "authnRequestsSigned": has_sp_key,
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "signMetadata": False,
            "wantMessagesSigned": profile in {"response", "both"},
            "wantAssertionsSigned": profile in {"assertion", "both"},
            "wantAssertionsEncrypted": False,
            "wantNameIdEncrypted": False,
            "wantNameId": True,
            "wantAttributeStatement": True,
            "requestedAuthnContext": True,
            "failOnAuthnContextMismatch": False,
            "allowSingleLabelDomains": False,
            "rejectUnsolicitedResponsesWithInResponseTo": True,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        }

    def _idp_certificate(self) -> str:
        return self._read_value(
            self._settings.saml_idp_certificate,
            self._settings.saml_idp_certificate_path,
        )

    @staticmethod
    def _read_value(inline: str, path: str) -> str:
        if inline:
            return inline.replace("\\n", "\n")
        if path:
            return Path(path).read_text(encoding="utf-8")
        return ""
