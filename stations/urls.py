# stations/urls.py

from stations.views_depotage.mouvement_stock import MouvementStockViewSet
from stations.views_stock import StockGlobalStationView
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_depotage.depotage import DepotageViewSet

from .dashboard_views import StationRelaisListView
from .views_operations import StationLastOperationsAPIView
from accounts.views import PersonnelStationViewSet

from .views import (
    CuveViewSet,
    IndexPompeActifListView,
    IndexPompeViewSet,
    PompeViewSet,
    PrixCarburantViewSet,
    ProduitCarburantViewSet,
    StationViewSet,
    StationDashboardView,
    RelaisEquipeViewSet,
    AdminTenantStationDashboardAPIView,
    AdminTenantStationDashboardView,
)

router = DefaultRouter()
router.register(r"depotages", DepotageViewSet, basename="depotage")
router.register(r"stations", StationViewSet, basename="station")
router.register(r"cuves", CuveViewSet, basename="cuve")
router.register(
    r"produits-carburant",
    ProduitCarburantViewSet,
    basename="produits"
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

router.register(
    r"prix",
    PrixCarburantViewSet,
    basename="prix"
)

router.register(
    r"pompes",
    PompeViewSet,
    basename="pompes"
)

router.register(
    r"index-pompes",
    IndexPompeViewSet,
    basename="index-pompes"
)

router.register(
    r"mouvements-stock",
    MouvementStockViewSet,
    basename="mouvements-stock"
)


urlpatterns = [
    path("stock/global/", StockGlobalStationView.as_view()),
    path(
        "operations/dernieres/",
        StationLastOperationsAPIView.as_view(),
        name="station-last-operations",
    ),
    path(
        "index-pompes/actifs/",
        IndexPompeActifListView.as_view(),
    ),
    path(
        "station/relais-equipes/",
        StationRelaisListView.as_view(),
        name="station-relais-list"
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