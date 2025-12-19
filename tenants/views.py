from tenants.models import Tenant
from tenants.serializers import TenantSerializer
from tenants.permissions import TenantPermission


from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from .models import Tenant
from .serializers import TenantSerializer


class TenantViewSet(viewsets.ModelViewSet):
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # ✅ SUPERADMIN : accès global
        if user.is_superuser:
            return Tenant.objects.all()

        # ✅ ADMIN TENANT : son propre tenant
        if user.role == "AdminTenant" and user.tenant_id:
            return Tenant.objects.filter(id=user.tenant_id)

        # ❌ AUTRES : aucun accès
        return Tenant.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied(
                "Seul le SuperAdmin peut créer une organisation."
            )
        serializer.save(created_by=self.request.user)

