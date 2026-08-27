from datetime import UTC, datetime

from app.models.devspaces import Devspace, ResourceUtilization
from app.models.observability import (
    DevspaceDetailResponse,
    DevspaceProcess,
    JobsResponse,
    JobSummary,
    KedroJobRun,
    MetricSeries,
    VmDetailResponse,
    VmFacts,
    VmInventoryItem,
    VmInventoryResponse,
    VmInventorySummary,
)
from app.services.devspaces import DevspaceInventoryService


class ObservabilityService:
    """Correlated preview data for jobs, devspaces, processes, users, and VMs."""

    def __init__(self, owner_keys: frozenset[str] | None = None) -> None:
        self.owner_keys = owner_keys
        self.inventory = DevspaceInventoryService().inventory()
        self.devspace_by_id = {item.id: item for item in self.inventory.devspaces}

    def _job(
        self,
        *,
        job_id: str,
        name: str,
        pipeline: str,
        project: str,
        devspace_id: str,
        state: str,
        status: str,
        started_at: str,
        duration: str,
        progress: int,
        nodes_completed: int,
        nodes_total: int,
        current_node: str,
        trigger: str,
        cpu_peak: int,
        memory_peak: float,
        last_message: str,
        failed_node: str | None = None,
    ) -> KedroJobRun:
        devspace = self.devspace_by_id[devspace_id]
        return KedroJobRun(
            id=job_id,
            name=name,
            pipeline=pipeline,
            project=project,
            devspace_id=devspace.id,
            devspace_name=devspace.name,
            vm_id=devspace.vm.id,
            vm_name=devspace.vm.name,
            owner=devspace.owner,
            state=state,
            status=status,
            started_at=started_at,
            duration=duration,
            progress_percentage=progress,
            nodes_completed=nodes_completed,
            nodes_total=nodes_total,
            current_node=current_node,
            trigger=trigger,
            cpu_peak_percentage=cpu_peak,
            memory_peak_gb=memory_peak,
            last_message=last_message,
            failed_node=failed_node,
        )

    def job_runs(self) -> list[KedroJobRun]:
        runs = [
            self._job(
                job_id="run-churn-284",
                name="Customer churn training",
                pipeline="model_training",
                project="customer-model",
                devspace_id="customer-model",
                state="running",
                status="Running",
                started_at="23 min ago",
                duration="23m 14s",
                progress=75,
                nodes_completed=18,
                nodes_total=24,
                current_node="train_xgboost_model",
                trigger="Manual",
                cpu_peak=87,
                memory_peak=14.1,
                last_message="Training fold 4 of 5",
            ),
            self._job(
                job_id="run-fraud-118",
                name="Fraud feature refresh",
                pipeline="feature_engineering",
                project="fraud-detection",
                devspace_id="fraud-lab",
                state="running",
                status="Running",
                started_at="8 min ago",
                duration="8m 06s",
                progress=42,
                nodes_completed=8,
                nodes_total=19,
                current_node="build_velocity_features",
                trigger="Schedule",
                cpu_peak=61,
                memory_peak=9.8,
                last_message="Processing transaction partition 17 of 41",
            ),
            self._job(
                job_id="run-risk-912",
                name="Credit risk calibration",
                pipeline="risk_calibration",
                project="risk-research",
                devspace_id="risk-research",
                state="failed",
                status="Failed",
                started_at="31 min ago",
                duration="14m 52s",
                progress=68,
                nodes_completed=13,
                nodes_total=19,
                current_node="write_calibrated_scores",
                trigger="Manual",
                cpu_peak=98,
                memory_peak=7.7,
                last_message="Process terminated after exceeding its memory allocation",
                failed_node="write_calibrated_scores",
            ),
            self._job(
                job_id="run-features-410",
                name="Customer feature build",
                pipeline="feature_store",
                project="customer-analytics",
                devspace_id="analytics-dev",
                state="succeeded",
                status="Succeeded",
                started_at="1h 12m ago",
                duration="18m 40s",
                progress=100,
                nodes_completed=21,
                nodes_total=21,
                current_node="complete",
                trigger="Manual",
                cpu_peak=54,
                memory_peak=8.4,
                last_message="Pipeline completed successfully",
            ),
            self._job(
                job_id="run-observe-633",
                name="Data quality snapshot",
                pipeline="data_quality",
                project="data-observability",
                devspace_id="data-observability",
                state="succeeded",
                status="Succeeded",
                started_at="2h 04m ago",
                duration="11m 03s",
                progress=100,
                nodes_completed=14,
                nodes_total=14,
                current_node="complete",
                trigger="Schedule",
                cpu_peak=38,
                memory_peak=6.1,
                last_message="All 126 checks completed",
            ),
            self._job(
                job_id="run-price-207",
                name="Pricing elasticity model",
                pipeline="elasticity_training",
                project="pricing-experiment",
                devspace_id="pricing-experiment",
                state="succeeded",
                status="Succeeded",
                started_at="3h 18m ago",
                duration="26m 17s",
                progress=100,
                nodes_completed=17,
                nodes_total=17,
                current_node="complete",
                trigger="Manual",
                cpu_peak=48,
                memory_peak=5.8,
                last_message="Model artefacts written to the experiment store",
            ),
            self._job(
                job_id="run-segment-399",
                name="Customer segmentation",
                pipeline="segmentation",
                project="customer-analytics",
                devspace_id="analytics-dev",
                state="failed",
                status="Failed",
                started_at="5h 42m ago",
                duration="7m 51s",
                progress=36,
                nodes_completed=5,
                nodes_total=14,
                current_node="load_trino_features",
                trigger="Manual",
                cpu_peak=32,
                memory_peak=5.2,
                last_message="Trino query exceeded the configured timeout",
                failed_node="load_trino_features",
            ),
            self._job(
                job_id="run-fraud-117",
                name="Fraud model scoring",
                pipeline="batch_scoring",
                project="fraud-detection",
                devspace_id="fraud-lab",
                state="succeeded",
                status="Succeeded",
                started_at="7h 09m ago",
                duration="32m 06s",
                progress=100,
                nodes_completed=22,
                nodes_total=22,
                current_node="complete",
                trigger="Schedule",
                cpu_peak=72,
                memory_peak=12.6,
                last_message="Scored 4.8 million transactions",
            ),
            self._job(
                job_id="run-churn-285",
                name="Customer churn backtest",
                pipeline="model_backtest",
                project="customer-model",
                devspace_id="customer-model",
                state="queued",
                status="Queued",
                started_at="Queued 4 min ago",
                duration="—",
                progress=0,
                nodes_completed=0,
                nodes_total=16,
                current_node="Waiting for local runner",
                trigger="Manual",
                cpu_peak=0,
                memory_peak=0,
                last_message="Waiting for the active training run to complete",
            ),
            self._job(
                job_id="run-observe-632",
                name="Schema drift detection",
                pipeline="schema_drift",
                project="data-observability",
                devspace_id="data-observability",
                state="succeeded",
                status="Succeeded",
                started_at="10h 26m ago",
                duration="8m 44s",
                progress=100,
                nodes_completed=11,
                nodes_total=11,
                current_node="complete",
                trigger="Schedule",
                cpu_peak=29,
                memory_peak=4.9,
                last_message="No breaking schema changes detected",
            ),
        ]
        if self.owner_keys is None:
            return runs
        return [run for run in runs if run.owner.id in self.owner_keys]

    def jobs(self) -> JobsResponse:
        runs = self.job_runs()
        succeeded = sum(run.state == "succeeded" for run in runs)
        completed = sum(run.state in {"succeeded", "failed"} for run in runs)
        return JobsResponse(
            generated_at=datetime.now(UTC),
            summary=JobSummary(
                total_24h=len(runs),
                running=sum(run.state == "running" for run in runs),
                succeeded=succeeded,
                failed=sum(run.state == "failed" for run in runs),
                queued=sum(run.state == "queued" for run in runs),
                success_rate=round((succeeded / completed) * 100) if completed else 100,
            ),
            jobs=runs,
        )

    def _metrics(self, devspace: Devspace) -> list[MetricSeries]:
        patterns = {
            "cpu": [6, 8, 11, 9, 14, 18, 16, 21, 17, 20, 18, devspace.cpu.percentage],
            "memory": [18, 20, 21, 22, 22, 24, 25, 25, 26, 26, 26, devspace.memory.percentage],
            "disk": [32, 32, 33, 34, 34, 35, 35, 36, 36, 37, 37, devspace.disk.percentage],
        }
        return [
            MetricSeries(
                id="cpu",
                label="CPU",
                resource=devspace.cpu,
                window="Last 6 hours",
                samples=patterns["cpu"],
            ),
            MetricSeries(
                id="memory",
                label="Memory",
                resource=devspace.memory,
                window="Last 6 hours",
                samples=patterns["memory"],
            ),
            MetricSeries(
                id="disk",
                label="Storage",
                resource=devspace.disk,
                window="Last 6 hours",
                samples=patterns["disk"],
            ),
        ]

    def _processes(self, devspace: Devspace) -> list[DevspaceProcess]:
        if devspace.state == "stopped":
            return []
        running_job = next(
            (run for run in self.job_runs() if run.devspace_id == devspace.id and run.state == "running"),
            None,
        )
        processes = [
            DevspaceProcess(
                pid=1284,
                name="code-server",
                command="code-server --host 0.0.0.0",
                category="editor",
                state="running",
                status="Running",
                cpu_percentage=2.8,
                memory_percentage=7.4,
                running_age=devspace.uptime,
                devspace_id=devspace.id,
            ),
            DevspaceProcess(
                pid=1432,
                name="python-language-server",
                command="pyright-langserver --stdio",
                category="editor",
                state="sleeping",
                status="Sleeping",
                cpu_percentage=0.6,
                memory_percentage=3.1,
                running_age="6h 18m",
                devspace_id=devspace.id,
            ),
            DevspaceProcess(
                pid=1519,
                name="jupyter-lab",
                command="jupyter lab --no-browser",
                category="notebook",
                state="running",
                status="Running",
                cpu_percentage=4.2,
                memory_percentage=8.6,
                running_age="4h 52m",
                devspace_id=devspace.id,
            ),
            DevspaceProcess(
                pid=702,
                name="conmon",
                command="conmon --runtime podman",
                category="system",
                state="sleeping",
                status="Sleeping",
                cpu_percentage=0.2,
                memory_percentage=0.8,
                running_age=devspace.uptime,
                devspace_id=devspace.id,
            ),
        ]
        if running_job:
            processes.insert(
                0,
                DevspaceProcess(
                    pid=18422,
                    name="kedro",
                    command=f"kedro run --pipeline {running_job.pipeline}",
                    category="kedro",
                    state="running",
                    status="Running",
                    cpu_percentage=min(82.4, float(running_job.cpu_peak_percentage)),
                    memory_percentage=min(
                        91.0,
                        round((running_job.memory_peak_gb / devspace.memory.limit) * 100, 1),
                    ),
                    running_age=running_job.duration,
                    job_id=running_job.id,
                    devspace_id=devspace.id,
                ),
            )
        return processes

    def devspace_detail(self, devspace_id: str) -> DevspaceDetailResponse | None:
        devspace = self.devspace_by_id.get(devspace_id)
        if not devspace or (self.owner_keys is not None and devspace.owner.id not in self.owner_keys):
            return None
        return DevspaceDetailResponse(
            generated_at=datetime.now(UTC),
            devspace=devspace,
            metrics=self._metrics(devspace),
            jobs=[run for run in self.job_runs() if run.devspace_id == devspace.id],
            processes=self._processes(devspace),
            vm_issues=[issue for issue in self.inventory.vm_issues if issue.vm_id == devspace.vm.id],
        )

    def vm_detail(self, vm_id: str) -> VmDetailResponse | None:
        devspaces = [
            item
            for item in self.inventory.devspaces
            if item.vm.id == vm_id and (self.owner_keys is None or item.owner.id in self.owner_keys)
        ]
        if not devspaces:
            return None
        vm = devspaces[0].vm
        users = list({item.owner.id: item.owner for item in devspaces}.values())
        active_issues = [
            issue for issue in self.inventory.vm_issues if issue.vm_id == vm_id and issue.status == "active"
        ]
        has_critical_issue = any(issue.severity == "critical" for issue in active_issues)
        host_resources = {
            "vm-021": (
                ResourceUtilization(used=8.4, limit=16, unit="cores", percentage=52),
                ResourceUtilization(used=18.3, limit=64, unit="GB", percentage=29),
                ResourceUtilization(used=102, limit=220, unit="GB", percentage=46),
            ),
            "vm-034": (
                ResourceUtilization(used=4.0, limit=24, unit="cores", percentage=17),
                ResourceUtilization(used=12.5, limit=96, unit="GB", percentage=13),
                ResourceUtilization(used=96, limit=300, unit="GB", percentage=32),
            ),
            "vm-041": (
                ResourceUtilization(used=4.8, limit=16, unit="cores", percentage=30),
                ResourceUtilization(used=11.2, limit=64, unit="GB", percentage=18),
                ResourceUtilization(used=124, limit=160, unit="GB", percentage=78),
            ),
            "vm-052": (
                ResourceUtilization(used=0.8, limit=16, unit="cores", percentage=5),
                ResourceUtilization(used=3.1, limit=48, unit="GB", percentage=6),
                ResourceUtilization(used=46, limit=200, unit="GB", percentage=23),
            ),
        }
        cpu, memory, disk = host_resources[vm_id]
        processes = sorted(
            [process for item in devspaces for process in self._processes(item)],
            key=lambda process: process.cpu_percentage,
            reverse=True,
        )[:8]
        facts = {
            "vm-021": VmFacts(
                operating_system="RHEL 9.4",
                kernel="5.14.0-427.31.1.el9_4",
                container_runtime="Podman 4.9.4",
                environment="Production",
                running_age="21d 4h",
                last_patch="Aug 14, 2026",
                load_average="2.18 / 1.94 / 1.72",
            ),
            "vm-034": VmFacts(
                operating_system="RHEL 9.4",
                kernel="5.14.0-427.31.1.el9_4",
                container_runtime="Podman 4.9.4",
                environment="Production",
                running_age="12d 9h",
                last_patch="Aug 14, 2026",
                load_average="1.12 / 0.94 / 0.82",
            ),
            "vm-041": VmFacts(
                operating_system="RHEL 9.4",
                kernel="5.14.0-427.31.1.el9_4",
                container_runtime="Podman 4.9.4",
                environment="Production",
                running_age="18d 2h",
                last_patch="Aug 14, 2026",
                load_average="3.81 / 3.12 / 2.72",
            ),
            "vm-052": VmFacts(
                operating_system="RHEL 9.4",
                kernel="5.14.0-427.31.1.el9_4",
                container_runtime="Podman 4.9.4",
                environment="Non-production",
                running_age="7d 16h",
                last_patch="Aug 18, 2026",
                load_average="0.42 / 0.38 / 0.31",
            ),
        }
        return VmDetailResponse(
            generated_at=datetime.now(UTC),
            vm=vm,
            state="critical" if has_critical_issue else "attention" if active_issues else "healthy",
            status="Critical issue"
            if has_critical_issue
            else "Needs attention"
            if active_issues
            else "Healthy",
            status_detail=(
                f"{len(active_issues)} active host issue{'s' if len(active_issues) != 1 else ''} "
                "may affect hosted devspaces."
                if active_issues
                else "Host services and capacity are within operational thresholds."
            ),
            facts=facts[vm_id],
            cpu=cpu,
            memory=memory,
            disk=disk,
            devspaces=devspaces,
            users=users,
            issues=[issue for issue in self.inventory.vm_issues if issue.vm_id == vm_id],
            top_processes=processes,
        )

    def vms(self) -> VmInventoryResponse:
        vm_ids = list(
            dict.fromkeys(
                item.vm.id
                for item in self.inventory.devspaces
                if self.owner_keys is None or item.owner.id in self.owner_keys
            )
        )
        details = [detail for vm_id in vm_ids if (detail := self.vm_detail(vm_id)) is not None]
        jobs = self.job_runs()
        items = []
        for detail in details:
            active_issues = [issue for issue in detail.issues if issue.status == "active"]
            items.append(
                VmInventoryItem(
                    vm=detail.vm,
                    state=detail.state,
                    status=detail.status,
                    status_detail=detail.status_detail,
                    environment=detail.facts.environment,
                    running_age=detail.facts.running_age,
                    cpu=detail.cpu,
                    memory=detail.memory,
                    disk=detail.disk,
                    devspace_count=len(detail.devspaces),
                    active_devspaces=sum(item.state != "stopped" for item in detail.devspaces),
                    user_count=len(detail.users),
                    users=detail.users,
                    active_jobs=sum(
                        job.vm_id == detail.vm.id and job.state in {"running", "queued"} for job in jobs
                    ),
                    active_issue_count=len(active_issues),
                    last_event=detail.issues[0].occurred_at if detail.issues else "No recent events",
                )
            )
        unique_users = {user.id for item in items for user in item.users}
        return VmInventoryResponse(
            generated_at=datetime.now(UTC),
            summary=VmInventorySummary(
                total=len(items),
                online=len(items),
                healthy=sum(item.state == "healthy" for item in items),
                attention=sum(item.state == "attention" for item in items),
                critical=sum(item.state == "critical" for item in items),
                devspaces=sum(item.devspace_count for item in items),
                users=len(unique_users),
                active_jobs=sum(item.active_jobs for item in items),
                active_issues=sum(item.active_issue_count for item in items),
            ),
            vms=items,
        )
