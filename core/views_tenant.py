# core/views_tenant.py
from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from .models import Tenant
from .serializers import TenantSerializer
from accounts.constants import UserRole

class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = []

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return Tenant.objects.all()

        if user.role in {
            UserRole.ADMIN_TENANT_FINANCE,
            UserRole.ADMIN_TENANT_STATION,
        }:
            return Tenant.objects.filter(id=user.tenant_id)

        return Tenant.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Seul le SuperAdmin peut créer un tenant.")
        serializer.save(created_by=self.request.user)
