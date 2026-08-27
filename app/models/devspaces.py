from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.dashboard import ApiModel

DevspaceState = Literal["healthy", "attention", "critical", "stopped"]
ConnectionState = Literal["connected", "degraded", "not_configured"]


class DevspaceOwner(ApiModel):
    id: str
    name: str
    initials: str
    team: str


class HostVm(ApiModel):
    id: str
    name: str
    tenant: str
    host_group: str


class ResourceUtilization(ApiModel):
    used: float = Field(ge=0)
    limit: float = Field(gt=0)
    unit: str
    percentage: int = Field(ge=0, le=100)


class DevspaceConnection(ApiModel):
    name: str
    state: ConnectionState
    status: str


class Devspace(ApiModel):
    id: str
    name: str
    kind: Literal["Devspace", "Dev container"]
    owner: DevspaceOwner
    vm: HostVm
    state: DevspaceState
    status: str
    status_detail: str
    cpu: ResourceUtilization
    memory: ResourceUtilization
    disk: ResourceUtilization
    uptime: str
    last_activity: str
    image: str
    python_version: str
    restart_count: int = Field(ge=0)
    connections: list[DevspaceConnection]


class DevspaceSummary(ApiModel):
    total: int = Field(ge=0)
    active: int = Field(ge=0)
    healthy: int = Field(ge=0)
    needs_attention: int = Field(ge=0)
    stopped: int = Field(ge=0)


class FleetCapacity(ApiModel):
    vm_count: int = Field(ge=0)
    online_vms: int = Field(ge=0)
    cpu_percentage: int = Field(ge=0, le=100)
    memory_percentage: int = Field(ge=0, le=100)
    storage_percentage: int = Field(ge=0, le=100)
    at_risk_vms: int = Field(ge=0)


class VmIssue(ApiModel):
    id: str
    vm_id: str
    title: str
    summary: str
    severity: Literal["critical", "warning", "informational"]
    status: Literal["active", "resolved"]
    occurred_at: str
    resolved_at: str | None = None
    affected_devspaces: int = Field(ge=0)


class DevspacesResponse(ApiModel):
    generated_at: datetime
    summary: DevspaceSummary
    fleet: FleetCapacity
    devspaces: list[Devspace]
    vm_issues: list[VmIssue] = Field(max_length=10)
