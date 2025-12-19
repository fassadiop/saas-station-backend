from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from finances_station.models import TransactionStation


class FinanceDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        qs = TransactionStation.objects.filter(
            tenant_id=user.tenant_id
        )

        # Chef de station → vue limitée
        if getattr(user, "station_id", None):
            qs = qs.filter(station_id=user.station_id)

        recettes = qs.filter(
            type="RECETTE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        depenses = qs.filter(
            type="DEPENSE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        par_station = qs.values(
            "station_id",
            "station__nom"
        ).annotate(
            recettes=Sum("montant", filter=Q(type="RECETTE")),
            depenses=Sum("montant", filter=Q(type="DEPENSE")),
        )

        return Response({
            "global": {
                "recettes": recettes,
                "depenses": depenses,
                "resultat": recettes - depenses,
            },
            "par_station": list(par_station),
        })
