from datetime import UTC, datetime

from app.models.devspaces import (
    Devspace,
    DevspaceConnection,
    DevspaceOwner,
    DevspacesResponse,
    DevspaceSummary,
    FleetCapacity,
    HostVm,
    ResourceUtilization,
    VmIssue,
)


def _owner(owner_id: str, name: str, initials: str, team: str) -> DevspaceOwner:
    return DevspaceOwner(id=owner_id, name=name, initials=initials, team=team)


def _vm(vm_id: str, name: str, tenant: str, host_group: str) -> HostVm:
    return HostVm(id=vm_id, name=name, tenant=tenant, host_group=host_group)


def _resource(used: float, limit: float, unit: str, percentage: int) -> ResourceUtilization:
    return ResourceUtilization(used=used, limit=limit, unit=unit, percentage=percentage)


def _connections(
    nexus: tuple[str, str] = ("connected", "Connected"),
    cdp: tuple[str, str] = ("connected", "Connected"),
    trino: tuple[str, str] = ("connected", "Connected"),
) -> list[DevspaceConnection]:
    return [
        DevspaceConnection(name="Nexus", state=nexus[0], status=nexus[1]),
        DevspaceConnection(name="CDP", state=cdp[0], status=cdp[1]),
        DevspaceConnection(name="Trino", state=trino[0], status=trino[1]),
    ]


