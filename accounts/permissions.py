from rest_framework.permissions import BasePermission


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
        if request.user.role == "AdminTenant":
            if view.action in ["create", "list", "retrieve", "update", "partial_update"]:
                return True

        # Autres rôles : lecture seule (optionnel)
        if view.action in ["retrieve", "list"]:
            return True

        return False
