from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied

from tenants.models import Tenant
from tenants.serializers import TenantSerializer
from accounts.constants import UserRole


class TenantViewSet(viewsets.ModelViewSet):
    """
    Gestion des tenants SaaS.

    - SUPERADMIN : accès global (CRUD contrôlé)
    - ADMIN_TENANT_* : lecture de son propre tenant uniquement
    - Autres rôles : aucun accès
    """

    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch"]  # Pas de DELETE destructif

    def get_queryset(self):
        user = self.request.user

        # 👑 SUPERADMIN SaaS
        if user.role == UserRole.SUPERADMIN:
            return Tenant.objects.all().order_by("-date_creation")

        # 🏢 ADMIN TENANT (Finance ou Station)
        if user.role in (
            UserRole.ADMIN_TENANT_FINANCE,
            UserRole.ADMIN_TENANT_STATION,
        ) and user.tenant_id:
            return Tenant.objects.filter(id=user.tenant_id)

        # ❌ Tous les autres rôles
        return Tenant.objects.none()

    def perform_create(self, serializer):
        user = self.request.user

        # 🔒 Seul SUPERADMIN peut créer un tenant
        if user.role != UserRole.SUPERADMIN:
            raise PermissionDenied(
                "Seul le SuperAdmin SaaS peut créer une organisation."
            )

        serializer.save(created_by=user)

    def perform_update(self, serializer):
        user = self.request.user

        # 🔒 Seul SUPERADMIN peut modifier un tenant
        if user.role != UserRole.SUPERADMIN:
            raise PermissionDenied(
                "Modification interdite."
            )

        serializer.save()

    def perform_destroy(self, instance):
        """
        Suppression physique interdite.
        On désactive le tenant.
        """
        instance.actif = False
        instance.save()
