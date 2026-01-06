# tenants/permissions.py
from rest_framework.permissions import BasePermission
from accounts.constants import UserRole


class TenantPermission(BasePermission):
    """
    Permissions d'accès aux tenants
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # SuperAdmin → accès total
        if user.is_superuser:
            return True

        # Admin FINANCE ou STATION → accès limité à SON tenant
        if user.role in {
            UserRole.ADMIN_TENANT_FINANCE,
            UserRole.ADMIN_TENANT_STATION,
        }:
            if view.action in {"list", "retrieve"}:
                return True

        return False


class IsStationActor(BasePermission):
    """
    Acteurs terrain station
    """
    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and getattr(user, "station", None) is not None
        )
