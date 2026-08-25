from datetime import datetime, timezone
from typing import Optional

from app.core.config import Settings
from app.models.onboarding import (
    AccessRequirement,
    BootcampSession,
    CohortStage,
    OnboardingLinks,
    OnboardingResponse,
    OnboardingStep,
    SetupTask,
    TrainingVideo,
)


def _append_path(base_url: str, path: str) -> Optional[str]:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


class OnboardingCatalogService:
    """Release-one onboarding journey, learning catalog, and configurable links."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def catalog(self) -> OnboardingResponse:
        configured = self.settings.onboarding_links

        def link(key: str, fallback_path: str) -> Optional[str]:
            return configured.get(key) or _append_path(self.settings.confluence_dsp_url, fallback_path)

        return OnboardingResponse(
            generated_at=datetime.now(timezone.utc),
            completed_steps=2,
            total_steps=5,
            steps=[
                OnboardingStep(id="request-access", number=1, title="Request access", state="complete"),
                OnboardingStep(id="cyberark", number=2, title="Set up CyberArk", state="complete"),
                OnboardingStep(id="dev-container", number=3, title="Prepare dev container", state="current"),
                OnboardingStep(id="data-sources", number=4, title="Connect data sources", state="upcoming"),
                OnboardingStep(id="training", number=5, title="Complete training", state="upcoming"),
            ],
            current_step_title="Step 3 — Prepare your dev container",
            tasks=[
                SetupTask(
                    id="nexus-access",
                    title="Verify Nexus package access",
                    description="Confirm the approved repositories available to your workspace.",
                    state="next",
                    guide_url=link("nexusGuideUrl", "onboarding/nexus-access"),
                ),
                SetupTask(
                    id="python-environment",
                    title="Choose an approved Python environment",
                    description="Select the DSP base image that matches your workload.",
                    state="next",
                    guide_url=link("pythonGuideUrl", "onboarding/python-environment"),
                ),
                SetupTask(
                    id="compute-workspace",
                    title="Prepare your compute workspace",
                    description="Follow the workspace launch and dev-container setup guide.",
                    state="next",
                    guide_url=link("workspaceGuideUrl", "onboarding/compute-workspace"),
                ),
                SetupTask(
                    id="data-connections",
                    title="Connect CDP, Trino, and SAS",
                    description="Use the approved connection patterns for required data services.",
                    state="optional",
                    guide_url=link("dataGuideUrl", "onboarding/data-connections"),
                ),
            ],
            benefits=[
                "Managed dev container",
                "Approved Python packages",
                "Secure enterprise credentials",
                "Access to CDP, Trino, and SAS",
            ],
            access_requirements=[
                AccessRequirement(id="manager-approval", label="Manager approval", state="complete"),
                AccessRequirement(id="dsp-user-group", label="DSP user group", state="complete"),
                AccessRequirement(id="cyberark-account", label="CyberArk account", state="complete"),
                AccessRequirement(id="cdp-access", label="CDP access", state="pending"),
                AccessRequirement(id="trino-access", label="Trino access", state="pending"),
                AccessRequirement(id="sas-access", label="SAS access", state="optional"),
            ],
            bootcamp=BootcampSession(
                title="DSP Bootcamp — September cohort",
                date_label="Sep 15–16, 2026",
                format="2-day virtual session",
                availability="Seats available",
                agenda_url=configured.get("bootcampAgendaUrl"),
                register_url=configured.get("bootcampRegisterUrl"),
            ),
            training_videos=[
                TrainingVideo(
                    id="platform-overview",
                    title="DSP platform overview",
                    duration="12 min",
                    url=link("platformVideoUrl", "training/platform-overview"),
                ),
                TrainingVideo(
                    id="dev-container",
                    title="Working in your dev container",
                    duration="18 min",
                    url=link("containerVideoUrl", "training/dev-container"),
                ),
                TrainingVideo(
                    id="data-connections",
                    title="Connecting to CDP and Trino",
                    duration="22 min",
                    url=link("dataVideoUrl", "training/data-connections"),
                ),
                TrainingVideo(
                    id="model-standards",
                    title="Model development standards",
                    duration="16 min",
                    url=link("standardsVideoUrl", "training/model-standards"),
                ),
            ],
            cohort_stages=[
                CohortStage(id="invited", label="Invited", status="Invitations underway", state="complete"),
                CohortStage(
                    id="approved", label="Access approved", status="Approvals in progress", state="current"
                ),
                CohortStage(
                    id="workspace", label="Workspace ready", status="Workspace setup active", state="upcoming"
                ),
                CohortStage(
                    id="trained", label="Training complete", status="Training underway", state="upcoming"
                ),
            ],
            links=OnboardingLinks(
                access_matrix_url=configured.get("accessMatrixUrl"),
                setup_guide_url=link("setupGuideUrl", "onboarding/getting-started"),
                support_teams_url=self.settings.teams_support_url or None,
                training_library_url=configured.get("trainingLibraryUrl"),
            ),
        )
