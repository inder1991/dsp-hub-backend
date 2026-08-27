from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DSP_", extra="ignore")

    app_name: str = "DSP Portal API"
    environment: str = "development"
    cors_origins: str = "http://localhost:5173"

    database_url: str = "postgresql+psycopg://dsp_portal:dsp_portal@127.0.0.1:5432/dsp_portal"
    frontend_base_url: str = "http://localhost:5173"

    jwt_issuer: str = "dsp-portal"
    jwt_audience: str = "dsp-portal-api"
    jwt_algorithm: str = "RS256"
    jwt_key_id: str = ""
    jwt_signing_key: str = ""
    jwt_signing_key_path: str = ""
    jwt_verification_key: str = ""
    jwt_verification_key_path: str = ""
    jwt_access_ttl_seconds: int = Field(default=600, ge=60, le=600)
    session_ttl_seconds: int = Field(default=28800, ge=300, le=28800)

    saml_sp_entity_id: str = ""
    saml_acs_url: str = ""
    saml_idp_sso_url: str = ""
    saml_expected_issuer: str = ""
    saml_idp_certificate: str = ""
    saml_idp_certificate_path: str = ""
    saml_idp_metadata_url: str = ""
    saml_idp_metadata_path: str = ""
    saml_signature_profile: str = "response"
    saml_durable_subject_attribute: str = "USER_ID"
    saml_groups_attribute: str = "LDAP_GROUPS"
    saml_email_attribute: str = "EMAIL"
    saml_given_name_attribute: str = "GIVEN_NAME"
    saml_family_name_attribute: str = "FAMILY_NAME"
    saml_employee_id_attribute: str = "EMPLOYEE_ID"
    saml_clock_skew_seconds: int = Field(default=60, ge=0, le=120)
    saml_sp_private_key: str = ""
    saml_sp_private_key_path: str = ""
    saml_sp_certificate: str = ""
    saml_sp_certificate_path: str = ""

    login_transaction_ttl_seconds: int = Field(default=300, ge=60, le=600)
    auth_code_ttl_seconds: int = Field(default=60, ge=30, le=60)
    local_password_action_ttl_seconds: int = Field(default=900, ge=300, le=3600)
    local_password_min_length: int = Field(default=12, ge=1, le=256)
    local_max_failures: int = Field(default=5, ge=3, le=20)
    local_lock_seconds: int = Field(default=900, ge=60, le=86400)
    auth_rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    local_auth_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)
    auth_cleanup_batch_size: int = Field(default=500, ge=10, le=10000)
    admin_reauth_seconds: int = Field(default=3600, ge=300, le=28800)
    auth_json_body_limit_bytes: int = Field(default=16384, ge=1024, le=1048576)
    saml_body_limit_bytes: int = Field(default=2097152, ge=65536, le=10485760)
    access_groups: str = ""
    admin_groups: str = ""
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_display_name: str = "DSP Local Administrator"
    preauth_support_url: str = ""

    confluence_dsp_url: str = ""
    confluence_status_url: str = ""
    confluence_releases_url: str = ""
    remedy_tickets_url: str = ""
    remedy_requests_url: str = ""
    teams_support_url: str = ""
    support_roster_name: str = "Alex Johnson"
    support_roster_role: str = "DSP support duty engineer"
    support_service_links: dict[str, dict[str, str]] = Field(default_factory=dict)
    onboarding_links: dict[str, str] = Field(default_factory=dict)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def admin_group_list(self) -> list[str]:
        return [group.strip() for group in self.admin_groups.split(",") if group.strip()]

    @property
    def access_group_list(self) -> list[str]:
        return [group.strip() for group in self.access_groups.split(",") if group.strip()]

    @property
    def approved_origin_list(self) -> list[str]:
        origins = [*self.cors_origin_list, self.frontend_base_url.rstrip("/")]
        return list(dict.fromkeys(origin for origin in origins if origin))

    @property
    def ping_configured(self) -> bool:
        required = (
            self.saml_sp_entity_id,
            self.saml_acs_url,
            self.saml_expected_issuer,
            bool(self.access_group_list),
        )
        direct_idp = bool(self.saml_idp_sso_url and self.saml_idp_certificate_value)
        metadata_idp = bool(self.saml_idp_metadata_url or self.saml_idp_metadata_path)
        return all(required) and (direct_idp or metadata_idp)

    @property
    def ping_configuration_started(self) -> bool:
        return any(
            (
                self.saml_sp_entity_id,
                self.saml_acs_url,
                self.saml_idp_sso_url,
                self.saml_expected_issuer,
                self.saml_idp_certificate,
                self.saml_idp_certificate_path,
                self.saml_idp_metadata_url,
                self.saml_idp_metadata_path,
                self.access_groups,
            )
        )

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        if not value.startswith(("RS", "PS", "ES")):
            raise ValueError("JWT algorithm must use an asymmetric key")
        return value

    @property
    def saml_idp_certificate_value(self) -> str:
        return self._secret_value(self.saml_idp_certificate, self.saml_idp_certificate_path)

    @property
    def jwt_signing_key_value(self) -> str:
        return self._secret_value(self.jwt_signing_key, self.jwt_signing_key_path)

    @property
    def jwt_verification_key_value(self) -> str:
        return self._secret_value(self.jwt_verification_key, self.jwt_verification_key_path)

    @staticmethod
    def _secret_value(inline: str, path: str) -> str:
        if inline:
            return inline.replace("\\n", "\n")
        if path:
            return Path(path).read_text(encoding="utf-8")
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
