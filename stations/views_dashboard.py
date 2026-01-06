from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField
from django.utils.timezone import localdate
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response

from dashboard.permissions import CanAccessStationOperationalDashboard
from finances_station.models import TransactionStation
from .models import FaitStatus, Station, VenteCarburant, RelaisEquipe
from accounts.constants import UserRole
from stations.models_depotage import Depotage

from datetime import date, timedelta
from django.db.models import Sum, Count
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import F, ExpressionWrapper, DecimalField

from stations.models_depotage import Cuve


class StationOperationalDashboardAPIView(APIView):
    """
    Dashboard OPÉRATIONNEL
    - Chef de station : données de SA station
    - ADMIN_TENANT_STATION : données AGRÉGÉES (toutes stations)
    """

    permission_classes = [CanAccessStationOperationalDashboard]

    def get(self, request):
        user = request.user
        tenant = user.tenant

        station_id = request.query_params.get("station_id")

        if not tenant:
            return Response(
                {"detail": "Utilisateur non autorisé."},
                status=403
            )

        # 🎯 Détermination du périmètre station
        if user.role == UserRole.ADMIN_TENANT_STATION:
            if not station_id:
                return Response(
                    {"detail": "station_id requis pour AdminTenantStation"},
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
        
        
        today = localdate()
        first_day_month = today.replace(day=1)
        start = today.replace(day=1)
        end = today

        # ======================================================
        # 1️⃣ FINANCES — SOURCE DE VÉRITÉ
        # ======================================================
        finances_qs = TransactionStation.objects.filter(
            tenant=tenant
        )

        if station is not None:
            finances_qs = finances_qs.filter(station=station)

        # ======================================================
        # 2️⃣ GOUVERNANCE FINANCES PAR RÔLE
        # ======================================================
        if user.role == UserRole.GERANT:
            # Le gérant voit PROVISOIRE + CONFIRMEE
            finances_qs = finances_qs.filter(
                finance_status__in=["PROVISOIRE", "CONFIRMEE"]
            )

        elif user.role in (
            UserRole.SUPERVISEUR,
            UserRole.POMPISTE,
            UserRole.CAISSIER,
            UserRole.PERSONNEL_ENTRETIEN,
            UserRole.SECURITE,
        ):
            # ❌ Aucun accès aux montants financiers
            finances_qs = TransactionStation.objects.none()

        # ======================================================
        # 🔐 QUERYSET FINANCIER OFFICIEL (KPI UNIQUEMENT)
        # ======================================================

        today = timezone.localdate()
        first_day_month = today.replace(day=1)

        finances_kpi_qs = TransactionStation.objects.filter(
            tenant=tenant,
            finance_status="CONFIRMEE"
        )

        if station is not None:
            finances_kpi_qs = finances_kpi_qs.filter(station=station)

        # ======================================================
        # 2️⃣ BIS — AGRÉGATS FINANCIERS (OBLIGATOIRES)
        # ======================================================
        recettes_today = finances_kpi_qs.filter(
            type="RECETTE",
            date__date=today
        ).aggregate(
            total=Sum("montant"),
            count=Count("id")
        )

        recettes_month = finances_kpi_qs.filter(
            type="RECETTE",
            date__date__gte=first_day_month
        ).aggregate(total=Sum("montant"))["total"] or 0

        depenses_month = finances_kpi_qs.filter(
            type="DEPENSE",
            date__date__gte=first_day_month
        ).aggregate(total=Sum("montant"))["total"] or 0

        recettes_by_source = (
            finances_kpi_qs.filter(
                type="RECETTE",
                date__date=today
            )
            .values("source_type")
            .annotate(total=Sum("montant"))
        )

        # ======================================================
        # 2️⃣ VOLUMES CARBURANT (STATION)
        # ======================================================
        ventes_qs = VenteCarburant.objects.filter(
            tenant=tenant,
            status=FaitStatus.TRANSFERE,
            date__date=today
        )
        if station is not None:
            ventes_qs = ventes_qs.filter(station=station)

        volumes_carburant = (
            ventes_qs
            .values("produit")
            .annotate(volume=Sum("volume"))
        )

        # ======================================================
        # 3️⃣ RELAIS D’ÉQUIPE — CONTRÔLE OPÉRATIONNEL
        # ======================================================
        relais_qs = RelaisEquipe.objects.filter(
            tenant=tenant,
            status=FaitStatus.TRANSFERE,
            debut_relais__date=today
        )
        if station is not None:
            relais_qs = relais_qs.filter(station=station)

        relais_stats = {
            "relais_effectues": relais_qs.count(),
            "total_encaisse": (
                relais_qs.aggregate(
                    total=
                        Sum("encaisse_liquide") +
                        Sum("encaisse_carte") +
                        Sum("encaisse_ticket_essence") +
                        Sum("encaisse_ticket_gasoil")
                )["total"] or 0
            )
        }

        # ======================================================
        # 4️⃣ ALERTES OPÉRATIONNELLES
        # ======================================================
        ventes_alerts_qs = VenteCarburant.objects.filter(
            tenant=tenant,
            status__in=["BROUILLON", "SOUMIS"]
        )
        relais_alerts_qs = RelaisEquipe.objects.filter(
            tenant=tenant,
            status__in=["BROUILLON", "SOUMIS"]
        )

        if station is not None:
            ventes_alerts_qs = ventes_alerts_qs.filter(station=station)
            relais_alerts_qs = relais_alerts_qs.filter(station=station)

        alerts = {
            "ventes_en_attente": ventes_alerts_qs.count(),
            "relais_en_attente": relais_alerts_qs.count(),
        }

        # ======================================================
        # 5️⃣ DERNIÈRES OPÉRATIONS FINANCIÈRES
        # ======================================================
        last_operations = (
            finances_qs
            .order_by("-date")[:10]
            .values(
                "id",
                "date",
                "type",
                "source_type",
                "montant",
                "finance_status",
                "station__nom",
                "station__departement",
                "station__region",
            ).annotate(
                station_nom=F("station__nom"),
                station_departement=F("station__departement"),
                station_region=F("station__region"),
            )
        )

        # ======================================================
        # DÉPOTAGE — VOLUMES & MONTANTS
        # ======================================================

        # Base queryset dépotages (périmètre station / tenant)
        depotages_qs = Depotage.objects.filter(
            station__tenant=tenant
        )

        if station is not None:
            depotages_qs = depotages_qs.filter(station=station)

        # -----------------------
        # Volumes dépotés - JOUR
        # -----------------------
        depotage_volume_today = (
            depotages_qs.filter(date_depotage__date=today)
            .aggregate(total=Sum("quantite_livree"))["total"] or 0
        )

        # -----------------------
        # Volumes dépotés - MOIS
        # -----------------------
        depotage_volume_month = (
            depotages_qs.filter(date_depotage__date__gte=first_day_month)
            .aggregate(total=Sum("quantite_livree"))["total"] or 0
        )

        # -----------------------
        # Dépenses dépotage - MOIS
        # ⚠️ SOURCE DE VÉRITÉ = FINANCE
        # -----------------------
        depotage_depense_month = (
            TransactionStation.objects.filter(
                tenant=tenant,
                source_type="DEPOTAGE",
                finance_status="CONFIRMEE",
                date__date__gte=first_day_month,
                **({"station": station} if station is not None else {})
            )
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        # ======================================================
        # 8️⃣ DÉPOTAGE — ÉCARTS & ALERTES
        # ======================================================
    
        depotages_with_ecart_qs = depotages_qs.filter(
            date_depotage__date=today
        ).annotate(
            ecart=ExpressionWrapper(
                F("quantite_livree") - F("variation_cuve"),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        )

        # -----------------------
        # Alertes critiques (> 200 L)
        # -----------------------
        depotage_alerts = depotages_with_ecart_qs.filter(ecart__gt=200).count()

        depotage_non_justifies = depotages_with_ecart_qs.filter(
            ecart__gt=200,
            justification__isnull=True
        ).count()


        start_30j = today - timedelta(days=30)
        autonomie = {}

        for produit in ["ESSENCE", "GASOIL"]:
            # =========================
            # 1️⃣ Stock actuel
            # =========================
            cuve = Cuve.objects.filter(
                station=station,
                produit=produit
            ).first()

            stock_actuel = cuve.stock_actuel if cuve else 0

            # =========================
            # 2️⃣ Consommation 30 jours
            # =========================
            if produit == "ESSENCE":
                conso_expr = ExpressionWrapper(
                    F("jauge_essence_debut") - F("jauge_essence_fin"),
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                )
            else:
                conso_expr = ExpressionWrapper(
                    F("jauge_gasoil_debut") - F("jauge_gasoil_fin"),
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                )

            consommation_30j = (
                RelaisEquipe.objects.filter(
                    station=station,
                    status="TRANSFERE",
                    fin_relais__date__gte=start_30j
                )
                .annotate(consommation=conso_expr)
                .aggregate(total=Sum("consommation"))["total"] or 0
            )

            # =========================
            # 3️⃣ Calcul autonomie
            # =========================
            conso_jour = consommation_30j / 30 if consommation_30j > 0 else 0

            jours_autonomie = (
                round(stock_actuel / conso_jour, 1)
                if conso_jour > 0 else None
            )

            autonomie[produit] = {
                "stock_actuel": round(stock_actuel, 2),
                "consommation_jour": round(conso_jour, 2),
                "jours_autonomie": jours_autonomie,
            }

        # ======================================================
        # 6️⃣ RÉPONSE FINALE (INCHANGÉE)
        # ======================================================
        data = {
            "jour": {
                "recettes": recettes_today["total"] or 0,
                "depenses": 0,
                "solde": recettes_today["total"] or 0,
            },
            "mois": {
                "recettes": recettes_month,
                "depenses": depenses_month,
                "solde": recettes_month - depenses_month,
            },
            "relais": relais_stats,
            "alerts": alerts,
            "last_operations": list(last_operations),
            
            "depotage": {
                "volume_today": depotage_volume_today,
                "volume_month": depotage_volume_month,
                "depense_month": depotage_depense_month,
                "alertes_ecart": depotage_alerts,
            },

            "autonomie": autonomie
        }
        return Response(data)

        
