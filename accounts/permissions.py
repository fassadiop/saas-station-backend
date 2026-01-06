# accounts/permissions.py
from rest_framework.permissions import BasePermission
from accounts.constants import UserRole


class CanManageUsers(BasePermission):
    """
    Gestion des utilisateurs par rôle.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # SuperAdmin : accès total
        if request.user.is_superuser:
            return True

        # AdminTenant : création et gestion limitée
        if request.user.role == UserRole.ADMIN_TENANT_FINANCE:
            if view.action in ["create", "list", "retrieve", "update", "partial_update"]:
                return True

        # Autres rôles : lecture seule (optionnel)
        if view.action in ["retrieve", "list"]:
            return True

        return False

class IsGerantOrAdminTenantStation(BasePermission):
    """
    Gestion du personnel STATION autorisée uniquement à :
    - Chef de station
    - AdminTenantStation
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        return request.user.role in (
            UserRole.GERANT,
            UserRole.ADMIN_TENANT_STATION,
        )

class CanCreateStationPersonnel(BasePermission):
    """
    Verrouillage strict de la création du personnel station.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # On ne verrouille QUE la création
        if view.action != "create":
            return True

        role_to_create = request.data.get("role")

        # 🔒 AdminTenantStation → UNIQUEMENT GERANT
        if request.user.role == UserRole.ADMIN_TENANT_STATION:
            return role_to_create == UserRole.GERANT

        # 🔒 GERANT → UNIQUEMENT staff station
        if request.user.role == UserRole.GERANT:
            return role_to_create in (
                UserRole.SUPERVISEUR,
                UserRole.POMPISTE,
                UserRole.CAISSIER,
                UserRole.PERSONNEL_ENTRETIEN,
                UserRole.SECURITE,
            )

        # ❌ Tous les autres rôles
        return False