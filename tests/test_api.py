from fastapi.testclient import TestClient

from app.auth.dependencies import ResourceScope, get_current_principal, get_resource_scope, require_admin
from app.auth.schemas import TokenPrincipal
from app.core.config import Settings
from app.main import app
from app.services.support import SupportCatalogService


def _authenticated_admin() -> TokenPrincipal:
    return TokenPrincipal(
        id="test-admin",
        role="ADMIN",
        authentication_provider="LOCAL",
        authorization_version=1,
        session_id="test-session",
    )


app.dependency_overrides[get_current_principal] = _authenticated_admin
app.dependency_overrides[require_admin] = _authenticated_admin
client = TestClient(app)


def test_service_health() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_portal_endpoints_reject_anonymous_requests() -> None:
    app.dependency_overrides.pop(get_current_principal)
    try:
        response = client.get("/api/v1/home")
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_principal] = _authenticated_admin


def test_home_dashboard_contract_is_camel_case() -> None:
    response = client.get("/api/v1/home")

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["label"] == "DEGRADED"
    assert payload["health"]["affectedSystems"] == 2
    assert len(payload["systems"]) == 5
    assert payload["systems"][4]["name"] == "GitHub Actions"
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


def test_devspace_inventory_exposes_user_vm_and_runtime_health() -> None:
    response = client.get("/api/v1/devspaces")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 7,
        "active": 6,
        "healthy": 4,
        "needsAttention": 2,
        "stopped": 1,
    }
    assert payload["fleet"]["vmCount"] == 4
    assert payload["fleet"]["atRiskVms"] == 1
    assert payload["fleet"]["storagePercentage"] == 54
    assert len(payload["vmIssues"]) == 10
    assert payload["vmIssues"][0]["status"] == "active"
    analytics = payload["devspaces"][0]
    assert analytics["owner"]["name"] == "Alex Morgan"
    assert analytics["vm"]["name"] == "dsp-vm-021"
    assert analytics["cpu"]["percentage"] == 18
    assert analytics["connections"][0]["name"] == "Nexus"


def test_kedro_jobs_link_to_devspaces_vms_and_users() -> None:
    response = client.get("/api/v1/jobs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["running"] == 2
    assert payload["summary"]["failed"] == 2
    running = payload["jobs"][0]
    assert running["pipeline"] == "model_training"
    assert running["devspaceId"] == "customer-model"
    assert running["vmId"] == "vm-021"
    assert running["owner"]["name"] == "Priya Nair"


def test_devspace_detail_correlates_jobs_processes_and_metrics() -> None:
    response = client.get("/api/v1/devspaces/customer-model")

    assert response.status_code == 200
    payload = response.json()
    assert payload["devspace"]["image"] == "python-3.11-dsp:2026.08"
    assert payload["jobs"][0]["state"] == "running"
    assert payload["processes"][0]["category"] == "kedro"
    assert {metric["id"] for metric in payload["metrics"]} == {"cpu", "memory", "disk"}


def test_vm_detail_correlates_hosted_devspaces_users_and_issues() -> None:
    response = client.get("/api/v1/vms/vm-021")

    assert response.status_code == 200
    payload = response.json()
    assert payload["vm"]["name"] == "dsp-vm-021"
    assert {item["id"] for item in payload["devspaces"]} == {"analytics-dev", "customer-model"}
    assert {user["name"] for user in payload["users"]} == {"Alex Morgan", "Priya Nair"}
    assert payload["issues"][0]["status"] == "active"
    assert payload["topProcesses"][0]["devspaceId"] == "customer-model"


def test_vm_inventory_exposes_host_capacity_workloads_and_drilldown_context() -> None:
    response = client.get("/api/v1/vms")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 4,
        "online": 4,
        "healthy": 2,
        "attention": 1,
        "critical": 1,
        "devspaces": 7,
        "users": 7,
        "activeJobs": 3,
        "activeIssues": 3,
    }
    analytics = payload["vms"][0]
    assert analytics["vm"]["id"] == "vm-021"
    assert analytics["devspaceCount"] == 2
    assert analytics["userCount"] == 2
    assert analytics["activeJobs"] == 2
    assert analytics["cpu"]["percentage"] == 52


