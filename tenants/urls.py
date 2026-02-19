from rest_framework.routers import DefaultRouter
from tenants.views_superadmin import SuperAdminTenantViewSet

router = DefaultRouter()
router.register(
    r"superadmin/tenants",
    SuperAdminTenantViewSet,
    basename="superadmin-tenants"
)

urlpatterns = router.urls
