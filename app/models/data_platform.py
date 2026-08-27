from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.dashboard import ApiModel

IngestionState = Literal["succeeded", "late", "failed", "pending", "not_received"]
QueueState = Literal["healthy", "attention", "critical"]
AdminSeverity = Literal["information", "warning", "critical"]


class PortalPrincipal(ApiModel):
    id: str
    enterprise_user_id: str
    name: str
    team: str
    ldap_groups: list[str]


class AccessPath(ApiModel):
    ldap_group: str
    team: str
    privilege: str
    policy_name: str


class MorningIngestionStatus(ApiModel):
    business_date: str
    status: IngestionState
    status_label: str
    scheduled_for: str
    completed_at: str | None = None
    last_successful_business_date: str | None = None
    sla_state: Literal["within_sla", "at_risk", "breached", "awaiting"]
    summary: str


class AccessibleHiveTable(ApiModel):
    id: str
    database: str
    table: str
    fully_qualified_name: str
    platform: Literal["Hive"] = "Hive"
    owner_team: str
    access: AccessPath
    ingestion: MorningIngestionStatus


class YarnQueueStatus(ApiModel):
    id: str
    queue_path: str
    team: str
    ldap_group: str
    state: QueueState
    status: str
    used_capacity_percentage: int = Field(ge=0)
    configured_capacity_percentage: int = Field(ge=0)
    running_applications: int = Field(ge=0)
    pending_applications: int = Field(ge=0)
    allocated_memory_gb: int = Field(ge=0)
    pending_memory_gb: int = Field(ge=0)
    observed_at: str


class DataAccessSummary(ApiModel):
    accessible_tables: int = Field(ge=0)
    ingested: int = Field(ge=0)
    late: int = Field(ge=0)
    failed: int = Field(ge=0)
    pending: int = Field(ge=0)
    business_date: str


class SourceFreshness(ApiModel):
    source: str
    status: Literal["current", "stale", "unavailable"]
    last_synced_at: str
    summary: str


class UserDataAccessResponse(ApiModel):
    generated_at: datetime
    principal: PortalPrincipal
    summary: DataAccessSummary
    tables: list[AccessibleHiveTable]
    yarn_queues: list[YarnQueueStatus]
    source_freshness: list[SourceFreshness]


class AdminPlatformSummary(ApiModel):
    total_vms: int = Field(ge=0)
    unhealthy_vms: int = Field(ge=0)
    active_devspaces: int = Field(ge=0)
    active_jobs: int = Field(ge=0)
    governed_tables: int = Field(ge=0)
    ingestion_attention: int = Field(ge=0)
    yarn_queue_attention: int = Field(ge=0)
    active_incidents: int = Field(ge=0)
    pending_approvals: int = Field(ge=0)


class AdminAttentionItem(ApiModel):
    id: str
    type: Literal["ingestion", "yarn_queue", "vm", "incident", "allocation"]
    severity: AdminSeverity
    title: str
    summary: str
    owner: str
    occurred_at: str
    href: str


class AdminHiveAccessItem(ApiModel):
    id: str
    database: str
    table: str
    fully_qualified_name: str
    owner_team: str
    teams: list[str]
    ldap_groups: list[str]
    user_count: int = Field(ge=0)
    privileges: list[str]
    ingestion: MorningIngestionStatus


class AdminIntegrationStatus(ApiModel):
    id: str
    name: str
    status: Literal["healthy", "degraded", "failed", "stale"]
    last_successful_sync: str
    objects_synced: int = Field(ge=0)
    summary: str


class AdminAllocationItem(ApiModel):
    id: str
    vm_name: str
    tenant: str
    target_team: str
    ldap_group: str
    status: Literal["draft", "pending_approval", "applying", "active", "failed"]
    requested_by: str
    requested_at: str
    approver: str | None = None
    summary: str


class AdminPublishedUpdate(ApiModel):
    id: str
    type: Literal["maintenance", "support", "troubleshooting", "documentation"]
    title: str
    service: str
    state: Literal["draft", "in_review", "published", "scheduled"]
    owner: str
    effective_at: str
    audience: str


class AdminCapabilities(ApiModel):
    read_only_preview: bool
    allocation_workflow_enabled: bool
    content_workflow_enabled: bool
    requires_enterprise_sso: bool


class AdminControlPlaneResponse(ApiModel):
    generated_at: datetime
    summary: AdminPlatformSummary
    attention_items: list[AdminAttentionItem]
    hive_tables: list[AdminHiveAccessItem]
    yarn_queues: list[YarnQueueStatus]
    integrations: list[AdminIntegrationStatus]
    allocations: list[AdminAllocationItem]
    updates: list[AdminPublishedUpdate]
    capabilities: AdminCapabilities
