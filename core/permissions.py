# core/permissions.py
from rest_framework.permissions import BasePermission, SAFE_METHODS
from accounts.constants import UserRole


class IsSuperAdminOnly(BasePermission):
    """
    Accès réservé au SuperAdmin.
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class IsAdminTenantFinanceOnly(BasePermission):
    """
    Admin qui gère UNIQUEMENT la finance du tenant.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == UserRole.ADMIN_TENANT_FINANCE
            and user.tenant is not None
        )


class IsAdminTenantStationOnly(BasePermission):
    """
    Admin qui supervise UNIQUEMENT les stations du tenant.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == UserRole.ADMIN_TENANT_STATION
            and user.tenant is not None
        )


class IsStationStaff(BasePermission):
    """
    Personnel terrain station.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role in {
                UserRole.CHEF_STATION,
                UserRole.COLLECTEUR,
            }
        )


class IsSameTenantOrSuper(BasePermission):
    """
    Accès objet si même tenant ou superadmin.
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_superuser:
            return True

        return (
            hasattr(obj, "tenant")
            and user.tenant is not None
            and obj.tenant_id == user.tenant_id
        )


class IsTransactionAllowed(BasePermission):
    """
    Règles transactions CLAIRES et NON ambiguës.
    """
    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # SuperAdmin : full access
        if user.is_superuser:
            return True

        # Admin finance : full finance
        if user.role == UserRole.ADMIN_TENANT_FINANCE:
            return True

        # Collecteur : RECETTES uniquement
        if user.role == UserRole.COLLECTEUR:
            if request.method == "POST":
                return request.data.get("type") == "RECETTE"
            return request.method in SAFE_METHODS

        # Autres : lecture seule
        return request.method in SAFE_METHODS
