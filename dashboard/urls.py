# dashboard/urls.py
from django.urls import path
from .views_admin import AdminDashboardView
from .views import DashboardView

urlpatterns = [
    path("dashboard/admin/", AdminDashboardView.as_view(), name="dashboard-admin"),
    path("dashboard/tenant/", DashboardView.as_view(), name="dashboard-tenant"),
]
