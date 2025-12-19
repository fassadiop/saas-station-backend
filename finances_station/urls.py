from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TransactionStationViewSet

router = DefaultRouter()
router.register("transactions", TransactionStationViewSet, basename="transactions")

urlpatterns = [
    path("", include(router.urls)),               # CRUD finances
    path("dashboard/", include("finances_station.api.urls")),  # DASHBOARD
]
