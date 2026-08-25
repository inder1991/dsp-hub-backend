from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from app.models.dashboard import ApiModel

OnboardingState = Literal["complete", "current", "upcoming"]
RequirementState = Literal["complete", "pending", "optional"]


class OnboardingStep(ApiModel):
    id: str
    number: int = Field(ge=1)
    title: str
    state: OnboardingState


class SetupTask(ApiModel):
    id: str
    title: str
    description: str
    state: Literal["complete", "next", "optional"]
    guide_url: Optional[str] = None


class AccessRequirement(ApiModel):
    id: str
    label: str
    state: RequirementState


class BootcampSession(ApiModel):
    title: str
    date_label: str
    format: str
    availability: str
    agenda_url: Optional[str] = None
    register_url: Optional[str] = None


class TrainingVideo(ApiModel):
    id: str
    title: str
    duration: str
    url: Optional[str] = None


class CohortStage(ApiModel):
    id: str
    label: str
    status: str
    state: Literal["complete", "current", "upcoming"]


class OnboardingLinks(ApiModel):
    access_matrix_url: Optional[str] = None
    setup_guide_url: Optional[str] = None
    troubleshooting_url: str = "#support"
    support_teams_url: Optional[str] = None
    training_library_url: Optional[str] = None


class OnboardingResponse(ApiModel):
    generated_at: datetime
    completed_steps: int = Field(ge=0)
    total_steps: int = Field(ge=1)
    steps: list[OnboardingStep]
    current_step_title: str
    tasks: list[SetupTask]
    benefits: list[str]
    access_requirements: list[AccessRequirement]
    bootcamp: BootcampSession
    training_videos: list[TrainingVideo]
    cohort_stages: list[CohortStage]
    links: OnboardingLinks
