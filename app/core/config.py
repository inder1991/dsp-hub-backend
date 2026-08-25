from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DSP_", extra="ignore")

    app_name: str = "DSP Portal API"
    environment: str = "development"
    cors_origins: str = "http://localhost:5173"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
