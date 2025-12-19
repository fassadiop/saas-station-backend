from django.urls import path
from .dashboard import StationDashboardAPIView

urlpatterns = [
    path("", StationDashboardAPIView.as_view(), name="station-dashboard"),
]
