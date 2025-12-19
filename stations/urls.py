from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StationViewSet, VenteCarburantViewSet, LocalViewSet, ContratLocationViewSet

router = DefaultRouter()
router.register("stations", StationViewSet, basename="stations")
router.register("ventes-carburant", VenteCarburantViewSet, basename="ventes-carburant")
router.register("locaux", LocalViewSet, basename="locaux")
router.register("contrats-location", ContratLocationViewSet, basename="contrats-location")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", include("stations.api.urls")),
]