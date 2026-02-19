from rest_framework.permissions import BasePermission
from accounts.constants import UserRole


class IsSuperAdmin(BasePermission):
    """
    Permission réservée au SuperAdmin SaaS.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.SUPERADMIN
        )
