from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from tenants.models import Tenant
from tenants.serializers import TenantSerializer
from accounts.permissions_superadmin import IsSuperAdmin


class SuperAdminTenantViewSet(viewsets.ModelViewSet):
    """
    CRUD Tenant réservé au SuperAdmin SaaS.
    """

    serializer_class = TenantSerializer
    queryset = Tenant.objects.all().order_by("-date_creation")
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    http_method_names = ["get", "post", "patch"]

    def perform_destroy(self, instance):
        """
        Suppression physique interdite.
        On désactive uniquement.
        """
        instance.actif = False
        instance.save()
