from django.urls import path
from .dashboard import FinanceDashboardAPIView

urlpatterns = [
    path("", FinanceDashboardAPIView.as_view(), name="finance-dashboard"),
]
