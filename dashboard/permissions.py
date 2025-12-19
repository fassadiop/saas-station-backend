from rest_framework.permissions import BasePermission


class DashboardPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        return user.role in [
            "SuperAdmin",
            "AdminTenant",
            "Tresorier",
        ]
