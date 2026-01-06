from rest_framework.permissions import BasePermission
from accounts.constants import UserRole


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.SUPERADMIN
        )


class IsAdminTenantFinance(BasePermission):
    """
    Accès STRICT au dashboard FINANCE du tenant
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.ADMIN_TENANT_FINANCE
        )


class IsAdminTenantStation(BasePermission):
    """
    Accès STRICT au dashboard SUPERVISION STATION
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.ADMIN_TENANT_STATION
        )


class IsStationStaff(BasePermission):
    """
    Accès STRICT au dashboard TERRAIN (station)
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {
                UserRole.ADMIN_TENANT_STATION,
                UserRole.GERANT,
                UserRole.SUPERVISEUR,
                UserRole.POMPISTE,
                UserRole.CAISSIER,
                UserRole.PERSONNEL_ENTRETIEN,
                UserRole.COLLECTEUR,
                UserRole.SECURITE,
            }
        )

class CanAccessStationOperationalDashboard(BasePermission):
    """
    Accès au dashboard opérationnel station pour :
    - Staff station
    - AdminTenantStation
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # ✅ Admin tenant station : autorisé
        if user.role == UserRole.ADMIN_TENANT_STATION:
            return True

        # ✅ Staff station : autorisé
        return (
            user.role in {
                UserRole.GERANT,
                UserRole.SUPERVISEUR,
                UserRole.POMPISTE,
                UserRole.CAISSIER,
                UserRole.PERSONNEL_ENTRETIEN,
                UserRole.SECURITE,
                UserRole.COLLECTEUR,
            }
            and user.station is not None
        )