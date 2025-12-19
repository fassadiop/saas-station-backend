from rest_framework.permissions import BasePermission


class TenantPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        if user.role == "SuperAdmin":
            return True

        if view.action == "list" and user.role == "AdminTenant":
            return True

        if view.action == "retrieve" and user.role == "AdminTenant":
            return True

        return False
    

class IsStationActor(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, "station")
            and request.user.station is not None
        )
