from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum
from django.db.models.functions import TruncDate

from finances_station.models import TransactionStation
from stations.models import RelaisEquipe
from stations.permissions import IsStationActor
from django.utils.timezone import now
from django.utils import timezone
from rest_framework.generics import ListAPIView

from stations.serializers import RelaisEquipeListSerializer

class StationDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsStationActor]

    def get(self, request):
        user = request.user

        if not user.station:
            return Response(
                {"detail": "Utilisateur sans station"},
                status=403
            )

        today = timezone.localdate()
        month_start = today.replace(day=1)

        qs = TransactionStation.objects.filter(
            station=user.station
        )

        # =========================
        # KPI JOUR
        # =========================
        qs_jour = qs.filter(date__date=today)

        recettes_jour = qs_jour.filter(
            type="RECETTE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        depenses_jour = qs_jour.filter(
            type="DEPENSE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        # =========================
        # KPI MOIS COURANT
        # =========================
        qs_mois = qs.filter(date__date__gte=month_start)

        recettes_mois = qs_mois.filter(
            type="RECETTE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        depenses_mois = qs_mois.filter(
            type="DEPENSE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        # =========================
        # ÉVOLUTION JOUR PAR JOUR (MOIS)
        # =========================
        evolution_qs = (
            qs_mois
            .annotate(jour=TruncDate("date"))
            .values("jour", "type")
            .annotate(total=Sum("montant"))
            .order_by("jour")
        )

        evolution_map = {}

        for e in evolution_qs:
            d = e["jour"].isoformat()
            evolution_map.setdefault(d, {
                "date": d,
                "recettes": 0,
                "depenses": 0,
            })

            if e["type"] == "RECETTE":
                evolution_map[d]["recettes"] = float(e["total"])
            else:
                evolution_map[d]["depenses"] = float(e["total"])

        # =========================
        # RÉPONSE FINALE (CONTRAT API)
        # =========================
        return Response({
            "jour": {
                "recettes": float(recettes_jour),
                "depenses": float(depenses_jour),
                "solde": float(recettes_jour - depenses_jour),
            },
            "mois": {
                "recettes": float(recettes_mois),
                "depenses": float(depenses_mois),
                "solde": float(recettes_mois - depenses_mois),
            },
            "evolution": list(evolution_map.values()),
            "meta": {
                "station_id": user.station_id,
                "has_data": qs.exists(),
            }
        })
    
class StationRelaisListView(ListAPIView):
    permission_classes = [IsAuthenticated, IsStationActor]
    serializer_class = RelaisEquipeListSerializer

    def get_queryset(self):
        user = self.request.user

        return (
            RelaisEquipe.objects
            .filter(station=user.station)
            .order_by("-debut_relais")
        )