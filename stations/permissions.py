from rest_framework.permissions import BasePermission

class IsStationActor(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "station")
            and request.user.station is not None
        )


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
                or request.user.role == "AdminTenant"
            )

        # Lecture : autorisée aux acteurs du tenant
        return True
