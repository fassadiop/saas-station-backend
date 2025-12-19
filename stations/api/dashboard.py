from datetime import datetime, timedelta
from django.db.models import Sum
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from finances_station.models import TransactionStation
from stations.permissions import IsStationActor


class StationDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStationActor]

    def get(self, request):
        user = request.user

        today = now().date()
        start_today = datetime.combine(today, datetime.min.time())
        end_today = datetime.combine(today, datetime.max.time())

        month_start = today.replace(day=1)
        start_month = datetime.combine(month_start, datetime.min.time())

        qs = TransactionStation.objects.filter(
            tenant_id=user.tenant_id,
            station_id=user.station_id,
        )

        # 🔹 JOUR
        recettes_jour = qs.filter(
            type="RECETTE",
            date__range=(start_today, end_today)
        ).aggregate(total=Sum("montant"))["total"] or 0

        depenses_jour = qs.filter(
            type="DEPENSE",
            date__range=(start_today, end_today)
        ).aggregate(total=Sum("montant"))["total"] or 0

        # 🔹 MOIS
        recettes_mois = qs.filter(
            type="RECETTE",
            date__gte=start_month
        ).aggregate(total=Sum("montant"))["total"] or 0

        depenses_mois = qs.filter(
            type="DEPENSE",
            date__gte=start_month
        ).aggregate(total=Sum("montant"))["total"] or 0

        # 🔹 Répartition par activité
        repartition = qs.filter(
            type="RECETTE"
        ).values("source_type").annotate(
            total=Sum("montant")
        )

        # 🔹 Dernières transactions
        derniers = qs.order_by("-date")[:10]

        return Response({
            "jour": {
                "recettes": recettes_jour,
                "depenses": depenses_jour,
                "solde": recettes_jour - depenses_jour,
            },
            "mois": {
                "recettes": recettes_mois,
                "depenses": depenses_mois,
                "solde": recettes_mois - depenses_mois,
            },
            "repartition": list(repartition),
            "dernieres_transactions": [
                {
                    "date": t.date,
                    "type": t.type,
                    "source_type": t.source_type,
                    "montant": t.montant,
                }
                for t in derniers
            ],
        })
