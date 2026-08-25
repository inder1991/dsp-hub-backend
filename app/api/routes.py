from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.models.dashboard import DashboardResponse, HealthSummary, ServiceHealthResponse
from app.models.onboarding import OnboardingResponse
from app.models.support import SupportResponse
from app.services.dashboard import DashboardService
from app.services.onboarding import OnboardingCatalogService
from app.services.support import SupportCatalogService

router = APIRouter()


def get_dashboard_service(settings: Settings = Depends(get_settings)) -> DashboardService:
    return DashboardService(settings)


def get_support_service(settings: Settings = Depends(get_settings)) -> SupportCatalogService:
    return SupportCatalogService(settings)


def get_onboarding_service(settings: Settings = Depends(get_settings)) -> OnboardingCatalogService:
    return OnboardingCatalogService(settings)


@router.get("/healthz", response_model=ServiceHealthResponse, tags=["operations"])
def service_health(settings: Settings = Depends(get_settings)) -> ServiceHealthResponse:
    return ServiceHealthResponse(environment=settings.environment)


@router.get("/api/v1/home", response_model=DashboardResponse, tags=["portal"])
def home_dashboard(service: DashboardService = Depends(get_dashboard_service)) -> DashboardResponse:
    return service.dashboard()


@router.get("/api/v1/health/summary", response_model=HealthSummary, tags=["portal"])
def health_summary(service: DashboardService = Depends(get_dashboard_service)) -> HealthSummary:
    return service.health_summary()


@router.get("/api/v1/support", response_model=SupportResponse, tags=["portal"])
def support_catalog(
    service: SupportCatalogService = Depends(get_support_service),
) -> SupportResponse:
    return service.catalog()


@router.get("/api/v1/onboarding", response_model=OnboardingResponse, tags=["portal"])
def onboarding_catalog(
    service: OnboardingCatalogService = Depends(get_onboarding_service),
) -> OnboardingResponse:
    return service.catalog()
