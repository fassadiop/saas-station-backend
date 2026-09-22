# stations/views_lubrifiant.py

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction

from stations.models import Station
from stations.models_lubrifiant import StockLubrifiant
from stations.models_produit import Lubrifiants
from stations.serializers_lubrifiant import LubrifiantSerializer


class LubrifiantViewSet(viewsets.ModelViewSet):
    """
    Gestion du catalogue des lubrifiants.

    - Lecture :
        utilisateurs authentifiés du tenant.

    - Création / modification / désactivation / suppression :
        GERANT
        ADMIN_TENANT_STATION

    - SUPERVISEUR :
        consultation uniquement.

    - Isolation stricte par tenant.
    """

    serializer_class = LubrifiantSerializer
    permission_classes = [IsAuthenticated]

    http_method_names = ["get", "post", "patch", "delete"]

    # ==================================================
    # QUERYSET
    # ==================================================

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, "tenant", None)

        if tenant is None:
            return Lubrifiants.objects.none()

        return (
            Lubrifiants.objects
            .filter(tenant=tenant)
            .order_by("code")
        )

    # ==================================================
    # PERMISSIONS METIER
    # ==================================================

    def _can_manage_lubrifiants(self):
        """
        Rôles autorisés à gérer le catalogue des lubrifiants.
        """

        return getattr(self.request.user, "role", None) in [
            "ADMIN_TENANT_STATION",
            "GERANT",
            "SUPERVISEUR",
        ]

    # ==================================================
    # CREATION
    # ==================================================

    def create(self, request, *args, **kwargs):
        if not self._can_manage_lubrifiants():
            return Response(
                {
                    "detail": (
                        "Seul le gérant ou l'administrateur "
                        "tenant/station peut créer un lubrifiant."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        Le tenant est toujours déterminé côté serveur.
        Il n'est jamais fourni par le client.

        Lors de la création d'un lubrifiant, une ligne de stock
        à zéro est créée pour chaque station active du tenant.
        """

        tenant = self.request.user.tenant

        with transaction.atomic():
            lubrifiant = serializer.save(tenant=tenant)

            stations = Station.objects.filter(
                tenant=tenant,
                active=True,
            )

            StockLubrifiant.objects.bulk_create(
                [
                    StockLubrifiant(
                        tenant=tenant,
                        station=station,
                        lubrifiant=lubrifiant,
                        stock_actuel=0,
                    )
                    for station in stations
                ],
                ignore_conflicts=True,
            )

    # ==================================================
    # MODIFICATION COMPLETE
    # ==================================================

    def update(self, request, *args, **kwargs):
        if not self._can_manage_lubrifiants():
            return Response(
                {
                    "detail": (
                        "Seul le gérant ou l'administrateur "
                        "tenant/station peut modifier un lubrifiant."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().update(request, *args, **kwargs)

    # ==================================================
    # MODIFICATION PARTIELLE
    # ==================================================

    def partial_update(self, request, *args, **kwargs):
        if not self._can_manage_lubrifiants():
            return Response(
                {
                    "detail": (
                        "Seul le gérant ou l'administrateur "
                        "tenant/station peut modifier un lubrifiant."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().partial_update(request, *args, **kwargs)

    # ==================================================
    # SUPPRESSION
    # ==================================================

    def destroy(self, request, *args, **kwargs):
        if not self._can_manage_lubrifiants():
            return Response(
                {
                    "detail": (
                        "Seul le gérant ou l'administrateur "
                        "tenant/station peut supprimer un lubrifiant."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        lubrifiant = self.get_object()

        # --------------------------------------------------
        # Protection contre les suppressions destructives
        # --------------------------------------------------

        if lubrifiant.stocks.exists():
            return Response(
                {
                    "detail": (
                        "Ce lubrifiant ne peut pas être supprimé "
                        "car il possède un historique de stock."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if lubrifiant.mouvements_stock.exists():
            return Response(
                {
                    "detail": (
                        "Ce lubrifiant ne peut pas être supprimé "
                        "car il possède un historique de mouvements."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if lubrifiant.ventes.exists():
            return Response(
                {
                    "detail": (
                        "Ce lubrifiant ne peut pas être supprimé "
                        "car il possède un historique de ventes."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().destroy(request, *args, **kwargs)

    # ==================================================
    # DESACTIVATION
    # ==================================================

    @action(
        detail=True,
        methods=["post"],
        url_path="desactiver",
    )
    def desactiver(self, request, pk=None):
        if not self._can_manage_lubrifiants():
            return Response(
                {
                    "detail": (
                        "Seul le gérant ou l'administrateur "
                        "tenant/station peut désactiver un lubrifiant."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        lubrifiant = self.get_object()

        if not lubrifiant.actif:
            return Response(
                {
                    "detail": "Ce lubrifiant est déjà désactivé."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lubrifiant.actif = False
        lubrifiant.save(
            update_fields=["actif", "updated_at"]
        )

        serializer = self.get_serializer(lubrifiant)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )