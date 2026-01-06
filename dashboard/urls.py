# dashboard/urls.py
from django.urls import path
from .views_admin import AdminDashboardView
from .views import DashboardView

from .views import (
    AdminTenantStationDashboardView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("admin/", AdminDashboardView.as_view(), name="dashboard-admin"),
    path("tenant/", DashboardView.as_view(), name="dashboard-tenant"),
    
    path(
        "admin-tenant/station/",
        AdminTenantStationDashboardView.as_view(),
        name="dashboard-admin-tenant-station",
    ),
]
