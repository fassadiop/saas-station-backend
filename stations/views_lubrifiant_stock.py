# stations/views_lubrifiant_stock.py

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from stations.models_lubrifiant import (
    MouvementStockLubrifiant,
    StockLubrifiant,
)
from stations.serializers_lubrifiant_stock import (
    MouvementStockLubrifiantActionSerializer,
    MouvementStockLubrifiantSerializer,
    StockLubrifiantSerializer,
)
from stations.services.stock_lubrifiant import (
    entree_stock_lubrifiant,
    sortie_stock_lubrifiant,
)


class StockLubrifiantViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consultation du stock de lubrifiants.

    - Lecture accessible aux utilisateurs authentifiés du tenant.
    - Le stock_actuel est géré exclusivement par les services métier.
    - Isolation stricte par tenant.
    """

    serializer_class = StockLubrifiantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, "tenant", None)

        if tenant is None:
            return StockLubrifiant.objects.none()

        queryset = (
            StockLubrifiant.objects
            .filter(tenant=tenant)
            .select_related(
                "station",
                "lubrifiant",
            )
        )

        station_id = self.request.query_params.get("station")

        if station_id:
            queryset = queryset.filter(station_id=station_id)

        return queryset.order_by(
            "station__nom",
            "lubrifiant__code",
        )


class MouvementStockLubrifiantViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consultation et opérations métier sur les mouvements
    de stock des lubrifiants.

    Consultation :
        utilisateurs authentifiés du tenant.

    Entrée / sortie :
        GERANT
        SUPERVISEUR

    Les opérations de stock passent obligatoirement par
    les services métier.
    """

    serializer_class = MouvementStockLubrifiantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, "tenant", None)

        if tenant is None:
            return MouvementStockLubrifiant.objects.none()

        return (
            MouvementStockLubrifiant.objects
            .filter(tenant=tenant)
            .select_related(
                "station",
                "lubrifiant",
            )
            .order_by(
                "-date_mouvement",
                "-id",
            )
        )

    def _can_manage_stock(self):
        return getattr(self.request.user, "role", None) in [
            "GERANT",
            "SUPERVISEUR",
        ]

    def _get_action_serializer(self, request):
        return MouvementStockLubrifiantActionSerializer(
            data=request.data,
            context={"request": request},
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="entree",
    )
    def entree(self, request):
        """
        Enregistre une entrée de stock de lubrifiant.
        """

        if not self._can_manage_stock():
            return Response(
                {
                    "detail": (
                        "Seul le gérant ou le superviseur "
                        "peut effectuer une entrée de stock."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self._get_action_serializer(request)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        mouvement = entree_stock_lubrifiant(
            tenant=request.user.tenant,
            station=data["station"],
            lubrifiant=data["lubrifiant"],
            quantite=data["quantite"],
            source_type="ENTREE_STOCK_MANUELLE",
            source_id=request.user.id,
            date_mouvement=data.get("date_mouvement"),
        )

        response_serializer = MouvementStockLubrifiantSerializer(
            mouvement,
            context={"request": request},
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="sortie",
    )
    def sortie(self, request):
        """
        Enregistre une sortie de stock de lubrifiant.

        Le service métier contrôle automatiquement
        la disponibilité du stock.
        """

        if not self._can_manage_stock():
            return Response(
                {
                    "detail": (
                        "Seul le gérant ou le superviseur "
                        "peut effectuer une sortie de stock."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self._get_action_serializer(request)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        mouvement = sortie_stock_lubrifiant(
            tenant=request.user.tenant,
            station=data["station"],
            lubrifiant=data["lubrifiant"],
            quantite=data["quantite"],
            source_type="SORTIE_STOCK_MANUELLE",
            source_id=request.user.id,
            date_mouvement=data.get("date_mouvement"),
        )

        response_serializer = MouvementStockLubrifiantSerializer(
            mouvement,
            context={"request": request},
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )