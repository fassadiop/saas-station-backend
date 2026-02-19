# saas-backend/stations/permissions.py
from rest_framework.permissions import BasePermission
from accounts.constants import UserRole

class IsStationActor(BasePermission):
    """
    Autorise :
    - Staff station (rattaché à une station)
    - AdminTenantStation (niveau tenant)
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # ✅ Admin tenant station : autorisé sans station
        if user.role == UserRole.ADMIN_TENANT_STATION:
            return True

        # ✅ Acteurs station : station obligatoire
        return user.station is not None

class CanCreateStation(BasePermission):
    """
    Autorise la création et gestion des stations
    uniquement pour SuperAdmin et AdminTenant.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Création / modification station
        if view.action in ["create", "update", "partial_update", "destroy"]:
            return (
                request.user.is_superuser
                or request.user.role == UserRole.ADMIN_TENANT_STATION
            )

        # Lecture : autorisée aux acteurs du tenant
        return True

class CanAccessStations(BasePermission):
    """
    Permission d'accès à la ressource Station.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

         # ✅ AdminTenantStation autorisé
        if request.user.role == UserRole.ADMIN_TENANT_STATION:
            return True

        # ✅ SuperAdmin autorisé
        if request.user.role == UserRole.SUPERADMIN:
            return True

        # Staff station : uniquement s’ils ont une station
        return request.user.station is not None
    
class IsStationAdminOrActor(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        if not user.is_authenticated:
            return False

        # Super admin
        if user.is_superuser or user.role == UserRole.SUPERADMIN:
            return True

        # Admin tenant station → autorisé même sans station directe
        if user.role == UserRole.ADMIN_TENANT_STATION:
            return True

        # Staff station → doit avoir une station
        return user.station is not None
    

class CanAccessStationStructure(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        return request.user.module in (
            "station",
            "admin-tenant-station",
        )

class IsAdminTenantStation(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "ADMIN_TENANT_STATION"
        )
    

class IsGerantOrSuperviseur(BasePermission):
    """
    Autorise uniquement :
    - GERANT
    - SUPERVISEUR
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        return user.role in [
            UserRole.GERANT,
            UserRole.SUPERVISEUR,
        ]
