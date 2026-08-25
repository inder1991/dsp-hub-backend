from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.services.support import SupportCatalogService

client = TestClient(app)


def test_service_health() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_home_dashboard_contract_is_camel_case() -> None:
    response = client.get("/api/v1/home")

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["label"] == "DEGRADED"
    assert payload["health"]["affectedSystems"] == 2
    assert len(payload["systems"]) == 5
    assert payload["myDsp"]["activeResources"][0]["name"] == "analytics-dev"
    assert payload["upcomingChanges"][1]["status"] == "Action required"


def test_health_summary_matches_homepage_attention_signal() -> None:
    response = client.get("/api/v1/health/summary")

    assert response.status_code == 200
    payload = response.json()
    degraded = [service for service in payload["services"] if service["state"] == "degraded"]
    assert payload["affectedSystems"] == len(degraded)
    assert {service["name"] for service in degraded} == {"Hadoop", "Trino"}


def test_support_catalog_is_read_only_and_service_specific() -> None:
    response = client.get("/api/v1/support")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dspSupport"]["role"] == "DSP support duty engineer"
    assert len(payload["services"]) == 7
    assert payload["services"][0]["name"] == "Dev container"
    cyberark = next(service for service in payload["services"] if service["id"] == "cyberark")
    assert cyberark["specialist"]["name"] == "Omar Rahman"
    assert cyberark["issues"][0]["title"] == "CyberArk session is unavailable"
    assert cyberark["issues"][0]["guideUrl"] == "#guide/cyberark/session-unavailable"
    assert "checks" not in payload


def test_support_links_can_be_overridden_per_service() -> None:
    settings = Settings(
        support_service_links={
            "cyberark": {
                "remedyUrl": "https://remedy.example/cyberark",
                "confluenceUrl": "https://confluence.example/cyberark",
                "teamsUrl": "https://teams.example/cyberark",
            }
        }
    )

    catalog = SupportCatalogService(settings).catalog()
    cyberark = next(service for service in catalog.services if service.id == "cyberark")
    assert cyberark.remedy_url == "https://remedy.example/cyberark"
    assert cyberark.specialist.teams_url == "https://teams.example/cyberark"
    assert cyberark.issues[0].guide_url == "https://confluence.example/cyberark/session-unavailable"


def test_onboarding_catalog_omits_target_and_executable_checks() -> None:
    response = client.get("/api/v1/onboarding")

    assert response.status_code == 200
    payload = response.json()
    assert payload["completedSteps"] == 2
    assert payload["totalSteps"] == 5
    assert payload["bootcamp"]["dateLabel"] == "Sep 15–16, 2026"
    serialized = response.text.lower()
    assert "target 300" not in serialized
    assert "run check" not in serialized