class DevspaceInventoryService:
    """Preview adapter for the future VM and container-runtime inventory integrations."""

    def inventory(self) -> DevspacesResponse:
        analytics_vm = _vm("vm-021", "dsp-vm-021", "Analytics", "vm-prod-a")
        modelling_vm = _vm("vm-034", "dsp-vm-034", "Model Development", "vm-prod-a")
        risk_vm = _vm("vm-041", "dsp-vm-041", "Risk", "vm-prod-b")
        sandbox_vm = _vm("vm-052", "dsp-vm-052", "Sandbox", "vm-nonprod-a")

        devspaces = [
            Devspace(
                id="analytics-dev",
                name="analytics-dev",
                kind="Devspace",
                owner=_owner("alex-morgan", "Alex Morgan", "AM", "Customer Analytics"),
                vm=analytics_vm,
                state="healthy",
                status="Healthy",
                status_detail="Runtime and dependencies are responding normally.",
                cpu=_resource(1.4, 8, "cores", 18),
                memory=_resource(4.2, 16, "GB", 26),
                disk=_resource(38, 100, "GB", 38),
                uptime="2d 7h",
                last_activity="6 min ago",
                image="python-3.11-dsp:2026.08",
                python_version="3.11.9",
                restart_count=0,
                connections=_connections(),
            ),
            Devspace(
                id="customer-model",
                name="customer-model",
                kind="Dev container",
                owner=_owner("priya-nair", "Priya Nair", "PN", "Customer Analytics"),
                vm=analytics_vm,
                state="attention",
                status="High memory",
                status_detail="Memory has remained above 85% for 18 minutes.",
                cpu=_resource(7.0, 8, "cores", 87),
                memory=_resource(14.1, 16, "GB", 88),
                disk=_resource(64, 100, "GB", 64),
                uptime="18h 42m",
                last_activity="2 min ago",
                image="python-3.11-dsp:2026.08",
                python_version="3.11.9",
                restart_count=1,
                connections=_connections(trino=("degraded", "Elevated latency")),
            ),
            Devspace(
                id="risk-research",
                name="risk-research",
                kind="Devspace",
                owner=_owner("omar-hassan", "Omar Hassan", "OH", "Credit Risk"),
                vm=risk_vm,
                state="critical",
                status="Unresponsive",
                status_detail="The container health probe has failed three consecutive times.",
                cpu=_resource(3.9, 4, "cores", 98),
                memory=_resource(7.7, 8, "GB", 96),
                disk=_resource(73, 80, "GB", 91),
                uptime="5d 3h",
                last_activity="21 min ago",
                image="python-3.10-dsp:2026.06",
                python_version="3.10.14",
                restart_count=4,
                connections=_connections(
                    cdp=("degraded", "Connection unavailable"),
                    trino=("degraded", "Connection unavailable"),
                ),
            ),
            Devspace(
                id="fraud-lab",
                name="fraud-lab",
                kind="Devspace",
                owner=_owner("leila-khan", "Leila Khan", "LK", "Financial Crime"),
                vm=modelling_vm,
                state="healthy",
                status="Healthy",
                status_detail="Runtime and dependencies are responding normally.",
                cpu=_resource(2.2, 8, "cores", 28),
                memory=_resource(6.8, 24, "GB", 28),
                disk=_resource(52, 120, "GB", 43),
                uptime="1d 4h",
                last_activity="14 min ago",
                image="python-3.11-dsp:2026.08",
                python_version="3.11.9",
                restart_count=0,
                connections=_connections(),
            ),
            Devspace(
                id="data-observability",
                name="data-observability",
                kind="Dev container",
                owner=_owner("daniel-lee", "Daniel Lee", "DL", "Data Platform"),
                vm=modelling_vm,
                state="healthy",
                status="Healthy",
                status_detail="Runtime and dependencies are responding normally.",
                cpu=_resource(1.8, 8, "cores", 23),
                memory=_resource(5.7, 16, "GB", 36),
                disk=_resource(44, 100, "GB", 44),
                uptime="9d 11h",
                last_activity="31 min ago",
                image="python-3.11-dsp:2026.08",
                python_version="3.11.9",
                restart_count=0,
                connections=_connections(),
            ),
            Devspace(
                id="pricing-experiment",
                name="pricing-experiment",
                kind="Devspace",
                owner=_owner("sara-ali", "Sara Ali", "SA", "Retail Pricing"),
                vm=sandbox_vm,
                state="healthy",
                status="Healthy",
                status_detail="Runtime and dependencies are responding normally.",
                cpu=_resource(0.8, 4, "cores", 20),
                memory=_resource(3.1, 8, "GB", 39),
                disk=_resource(29, 80, "GB", 36),
                uptime="6h 18m",
                last_activity="1h ago",
                image="python-3.11-dsp:2026.08",
                python_version="3.11.9",
                restart_count=0,
                connections=_connections(cdp=("not_configured", "Not configured")),
            ),
            Devspace(
                id="treasury-sandbox",
                name="treasury-sandbox",
                kind="Devspace",
                owner=_owner("michael-ross", "Michael Ross", "MR", "Treasury Analytics"),
                vm=sandbox_vm,
                state="stopped",
                status="Stopped",
                status_detail="Stopped by the owner. No compute resources are currently consumed.",
                cpu=_resource(0, 4, "cores", 0),
                memory=_resource(0, 8, "GB", 0),
                disk=_resource(17, 80, "GB", 21),
                uptime="—",
                last_activity="Yesterday",
                image="python-3.11-dsp:2026.08",
                python_version="3.11.9",
                restart_count=0,
                connections=_connections(
                    nexus=("not_configured", "Not running"),
                    cdp=("not_configured", "Not running"),
                    trino=("not_configured", "Not running"),
                ),
            ),
        ]

        return DevspacesResponse(
            generated_at=datetime.now(UTC),
            summary=DevspaceSummary(
                total=len(devspaces),
                active=6,
                healthy=4,
                needs_attention=2,
                stopped=1,
            ),
            fleet=FleetCapacity(
                vm_count=4,
                online_vms=4,
                cpu_percentage=47,
                memory_percentage=61,
                storage_percentage=54,
                at_risk_vms=1,
            ),
            devspaces=devspaces,
            vm_issues=[
                VmIssue(
                    id="issue-vm041-runtime",
                    vm_id="vm-041",
                    title="Container runtime health degraded",
                    summary="Health probes are timing out for one hosted devspace.",
                    severity="critical",
                    status="active",
                    occurred_at="12 min ago",
                    affected_devspaces=1,
                ),
                VmIssue(
                    id="issue-vm021-memory",
                    vm_id="vm-021",
                    title="Sustained memory pressure",
                    summary="Allocated memory has remained above the operational threshold.",
                    severity="warning",
                    status="active",
                    occurred_at="18 min ago",
                    affected_devspaces=1,
                ),
                VmIssue(
                    id="issue-vm041-disk",
                    vm_id="vm-041",
                    title="Low workspace disk capacity",
                    summary="Available workspace storage fell below 10 GB.",
                    severity="warning",
                    status="active",
                    occurred_at="34 min ago",
                    affected_devspaces=1,
                ),
                VmIssue(
                    id="issue-vm034-nexus",
                    vm_id="vm-034",
                    title="Nexus package retrieval latency",
                    summary="Package downloads were slower than the normal baseline.",
                    severity="warning",
                    status="resolved",
                    occurred_at="Yesterday, 14:10",
                    resolved_at="Yesterday, 14:32",
                    affected_devspaces=2,
                ),
                VmIssue(
                    id="issue-vm021-runtime-restart",
                    vm_id="vm-021",
                    title="Container runtime restarted",
                    summary="Runtime service recovered automatically after a transient failure.",
                    severity="informational",
                    status="resolved",
                    occurred_at="Aug 23, 09:18",
                    resolved_at="Aug 23, 09:21",
                    affected_devspaces=2,
                ),
                VmIssue(
                    id="issue-vm052-network",
                    vm_id="vm-052",
                    title="Intermittent Trino connectivity",
                    summary="Three short connection interruptions were detected.",
                    severity="warning",
                    status="resolved",
                    occurred_at="Aug 22, 16:44",
                    resolved_at="Aug 22, 16:58",
                    affected_devspaces=1,
                ),
                VmIssue(
                    id="issue-vm041-cdp",
                    vm_id="vm-041",
                    title="CDP authentication latency",
                    summary="Kerberos authentication exceeded the expected response time.",
                    severity="warning",
                    status="resolved",
                    occurred_at="Aug 20, 11:06",
                    resolved_at="Aug 20, 11:29",
                    affected_devspaces=1,
                ),
                VmIssue(
                    id="issue-vm034-maintenance",
                    vm_id="vm-034",
                    title="Scheduled host patching completed",
                    summary="The VM returned to service and all devspaces recovered.",
                    severity="informational",
                    status="resolved",
                    occurred_at="Aug 18, 01:00",
                    resolved_at="Aug 18, 01:22",
                    affected_devspaces=2,
                ),
                VmIssue(
                    id="issue-vm021-disk-cleanup",
                    vm_id="vm-021",
                    title="Temporary storage threshold exceeded",
                    summary="Unused image layers were removed automatically.",
                    severity="warning",
                    status="resolved",
                    occurred_at="Aug 15, 17:30",
                    resolved_at="Aug 15, 17:37",
                    affected_devspaces=2,
                ),
                VmIssue(
                    id="issue-vm052-image-pull",
                    vm_id="vm-052",
                    title="Base image pull retried",
                    summary="A transient registry timeout recovered on the second attempt.",
                    severity="informational",
                    status="resolved",
                    occurred_at="Aug 12, 08:51",
                    resolved_at="Aug 12, 08:54",
                    affected_devspaces=1,
                ),
            ],
        )

    def inventory_for(self, owner_keys: frozenset[str] | None) -> DevspacesResponse:
        """Return only resources owned by the caller; ``None`` is platform-wide admin scope."""
        inventory = self.inventory()
        if owner_keys is None:
            return inventory
        devspaces = [item for item in inventory.devspaces if item.owner.id in owner_keys]
        vm_ids = {item.vm.id for item in devspaces}
        active = [item for item in devspaces if item.state != "stopped"]

        def average(resource: str) -> int:
            values = [getattr(item, resource).percentage for item in active]
            return round(sum(values) / len(values)) if values else 0

        return DevspacesResponse(
            generated_at=inventory.generated_at,
            summary=DevspaceSummary(
                total=len(devspaces),
                active=len(active),
                healthy=sum(item.state == "healthy" for item in devspaces),
                needs_attention=sum(item.state in {"attention", "critical"} for item in devspaces),
                stopped=sum(item.state == "stopped" for item in devspaces),
            ),
            fleet=FleetCapacity(
                vm_count=len(vm_ids),
                online_vms=len(vm_ids),
                cpu_percentage=average("cpu"),
                memory_percentage=average("memory"),
                storage_percentage=average("disk"),
                at_risk_vms=len(
                    {item.vm.id for item in devspaces if item.state in {"attention", "critical"}}
                ),
            ),
            devspaces=devspaces,
            vm_issues=[issue for issue in inventory.vm_issues if issue.vm_id in vm_ids],
        )
