# stations/views_dashboard.py

from django.db.models import Sum, F
from django.utils.timezone import localdate
from django.utils import timezone
from calendar import monthrange
from datetime import datetime

from dashboard.permissions import CanAccessStationOperationalDashboard
from finances_station.models import TransactionStation
from .models import FaitStatus, Station, RelaisEquipe
from accounts.constants import UserRole
from stations.models_depotage import Depotage, Cuve

from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response


class StationOperationalDashboardAPIView(APIView):

    permission_classes = [CanAccessStationOperationalDashboard]

    def get(self, request):
        user = request.user
        tenant = user.tenant

        if not tenant:
            return Response(
                {"detail": "Utilisateur non autorisé."},
                status=403
            )

        station_id = request.query_params.get("station_id")

        # ======================================================
        # 🎯 Détermination station
        # ======================================================
        if user.role == UserRole.ADMIN_TENANT_STATION:
            if not station_id:
                return Response(
                    {"detail": "station_id requis"},
                    status=400
                )

            station = Station.objects.filter(
                id=station_id,
                tenant=tenant
            ).first()

            if not station:
                return Response(
                    {"detail": "Station invalide"},
                    status=404
                )
        else:
            station = user.station

        # ======================================================
        # 📅 PARAMÈTRES PÉRIODE (SANS CASSER L’EXISTANT)
        # ======================================================

        annee = request.query_params.get("annee")
        mois = request.query_params.get("mois")

        today = timezone.localdate()

        if annee and mois:
            annee = int(annee)
            mois = int(mois)
        else:
            annee = today.year
            mois = today.month

        from calendar import monthrange
        from datetime import datetime

        last_day = monthrange(annee, mois)[1]

        start_date = timezone.make_aware(
            datetime(annee, mois, 1),
            timezone.get_current_timezone()
        )

        end_date = timezone.make_aware(
            datetime(annee, mois, last_day, 23, 59, 59),
            timezone.get_current_timezone()
        )

        start_30j = timezone.now() - timedelta(days=30)

        # ======================================================
        # 1️⃣ FINANCES
        # ======================================================

        finances_qs = TransactionStation.objects.filter(
            tenant=tenant,
            station=station,
            finance_status="CONFIRMEE"
        )

        # 🔹 Recettes du jour (seulement si mois courant)
        if annee == today.year and mois == today.month:
            recettes_today = finances_qs.filter(
                type="RECETTE",
                date__date=today
            ).aggregate(total=Sum("montant"))["total"] or 0
        else:
            recettes_today = 0

        # 🔹 Recettes du mois sélectionné
        recettes_month = finances_qs.filter(
            type="RECETTE",
            date__range=[start_date, end_date]
        ).aggregate(total=Sum("montant"))["total"] or 0

        # 🔹 Dépenses du mois sélectionné
        depenses_month = finances_qs.filter(
            type="DEPENSE",
            date__range=[start_date, end_date]
        ).aggregate(total=Sum("montant"))["total"] or 0

        # ======================================================
        # 2️⃣ RELAIS (PÉRIODE SÉLECTIONNÉE)
        # ======================================================

        relais_qs = RelaisEquipe.objects.filter(
            tenant=tenant,
            station=station,
            debut_relais__range=[start_date, end_date]
        )

        if user.role == UserRole.GERANT:
            relais_qs = relais_qs.filter(
                status__in=[FaitStatus.CONFIRME, FaitStatus.TRANSFERE]
            )
        else:
            relais_qs = relais_qs.filter(
                status=FaitStatus.TRANSFERE
            )

        relais_stats = {
            "relais_effectues": relais_qs.count(),
            "total_encaisse": (
                relais_qs.aggregate(
                    total=Sum("encaisse_liquide")
                        + Sum("encaisse_carte")
                        + Sum("encaisse_ticket")
                )["total"] or 0
            )
        }

        # ======================================================
        # 3️⃣ ALERTES
        # ======================================================

        alerts = {
            "relais_en_attente": RelaisEquipe.objects.filter(
                tenant=tenant,
                station=station,
                status__in=["BROUILLON", "SOUMIS"]
            ).count()
        }

        # ======================================================
        # 4️⃣ DÉPOTAGE
        # ======================================================

        depotages_qs = Depotage.objects.filter(
            station=station
        )

        # 🔹 Volume du jour (si mois courant)
        if annee == today.year and mois == today.month:
            depotage_volume_today = (
                depotages_qs.filter(date_depotage__date=today)
                .aggregate(total=Sum("quantite_livree"))["total"] or 0
            )
        else:
            depotage_volume_today = 0

        # 🔹 Volume du mois
        depotage_volume_month = (
            depotages_qs.filter(date_depotage__range=[start_date, end_date])
            .aggregate(total=Sum("quantite_livree"))["total"] or 0
        )

        # ======================================================
        # 5️⃣ AUTONOMIE (30 JOURS GLISSANTS)
        # ======================================================

        from stations.models import RelaisIndex

        autonomie = {}

        for produit_code in ["ESSENCE", "GASOIL"]:

            stock_cuve = Cuve.objects.filter(
                station=station,
                produit__code=produit_code
            ).first()

            stock_actuel = stock_cuve.stock_actuel if stock_cuve else 0

            consommation_30j = (
                RelaisIndex.objects.filter(
                    relais__station=station,
                    relais__status=FaitStatus.TRANSFERE,
                    relais__fin_relais__date__gte=start_30j,
                    index_pompe__produit__code=produit_code
                )
                .aggregate(total=Sum(F("index_fin") - F("index_debut")))
                ["total"] or 0
            )

            conso_jour = consommation_30j / 30 if consommation_30j > 0 else 0

            jours_autonomie = (
                round(stock_actuel / conso_jour, 1)
                if conso_jour > 0 else None
            )

            autonomie[produit_code] = {
                "stock_actuel": round(stock_actuel, 2),
                "consommation_jour": round(conso_jour, 2),
                "jours_autonomie": jours_autonomie,
            }

        # ======================================================
        # 🔹 RÉPONSE
        # ======================================================

        return Response({
            "jour": {
                "recettes": recettes_today,
                "solde": recettes_today,
            },
            "mois": {
                "recettes": recettes_month,
                "depenses": depenses_month,
                "solde": recettes_month - depenses_month,
            },
            "relais": relais_stats,
            "alerts": alerts,
            "depotage": {
                "volume_today": depotage_volume_today,
                "volume_month": depotage_volume_month,
            },
            "autonomie": autonomie,
        })