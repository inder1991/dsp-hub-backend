from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text

from app.auth.db import get_engine
from app.auth.dependencies import ResourceScope, get_current_principal, get_resource_scope, require_admin
from app.auth.service import build_token_service
from app.core.config import Settings, get_settings
from app.models.dashboard import (
    DashboardResponse,
    HealthSummary,
    ReadinessDependency,
    ServiceHealthResponse,
    ServiceReadinessResponse,
)
from app.models.data_platform import AdminControlPlaneResponse, UserDataAccessResponse
from app.models.devspaces import DevspacesResponse
from app.models.observability import (
    DevspaceDetailResponse,
    JobsResponse,
    VmDetailResponse,
    VmInventoryResponse,
)
from app.models.onboarding import OnboardingResponse
from app.models.support import SupportResponse
from app.services.dashboard import DashboardService
from app.services.data_platform import DataPlatformService
from app.services.devspaces import DevspaceInventoryService
from app.services.observability import ObservabilityService
from app.services.onboarding import OnboardingCatalogService
from app.services.support import SupportCatalogService

router = APIRouter()


def get_dashboard_service(settings: Settings = Depends(get_settings)) -> DashboardService:
    return DashboardService(settings)


def get_support_service(settings: Settings = Depends(get_settings)) -> SupportCatalogService:
    return SupportCatalogService(settings)


def get_onboarding_service(settings: Settings = Depends(get_settings)) -> OnboardingCatalogService:
    return OnboardingCatalogService(settings)


def get_devspace_service() -> DevspaceInventoryService:
    return DevspaceInventoryService()


def get_observability_service() -> ObservabilityService:
    return ObservabilityService()


def get_data_platform_service() -> DataPlatformService:
    return DataPlatformService()


@router.get("/healthz", response_model=ServiceHealthResponse, tags=["operations"])
def service_health(settings: Settings = Depends(get_settings)) -> ServiceHealthResponse:
    return ServiceHealthResponse(environment=settings.environment)


@router.get("/readyz", response_model=ServiceReadinessResponse, tags=["operations"])
def service_readiness(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ServiceReadinessResponse:
    dependencies: dict[str, ReadinessDependency] = {}
    ready = True
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        dependencies["postgresql"] = ReadinessDependency(status="ready", detail="Available")
    except Exception:  # pragma: no cover - exercised by deployment probes
        ready = False
        dependencies["postgresql"] = ReadinessDependency(status="unavailable", detail="Unavailable")
    try:
        build_token_service(settings)
        dependencies["jwtSigning"] = ReadinessDependency(status="ready", detail="Configured")
    except Exception:
        ready = False
        dependencies["jwtSigning"] = ReadinessDependency(status="unavailable", detail="Unavailable")

    if settings.ping_configured:
        dependencies["pingSso"] = ReadinessDependency(status="ready", detail="Configured")
    elif settings.ping_configuration_started:
        dependencies["pingSso"] = ReadinessDependency(
            status="degraded", detail="Configuration is incomplete; local login remains available"
        )
    else:
        dependencies["pingSso"] = ReadinessDependency(
            status="degraded", detail="Not configured; local login remains available"
        )
    if not ready:
        response.status_code = 503
    return ServiceReadinessResponse(
        status="ready" if ready else "unavailable",
        environment=settings.environment,
        dependencies=dependencies,
    )


@router.get(
    "/api/v1/home",
    response_model=DashboardResponse,
    tags=["portal"],
)
def home_dashboard(
    scope: ResourceScope = Depends(get_resource_scope),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardResponse:
    return service.dashboard(None if scope.is_admin else scope.owner_keys)


@router.get(
    "/api/v1/health/summary",
    response_model=HealthSummary,
    tags=["portal"],
    dependencies=[Depends(get_current_principal)],
)
def health_summary(service: DashboardService = Depends(get_dashboard_service)) -> HealthSummary:
    return service.health_summary()


@router.get(
    "/api/v1/support",
    response_model=SupportResponse,
    tags=["portal"],
    dependencies=[Depends(get_current_principal)],
)
def support_catalog(
    service: SupportCatalogService = Depends(get_support_service),
) -> SupportResponse:
    return service.catalog()


@router.get(
    "/api/v1/onboarding",
    response_model=OnboardingResponse,
    tags=["portal"],
    dependencies=[Depends(get_current_principal)],
)
def onboarding_catalog(
    service: OnboardingCatalogService = Depends(get_onboarding_service),
) -> OnboardingResponse:
    return service.catalog()


@router.get(
    "/api/v1/devspaces",
    response_model=DevspacesResponse,
    tags=["portal"],
)
def devspace_inventory(
    scope: ResourceScope = Depends(get_resource_scope),
    service: DevspaceInventoryService = Depends(get_devspace_service),
) -> DevspacesResponse:
    return service.inventory_for(None if scope.is_admin else scope.owner_keys)


@router.get(
    "/api/v1/jobs",
    response_model=JobsResponse,
    tags=["portal"],
)
def job_inventory(scope: ResourceScope = Depends(get_resource_scope)) -> JobsResponse:
    return ObservabilityService(None if scope.is_admin else scope.owner_keys).jobs()


@router.get(
    "/api/v1/devspaces/{devspace_id}",
    response_model=DevspaceDetailResponse,
    tags=["portal"],
)
def devspace_detail(
    devspace_id: str,
    scope: ResourceScope = Depends(get_resource_scope),
) -> DevspaceDetailResponse:
    service = ObservabilityService(None if scope.is_admin else scope.owner_keys)
    detail = service.devspace_detail(devspace_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Devspace not found")
    return detail


@router.get(
    "/api/v1/vms",
    response_model=VmInventoryResponse,
    tags=["portal"],
)
def vm_inventory(scope: ResourceScope = Depends(get_resource_scope)) -> VmInventoryResponse:
    return ObservabilityService(None if scope.is_admin else scope.owner_keys).vms()


@router.get(
    "/api/v1/vms/{vm_id}",
    response_model=VmDetailResponse,
    tags=["portal"],
)
def vm_detail(
    vm_id: str,
    scope: ResourceScope = Depends(get_resource_scope),
) -> VmDetailResponse:
    service = ObservabilityService(None if scope.is_admin else scope.owner_keys)
    detail = service.vm_detail(vm_id)
    if not detail:
        raise HTTPException(status_code=404, detail="VM not found")
    return detail


@router.get(
    "/api/v1/data-access",
    response_model=UserDataAccessResponse,
    tags=["data-platform"],
)
def user_data_access(
    scope: ResourceScope = Depends(get_resource_scope),
    service: DataPlatformService = Depends(get_data_platform_service),
) -> UserDataAccessResponse:
    return service.user_access(None if scope.is_admin else scope.owner_keys)


@router.get(
    "/api/v1/admin/control-plane",
    response_model=AdminControlPlaneResponse,
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
def admin_control_plane(
    service: DataPlatformService = Depends(get_data_platform_service),
) -> AdminControlPlaneResponse:
    return service.admin_control_plane()
