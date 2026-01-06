# dashboard/views_admin.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from core.permissions import IsSuperAdminOnly
from core.models import Tenant
from accounts.constants import UserRole

User = get_user_model()


class AdminDashboardView(APIView):
    """
    Dashboard de gouvernance (SuperAdmin uniquement)
    """
    permission_classes = [IsAuthenticated, IsSuperAdminOnly]

    def get(self, request):
        tenants = Tenant.objects.all().order_by("-date_creation")[:5]

        admin_tenants = User.objects.filter(
            role__in=[
                UserRole.ADMIN_TENANT_FINANCE,
                UserRole.ADMIN_TENANT_STATION,
            ]
        ).select_related("tenant")

        return Response({
            "stats": {
                "tenants_total": Tenant.objects.count(),
                "admin_tenants_total": admin_tenants.count(),
            },
            "tenants_latest": [
                {
                    "id": t.id,
                    "nom": t.nom,
                    "date_creation": t.date_creation.isoformat(),
                }
                for t in tenants
            ],
            "admin_tenants": [
                {
                    "id": u.id,
                    "email": u.email,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "role": u.role,
                    "tenant_nom": u.tenant.nom if u.tenant else None,
                }
                for u in admin_tenants
            ],
        })
