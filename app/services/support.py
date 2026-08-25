from datetime import datetime, timezone
from typing import Optional

from app.core.config import Settings
from app.models.support import (
    SupportIssue,
    SupportResponse,
    SupportServiceItem,
    SupportSpecialist,
)


def _append_path(base_url: str, path: str) -> Optional[str]:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


SERVICE_CATALOG = [
    (
        "dev-container",
        "Dev container",
        "Workspace startup, image build, and local package issues.",
        "Aisha Khan",
        "DSP workspace support",
        [
            (
                "container-wont-start",
                "Dev container will not start",
                "Recover a workspace that stops during startup.",
                6,
            ),
            (
                "container-build-fails",
                "Dev container build fails",
                "Review common image and configuration failures.",
                8,
            ),
            (
                "python-package-missing",
                "Python package is missing",
                "Confirm the approved package source and image version.",
                5,
            ),
        ],
    ),
    (
        "cyberark",
        "CyberArk",
        "Credential retrieval, session, and target connection issues.",
        "Omar Rahman",
        "CyberArk on-call",
        [
            (
                "session-unavailable",
                "CyberArk session is unavailable",
                "Restart the session and validate the target account mapping.",
                5,
            ),
            (
                "credential-expired",
                "Credential has expired",
                "Confirm rotation status and request credential reconciliation.",
                7,
            ),
            (
                "target-denied",
                "Target connection is denied",
                "Validate safe membership, platform policy, and target access.",
                8,
            ),
        ],
    ),
    (
        "nexus",
        "Nexus",
        "Approved Python packages, container images, and repository access.",
        "Priya Nair",
        "Nexus on-call",
        [
            (
                "package-unavailable",
                "Python package unavailable in Nexus",
                "Check the approved repository and package onboarding status.",
                6,
            ),
            (
                "pip-authentication",
                "Pip authentication failed",
                "Refresh repository credentials and validate pip configuration.",
                5,
            ),
            (
                "image-pull-fails",
                "Container image pull fails",
                "Confirm repository path, image tag, and network access.",
                7,
            ),
        ],
    ),
    (
        "compute",
        "Compute",
        "DSP VM availability, capacity, disk, and memory issues.",
        "Daniel Lewis",
        "Compute on-call",
        [
            (
                "workspace-unreachable",
                "Workspace or VM is unreachable",
                "Check maintenance status, network path, and VM state.",
                7,
            ),
            (
                "out-of-memory",
                "Workload stopped due to memory",
                "Identify memory pressure and right-size the workload.",
                8,
            ),
            (
                "disk-full",
                "Workspace disk is full",
                "Locate safe cleanup targets and request capacity if needed.",
                8,
            ),
        ],
    ),
    (
        "cdp",
        "CDP",
        "Data access, Kerberos, permission, and dataset visibility issues.",
        "Fatima Ali",
        "CDP on-call",
        [
            (
                "permission-denied",
                "CDP permission denied",
                "Confirm entitlement, role mapping, and dataset policy.",
                7,
            ),
            (
                "kerberos-expired",
                "Kerberos ticket expired",
                "Renew the ticket and confirm the configured principal.",
                5,
            ),
            (
                "dataset-not-visible",
                "Dataset is not visible",
                "Validate the database, schema, and granted access.",
                6,
            ),
        ],
    ),
    (
        "trino",
        "Trino",
        "Query connection, catalogue availability, and performance issues.",
        "Rohan Mehta",
        "Trino on-call",
        [
            (
                "connection-denied",
                "Trino connection denied",
                "Validate the endpoint, credentials, and network route.",
                6,
            ),
            (
                "query-slow",
                "Trino query is slow",
                "Review partition filters, query shape, and current service status.",
                9,
            ),
            (
                "catalogue-unavailable",
                "Trino catalogue is unavailable",
                "Check catalogue status and the upstream data platform.",
                7,
            ),
        ],
    ),
    (
        "sas",
        "SAS",
        "SAS connectivity, libraries, and data transfer issues.",
        "Maya Thomas",
        "SAS on-call",
        [
            (
                "connection-failed",
                "SAS connection failed",
                "Validate the connection profile and network access.",
                6,
            ),
            (
                "library-unavailable",
                "SAS library is unavailable",
                "Confirm library assignment and permissions.",
                7,
            ),
            (
                "export-failed",
                "Export to SAS failed",
                "Review data types, target location, and transfer limits.",
                8,
            ),
        ],
    ),
]


class SupportCatalogService:
    """Release-one read-only guide and escalation directory."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def catalog(self) -> SupportResponse:
        services = []
        for service_id, name, description, specialist_name, role, issues in SERVICE_CATALOG:
            service_links = self.settings.support_service_links.get(service_id, {})
            confluence_url = service_links.get("confluenceUrl")
            services.append(
                SupportServiceItem(
                    id=service_id,
                    name=name,
                    description=description,
                    remedy_url=(service_links.get("remedyUrl") or self.settings.remedy_requests_url or None),
                    specialist=SupportSpecialist(
                        name=specialist_name,
                        role=role,
                        roster_status="available",
                        teams_url=service_links.get("teamsUrl") or None,
                    ),
                    issues=[
                        SupportIssue(
                            id=issue_id,
                            title=title,
                            description=issue_description,
                            estimated_minutes=estimated_minutes,
                            guide_url=(
                                _append_path(confluence_url, issue_id)
                                if confluence_url
                                else (
                                    "#guide/cyberark/session-unavailable"
                                    if service_id == "cyberark" and issue_id == "session-unavailable"
                                    else _append_path(
                                        self.settings.confluence_dsp_url,
                                        f"troubleshooting/{service_id}/{issue_id}",
                                    )
                                )
                            ),
                        )
                        for issue_id, title, issue_description, estimated_minutes in issues
                    ],
                )
            )
        return SupportResponse(
            generated_at=datetime.now(timezone.utc),
            dsp_support=SupportSpecialist(
                name=self.settings.support_roster_name,
                role=self.settings.support_roster_role,
                roster_status="available",
                teams_url=self.settings.teams_support_url or None,
            ),
            services=services,
        )
