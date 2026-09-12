# stations/urls.py

from stations.views_dashboard import StationOperationalDashboardAPIView
from stations.views_depotage.mouvement_stock import MouvementStockViewSet
from stations.views_stock import StockGlobalStationView
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views_depotage.depotage import DepotageViewSet

from .dashboard_views import StationRelaisListView
from .views_operations import StationLastOperationsAPIView
from accounts.views import PersonnelStationViewSet

from .views import (
    CategorieDepenseViewSet,
    ClientStationViewSet,
    ClotureJournaliereView,
    ClotureRelaisListView,
    ClotureRelaisPdfView,
    ClotureRelaisView,
    CuveViewSet,
    DepenseViewSet,
    DetteStationViewSet,
    EcartSyntheseMensuelleView,
    EncaissementRelaisViewSet,
    IlotViewSet,
    IndexPompeActifListView,
    IndexPompeViewSet,
    ModePaiementViewSet,
    ObjectifStationViewSet,
    PompeViewSet,
    PrixCarburantViewSet,
    ProduitCarburantViewSet,
    RelaisEcartViewSet,
    RelaisIlotViewSet,
    RemboursementEcartViewSet,
    StationViewSet,
    StationDashboardView,
    RelaisEquipeViewSet,
    AdminTenantStationDashboardView,
    VersementViewSet,
    list_notifications,
    mark_as_read,
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

router.register(
    r"objectifs",
    ObjectifStationViewSet,
    basename="objectifs-station"
)

router.register(
    "ilots",
    IlotViewSet,
    basename="station-ilots"
)

router.register(
    r"relais-ilots",
    RelaisIlotViewSet,
    basename="relais-ilots"
)

router.register(
    "modes-paiement",
    ModePaiementViewSet,
    basename="modes-paiement"
)

router.register(
    r"encaissements",
    EncaissementRelaisViewSet,
    basename="encaissements"
)

router.register(
    r"versements",
    VersementViewSet,
    basename="versements"
)

router.register(
    r"depenses",
    DepenseViewSet,
    basename="depenses"
)

router.register(
    "categories-depense",
    CategorieDepenseViewSet,
    basename="categories-depense"
)

router.register(
    "dettes",
    DetteStationViewSet,
    basename="dettes"
)

router.register(
    "clients",
    ClientStationViewSet,
    basename="clients"
)

router.register(
    r"relais-ecarts",
    RelaisEcartViewSet,
    basename="relais-ecarts"
)

router.register(
    r"remboursements-ecarts",
    RemboursementEcartViewSet,
    basename="remboursements-ecarts"
)

urlpatterns = [
    path(
        "cloture-relais/<int:relais_id>/pdf/",
        ClotureRelaisPdfView.as_view(),
    ),

    path(
        "cloture-relais/",
        ClotureRelaisListView.as_view(),
    ),

    path(
        "cloture-relais/<int:relais_id>/",
        ClotureRelaisView.as_view(),
    ),

    path(
        "cloture-journaliere/",
        ClotureJournaliereView.as_view(),
        name="cloture-journaliere",
    ),

    path(
        "relais-ecarts/synthese-mensuelle/",
        EcartSyntheseMensuelleView.as_view(),
    ),

    path(
        "stock/global/", 
        StockGlobalStationView.as_view()
    ),

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
        "station/relais-equipes-list/",
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
        name="admin-tenant-station-dashboard",
    ),  
    path("dashboard/", StationDashboardView.as_view(), name="station-dashboard"),
    path("", include(router.urls)),

    path("", list_notifications),
    path("<int:pk>/read/", mark_as_read),
]