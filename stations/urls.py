# stations/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_depotage.depotage import DepotageViewSet
from .views_depotage.justification import JustificationDepotageViewSet

from .views_dashboard import StationOperationalDashboardAPIView
from .dashboard_views import StationRelaisListView
from .views_operations import StationLastOperationsAPIView
from accounts.views import PersonnelStationViewSet

from .views import (
    StationViewSet,
    VenteCarburantViewSet,
    LocalViewSet,
    ContratLocationViewSet,
    StationDashboardView,
    RelaisEquipeViewSet,
    AdminTenantStationDashboardAPIView,
    AdminTenantStationDashboardView,
)

router = DefaultRouter()
router.register(r"depotages", DepotageViewSet, basename="depotage")
router.register(r"stations", StationViewSet, basename="station")
router.register(r"ventes-carburant", VenteCarburantViewSet, basename="ventes-carburant")
router.register(r"locaux", LocalViewSet, basename="locaux")
router.register(r"contrats-location", ContratLocationViewSet, basename="contrats-location")

router.register(
    "depotages/justifications",
    JustificationDepotageViewSet,
    basename="justification-depotage"
)

router.register(
    r"personnel",
    PersonnelStationViewSet,
    basename="station-personnel"
)

router.register(
    r"relais-equipes",
    RelaisEquipeViewSet,
    basename="relais-equipes"
)


urlpatterns = [
    path(
        "operations/dernieres/",
        StationLastOperationsAPIView.as_view(),
        name="station-last-operations",
    ),
    path(
        "station/relais-equipes/",
        StationRelaisListView.as_view(),
        name="station-relais-list"
    ),
    path(
        "dashboard/operationnel/",
        StationOperationalDashboardAPIView.as_view(),
        name="station-dashboard-operationnel",
    ),
    path(
        "dashboard/admin-tenant/",
        AdminTenantStationDashboardView.as_view(),
        name="dashboard-admin-tenant-station",
    ),
    path(
        "dashboard/admin-tenant/",
        AdminTenantStationDashboardAPIView.as_view(),
        name="admin-tenant-station-dashboard",
    ),  
    path("dashboard/", StationDashboardView.as_view(), name="station-dashboard"),
    path("", include(router.urls)),
]