def test_observability_detail_returns_not_found_for_unknown_resources() -> None:
    assert client.get("/api/v1/devspaces/missing").status_code == 404
    assert client.get("/api/v1/vms/missing").status_code == 404


def test_read_only_resource_scope_hides_other_users_devspaces_jobs_and_vm_workloads() -> None:
    app.dependency_overrides[get_resource_scope] = lambda: ResourceScope(
        is_admin=False,
        owner_keys=frozenset({"alex-morgan"}),
    )
    try:
        devspaces = client.get("/api/v1/devspaces")
        jobs = client.get("/api/v1/jobs")
        vm = client.get("/api/v1/vms/vm-021")

        assert [item["id"] for item in devspaces.json()["devspaces"]] == ["analytics-dev"]
        assert {item["owner"]["id"] for item in jobs.json()["jobs"]} == {"alex-morgan"}
        assert [item["id"] for item in vm.json()["devspaces"]] == ["analytics-dev"]
        assert client.get("/api/v1/devspaces/customer-model").status_code == 404
        assert client.get("/api/v1/vms/vm-041").status_code == 404
    finally:
        app.dependency_overrides.pop(get_resource_scope)


def test_unmapped_read_only_user_does_not_receive_another_users_home_or_data_entitlements() -> None:
    app.dependency_overrides[get_resource_scope] = lambda: ResourceScope(
        is_admin=False,
        owner_keys=frozenset({"unmapped-reader"}),
    )
    try:
        homepage = client.get("/api/v1/home").json()
        data_access = client.get("/api/v1/data-access").json()

        assert homepage["myDsp"]["activeResources"] == []
        assert homepage["myDsp"]["metrics"] == [
            {"label": "Jobs", "value": 0},
            {"label": "Workspaces", "value": 0},
            {"label": "Warnings", "value": 0},
            {"label": "Failed", "value": 0},
        ]
        assert data_access["tables"] == []
        assert data_access["yarnQueues"] == []
        assert data_access["summary"]["accessibleTables"] == 0
    finally:
        app.dependency_overrides.pop(get_resource_scope)


def test_user_data_access_exposes_entitlements_ingestion_and_team_queues_only() -> None:
    response = client.get("/api/v1/data-access")

    assert response.status_code == 200
    payload = response.json()
    assert payload["principal"]["enterpriseUserId"] == "alex.morgan"
    assert payload["principal"]["team"] == "Customer Analytics"
    assert payload["summary"]["accessibleTables"] == 8
    assert payload["tables"][0]["fullyQualifiedName"] == "customer.customer_features"
    assert payload["tables"][0]["access"]["ldapGroup"] == "DSP-CUSTOMER-ANALYTICS"
    assert payload["tables"][0]["ingestion"]["businessDate"] == "26 Aug 2026"
    assert {queue["team"] for queue in payload["yarnQueues"]} == {"Customer Analytics"}

    serialized = response.text.lower()
    for forbidden in ("sampledata", "sample_data", "datarows", "data_rows", "rowvalues", "row_values"):
        assert forbidden not in serialized


def test_admin_control_plane_correlates_teams_ldap_ingestion_and_yarn() -> None:
    response = client.get("/api/v1/admin/control-plane")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["totalVms"] == 18
    assert payload["summary"]["pendingApprovals"] == 3
    assert payload["hiveTables"][0]["ldapGroups"] == ["DSP-CUSTOMER-ANALYTICS"]
    assert payload["hiveTables"][0]["ingestion"]["status"] == "succeeded"
    assert {queue["team"] for queue in payload["yarnQueues"]} >= {
        "Customer Analytics",
        "Risk Modelling",
        "Finance Insights",
    }
    assert payload["allocations"][0]["status"] == "pending_approval"
    assert payload["capabilities"] == {
        "readOnlyPreview": True,
        "allocationWorkflowEnabled": False,
        "contentWorkflowEnabled": False,
        "requiresEnterpriseSso": True,
    }
