from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated

from stations.models_depotage.mouvement_stock import MouvementStock
from stations.serializers_depotage.mouvement_stock import MouvementStockSerializer


class MouvementStockViewSet(ReadOnlyModelViewSet):
    """
    Lecture seule.
    Source de vérité du stock.
    """

    serializer_class = MouvementStockSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = MouvementStock.objects.filter(
            tenant=user.tenant
        ).select_related(
            "cuve",
            "cuve__produit",
        )

        # Filtre station (ADMIN)
        station_id = self.request.query_params.get("station_id")
        if station_id:
            qs = qs.filter(station_id=station_id)
        elif hasattr(user, "station") and user.station:
            qs = qs.filter(station=user.station)

        # Filtre produit
        produit = self.request.query_params.get("produit")
        if produit:
            qs = qs.filter(cuve__produit__code=produit)

        # Filtre type mouvement
        type_mouvement = self.request.query_params.get("type_mouvement")
        if type_mouvement:
            qs = qs.filter(type_mouvement=type_mouvement)

        return qs
