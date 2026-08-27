from datetime import UTC, datetime

from app.core.config import Settings
from app.models.dashboard import (
    ActivityItem,
    DashboardResponse,
    ExternalLinks,
    HealthService,
    HealthSummary,
    IncidentSummary,
    Metric,
    MyDspSummary,
    ResourceItem,
    SystemStatus,
    UpcomingChange,
)
from app.services.devspaces import DevspaceInventoryService
from app.services.observability import ObservabilityService


def _append_path(base_url: str, path: str) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


class DashboardService:
    """Phase-one static adapter matching the future integration contract."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def health_summary(self) -> HealthSummary:
        return HealthSummary(
            state="degraded",
            label="DEGRADED",
            affected_systems=2,
            services=[
                HealthService(
                    id="hadoop",
                    name="Hadoop",
                    state="degraded",
                    status="Degraded",
                    summary="Elevated latency",
                ),
                HealthService(
                    id="trino",
                    name="Trino",
                    state="degraded",
                    status="Degraded",
                    summary="Query performance degraded",
                ),
                HealthService(id="nexus", name="Nexus", state="operational", status="Operational"),
                HealthService(
                    id="vm-platform", name="VM Platform", state="operational", status="Operational"
                ),
                HealthService(id="github", name="GitHub", state="operational", status="Operational"),
            ],
        )

    def dashboard(self, owner_keys: frozenset[str] | None = None) -> DashboardResponse:
        links = ExternalLinks(
            confluence_dsp=self.settings.confluence_dsp_url or None,
            confluence_status=self.settings.confluence_status_url or None,
            confluence_releases=self.settings.confluence_releases_url or None,
            remedy_tickets=self.settings.remedy_tickets_url or None,
            remedy_requests=self.settings.remedy_requests_url or None,
        )
        systems = [
            SystemStatus(
                id="vm-platform",
                name="VM Platform",
                state="operational",
                status="Operational",
                details_url=_append_path(self.settings.confluence_dsp_url, "systems/vm-platform"),
            ),
            SystemStatus(
                id="hadoop",
                name="Hadoop",
                state="degraded",
                status="Degraded",
                summary="Elevated latency",
                details_url=_append_path(self.settings.confluence_dsp_url, "systems/hadoop"),
            ),
            SystemStatus(
                id="trino",
                name="Trino",
                state="degraded",
                status="Degraded",
                summary="Query performance",
                details_url=_append_path(self.settings.confluence_dsp_url, "systems/trino"),
            ),
            SystemStatus(
                id="nexus",
                name="Nexus",
                state="operational",
                status="Operational",
                details_url=_append_path(self.settings.confluence_dsp_url, "systems/nexus"),
            ),
            SystemStatus(
                id="github-actions",
                name="GitHub Actions",
                state="operational",
                status="Operational",
                details_url=_append_path(self.settings.confluence_dsp_url, "systems/github-actions"),
            ),
        ]

        resources = [
            (
                "alex-morgan",
                ResourceItem(
                    id="analytics-dev",
                    name="analytics-dev",
                    type="Workspace",
                    state="running",
                    status="Running",
                ),
            ),
            (
                "priya-nair",
                ResourceItem(
                    id="model-training",
                    name="model-training",
                    type="Job",
                    state="completed",
                    status="Completed",
                ),
            ),
            (
                "priya-nair",
                ResourceItem(
                    id="customer-model",
                    name="customer-model",
                    type="Job",
                    state="needs_attention",
                    status="Needs attention",
                ),
            ),
            (
                "daniel-lee",
                ResourceItem(
                    id="data-observability",
                    name="data-observability",
                    type="Monitor",
                    state="healthy",
                    status="Healthy",
                ),
            ),
        ]
        activity = [
            (
                "priya-nair",
                ActivityItem(
                    id="build-182",
                    name="customer-model",
                    activity="Build #182",
                    state="completed",
                    status="Passed",
                    occurred_at="1h ago",
                ),
            ),
            (
                "alex-morgan",
                ActivityItem(
                    id="workspace-analytics-dev",
                    name="analytics-dev",
                    activity="Workspace",
                    state="running",
                    status="Running",
                    occurred_at="2h ago",
                ),
            ),
            (
                "omar-hassan",
                ActivityItem(
                    id="commit-8f21a",
                    name="risk-model",
                    activity="Commit 8f21a",
                    state="informational",
                    status="2h ago",
                    occurred_at="2h ago",
                ),
            ),
            (
                "platform",
                ActivityItem(
                    id="image-python-311",
                    name="python-3.11-image",
                    activity="Released",
                    state="informational",
                    status="Yesterday",
                    occurred_at="Yesterday",
                ),
            ),
        ]
        visible_resources = [item for owner, item in resources if owner_keys is None or owner in owner_keys]
        visible_activity = [
            item
            for owner, item in activity
            if owner_keys is None or owner in owner_keys or owner == "platform"
        ]
        inventory = DevspaceInventoryService().inventory_for(owner_keys)
        job_data = ObservabilityService(owner_keys).jobs()

        return DashboardResponse(
            generated_at=datetime.now(UTC),
            health=self.health_summary(),
            systems=systems,
            incident=IncidentSummary(
                message="Hadoop and Trino are experiencing elevated latency.",
                url=self.settings.confluence_status_url or None,
            ),
            my_dsp=MyDspSummary(
                metrics=[
                    Metric(value=12 if owner_keys is None else job_data.summary.total_24h, label="Jobs"),
                    Metric(
                        value=3 if owner_keys is None else inventory.summary.total,
                        label="Workspaces",
                    ),
                    Metric(
                        value=2 if owner_keys is None else inventory.summary.needs_attention,
                        label="Warnings",
                    ),
                    Metric(value=1 if owner_keys is None else job_data.summary.failed, label="Failed"),
                ],
                active_resources=visible_resources,
            ),
            recent_activity=visible_activity,
            upcoming_changes=[
                UpcomingChange(
                    id="vm-maintenance",
                    date_label="Sep 02",
                    title="VM maintenance",
                    impact=(
                        "Affects 2 of your workspaces"
                        if owner_keys is None
                        else f"Affects {inventory.summary.total} of your workspaces"
                    ),
                    state="needs_attention",
                    status="Impact",
                    url=self.settings.confluence_releases_url or None,
                ),
                UpcomingChange(
                    id="python-image-upgrade",
                    date_label="Sep 04",
                    title="Python image upgrade",
                    impact="Action required",
                    state="action_required",
                    status="Action required",
                    url=self.settings.confluence_releases_url or None,
                ),
                UpcomingChange(
                    id="hadoop-maintenance",
                    date_label="Sep 12",
                    title="Hadoop maintenance",
                    impact="No action required",
                    state="no_action",
                    status="No action",
                    url=self.settings.confluence_releases_url or None,
                ),
            ],
            external_links=links,
        )
