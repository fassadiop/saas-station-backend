# core/permissions.py
from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsSuperAdminOnly(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class IsTenantAdminOnly(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == "AdminTenant"
            and user.tenant is not None
        )


class IsSameTenantOrSuper(BasePermission):
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
    def has_permission(self, request, view):
        user = request.user

        if user.is_superuser:
            return True

        if user.role in ("AdminTenant", "Tresorier"):
            return True

        if user.role == "Collecteur":
            if request.method == "POST":
                return request.data.get("type") == "RECETTE"
            return request.method in SAFE_METHODS

        return request.method in SAFE_METHODS


# from rest_framework.permissions import BasePermission, SAFE_METHODS

# class IsSuperAdmin(BasePermission):
#     def has_permission(self, request, view):
#         return bool(request.user and request.user.is_authenticated and request.user.is_superuser)

# class IsTenantAdmin(BasePermission):
#     """
#     Un AdminTenant ou SuperAdmin peut gérer son tenant.
#     'is_staff' n'est plus jamais utilisé pour éviter les failles multi-tenant.
#     """
#     def has_permission(self, request, view):
#         user = getattr(request, "user", None)
#         if not user or not user.is_authenticated:
#             return False
#         return getattr(user, "role", None) in ("SuperAdmin", "AdminTenant")
    

# class IsTenantAdminOnly(BasePermission):
#     """
#     Seul l'AdminTenant peut gérer les ressources métier (stations, ventes, etc.).
#     Le SuperAdmin est volontairement exclu.
#     """

#     def has_permission(self, request, view):
#         user = getattr(request, "user", None)
#         if not user or not user.is_authenticated:
#             return False

#         return user.role == "AdminTenant" and user.tenant is not None


# class IsTreasurerOrCollecteur(BasePermission):
#     """
#     Autorise les utilisateurs avec role 'Tresorier' ou 'Collecteur'.
#     Protège contre l'accès quand request.user est None.
#     """
#     def has_permission(self, request, view):
#         user = getattr(request, "user", None)
#         if not user or not user.is_authenticated:
#             return False
#         role = getattr(user, "role", None)
#         return role in ('Tresorier', 'Collecteur')

# class IsSameTenantOrSuper(BasePermission):
#     """Autorise l'accès si l'objet appartient au même tenant que l'utilisateur, ou si superuser."""
#     # Note: ceci est une permission d'objet (has_object_permission). Pour lister/filtrer il faut gérer dans get_queryset.
#     def has_object_permission(self, request, view, obj):
#         user = getattr(request, "user", None)
#         if not user:
#             return False
#         if getattr(user, "is_superuser", False):
#             return True
#         user_t = getattr(user, 'tenant', None)
#         obj_t = getattr(obj, 'tenant', None)
#         return user_t is not None and obj_t is not None and user_t.id == obj_t.id

# class IsReadOnlyOrTenantAdmin(BasePermission):
#     """
#     Lecture pour tout utilisateur authentifié, écriture seulement pour TenantAdmin/SuperAdmin.
#     """
#     def has_permission(self, request, view):
#         if request.method in SAFE_METHODS:
#             return bool(request.user and request.user.is_authenticated)
#         return IsTenantAdmin().has_permission(request, view)

# class IsTransactionAllowed(BasePermission):
#     def has_permission(self, request, view):
#         user = request.user

#         # Superuser = full access
#         if user.is_superuser:
#             return True

#         # AdminTenant + Tresorier = accès total aux transactions
#         if user.role in ("AdminTenant", "Tresorier"):
#             return True

#         # Collecteur peut seulement créer des RECETTES
#         if user.role == "Collecteur":
#             if request.method == "POST":
#                 return request.data.get("type") == "RECETTE"
#             return request.method in SAFE_METHODS

#         # Lecteur : uniquement GET
#         return request.method in SAFE_METHODS

# class IsSuperAdmin(BasePermission):
#     def has_permission(self, request, view):
#         return request.user.role == "SuperAdmin"


# # class IsSuperAdminOrTenantAdmin(BasePermission):
# #     """
# #     Autorise l'accès aux SuperAdmin ou AdminTenant
# #     """

# #     def has_permission(self, request, view):
# #         user = request.user
# #         if not user or not user.is_authenticated:
# #             return False

# #         return user.is_superuser or user.role == "AdminTenant"


# class IsSuperAdminOrTenantAdmin(BasePermission):
#     """
#     SuperAdmin (is_superuser) = accès global
#     AdminTenant = accès sur son tenant
#     """

#     def has_permission(self, request, view):
#         user = getattr(request, "user", None)
#         if not user or not user.is_authenticated:
#             return False

#         # SuperAdmin global (sans tenant)
#         if user.is_superuser:
#             return True

#         # Admin métier, nécessite un tenant
#         return user.role == "AdminTenant" and user.tenant is not None


# class IsDashboardUser(BasePermission):
#     """
#     Dashboard accessible au SuperAdmin (global)
#     et à l'AdminTenant (par tenant).
#     """

#     def has_permission(self, request, view):
#         user = getattr(request, "user", None)
#         if not user or not user.is_authenticated:
#             return False

#         if user.is_superuser:
#             return True

#         return user.role == "AdminTenant" and user.tenant is not None


# class IsSuperAdminOnly(BasePermission):
#     """
#     Accès réservé au SuperAdmin.
#     Utilisé pour le dashboard de gouvernance.
#     """

#     def has_permission(self, request, view):
#         user = getattr(request, "user", None)
#         return bool(
#             user
#             and user.is_authenticated
#             and user.is_superuser
#         )


