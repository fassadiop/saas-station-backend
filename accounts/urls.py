from rest_framework.routers import DefaultRouter
from accounts.views import GerantViewSet
from accounts.views_superadmin.admin_tenant_station import (
    SuperAdminAdminTenantStationViewSet,
)

router = DefaultRouter()
router.register(
    r"superadmin/admin-tenant-station",
    SuperAdminAdminTenantStationViewSet,
    basename="superadmin-admin-tenant-station"
)


router.register(r"admin-tenant/gerants", GerantViewSet, basename="gerants")

urlpatterns = router.urls
