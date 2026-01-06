# backend/saas_finance/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework import routers
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    MembreViewSet,
    ProjetViewSet,
    UtilisateurViewSet,
    TransactionViewSet,
    CotisationViewSet,
    SyncView,
    FileUploadView,
    LoginView,
    MeView,
    MyTokenObtainPairView,
    StaffViewSet,
)

from core.views_tenant import TenantViewSet

app_name = "saas_finance"

router = routers.DefaultRouter()
router.register(r'files', FileUploadView, basename='files')
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'membres', MembreViewSet, basename='membre')
router.register(r'projets', ProjetViewSet, basename='projet')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'cotisations', CotisationViewSet, basename='cotisation')
router.register(r'utilisateurs', UtilisateurViewSet, basename='utilisateur')
router.register(r'staff', StaffViewSet, basename="staff")


urlpatterns = [
    path("api/v1/dashboard/", include("dashboard.urls")),
    
    path("api/v1/station/", include("stations.urls")),
    path("api/v1/finances/", include("finances_station.urls")),

    path("api/v1/", include(router.urls)),

    path("api/v1/me/", MeView.as_view()),
    path("api/v1/sync/", SyncView.as_view()),

    path("api/v1/auth/login/", MyTokenObtainPairView.as_view()),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view()),

    path('api/schema/', SpectacularAPIView.as_view(), name='openapi-schema'),

    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url='/api/schema/'),
        name='swagger-ui'
    ),

    path("admin/", admin.site.urls),
]
