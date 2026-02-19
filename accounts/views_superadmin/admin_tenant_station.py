from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from accounts.models import Utilisateur
from accounts.constants import UserRole
from accounts.permissions_superadmin import IsSuperAdmin
from accounts.serializers.admin_tenant_station import (
    AdminTenantStationCreateSerializer,
)


class SuperAdminAdminTenantStationViewSet(viewsets.ModelViewSet):
    """
    Gestion des AdminTenantStation par le SuperAdmin SaaS.
    """

    serializer_class = AdminTenantStationCreateSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        queryset = Utilisateur.objects.filter(
            role=UserRole.ADMIN_TENANT_STATION
        ).select_related("tenant").order_by("-date_joined")

        # 🔎 Support search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(tenant__nom__icontains=search)
            )

        return queryset
