from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.dashboard import ApiModel
from app.models.devspaces import (
    Devspace,
    DevspaceOwner,
    HostVm,
    ResourceUtilization,
    VmIssue,
)

JobState = Literal["running", "succeeded", "failed", "queued", "cancelled"]
ProcessState = Literal["running", "sleeping", "waiting", "stopped"]


class KedroJobRun(ApiModel):
    id: str
    name: str
    pipeline: str
    project: str
    devspace_id: str
    devspace_name: str
    vm_id: str
    vm_name: str
    owner: DevspaceOwner
    state: JobState
    status: str
    started_at: str
    duration: str
    progress_percentage: int = Field(ge=0, le=100)
    nodes_completed: int = Field(ge=0)
    nodes_total: int = Field(gt=0)
    current_node: str
    trigger: str
    cpu_peak_percentage: int = Field(ge=0, le=100)
    memory_peak_gb: float = Field(ge=0)
    last_message: str
    failed_node: str | None = None


class JobSummary(ApiModel):
    total_24h: int = Field(ge=0)
    running: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    queued: int = Field(ge=0)
    success_rate: int = Field(ge=0, le=100)


class JobsResponse(ApiModel):
    generated_at: datetime
    summary: JobSummary
    jobs: list[KedroJobRun]


class DevspaceProcess(ApiModel):
    pid: int = Field(gt=0)
    name: str
    command: str
    category: Literal["kedro", "editor", "notebook", "system"]
    state: ProcessState
    status: str
    cpu_percentage: float = Field(ge=0, le=100)
    memory_percentage: float = Field(ge=0, le=100)
    running_age: str
    job_id: str | None = None
    devspace_id: str | None = None


class MetricSeries(ApiModel):
    id: Literal["cpu", "memory", "disk"]
    label: str
    resource: ResourceUtilization
    window: str
    samples: list[int]


class DevspaceDetailResponse(ApiModel):
    generated_at: datetime
    devspace: Devspace
    metrics: list[MetricSeries]
    jobs: list[KedroJobRun]
    processes: list[DevspaceProcess]
    vm_issues: list[VmIssue]


class VmFacts(ApiModel):
    operating_system: str
    kernel: str
    container_runtime: str
    environment: str
    running_age: str
    last_patch: str
    load_average: str


class VmInventoryItem(ApiModel):
    vm: HostVm
    state: Literal["healthy", "attention", "critical"]
    status: str
    status_detail: str
    environment: str
    running_age: str
    cpu: ResourceUtilization
    memory: ResourceUtilization
    disk: ResourceUtilization
    devspace_count: int = Field(ge=0)
    active_devspaces: int = Field(ge=0)
    user_count: int = Field(ge=0)
    users: list[DevspaceOwner]
    active_jobs: int = Field(ge=0)
    active_issue_count: int = Field(ge=0)
    last_event: str


class VmInventorySummary(ApiModel):
    total: int = Field(ge=0)
    online: int = Field(ge=0)
    healthy: int = Field(ge=0)
    attention: int = Field(ge=0)
    critical: int = Field(ge=0)
    devspaces: int = Field(ge=0)
    users: int = Field(ge=0)
    active_jobs: int = Field(ge=0)
    active_issues: int = Field(ge=0)


class VmInventoryResponse(ApiModel):
    generated_at: datetime
    summary: VmInventorySummary
    vms: list[VmInventoryItem]


class VmDetailResponse(ApiModel):
    generated_at: datetime
    vm: HostVm
    state: Literal["healthy", "attention", "critical"]
    status: str
    status_detail: str
    facts: VmFacts
    cpu: ResourceUtilization
    memory: ResourceUtilization
    disk: ResourceUtilization
    devspaces: list[Devspace]
    users: list[DevspaceOwner]
    issues: list[VmIssue]
    top_processes: list[DevspaceProcess]
