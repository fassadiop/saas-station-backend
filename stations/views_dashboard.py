# stations/views_dashboard.py

from django.utils import timezone
from calendar import monthrange
from datetime import datetime, timedelta
from django.db.models import Sum, F
from django.db.models.fields import DecimalField

from rest_framework.views import APIView
from rest_framework.response import Response

from dashboard.permissions import CanAccessStationOperationalDashboard
from finances_station.models import TransactionStation
from stations.models_produit import PrixCarburant
from stations.models_depotage import Depotage, Cuve
from stations.models import (
    EncaissementRelais,
    FaitStatus,
    Station,
    RelaisEquipe,
    RelaisIndex,
    DetteStation,
    RelaisEcart,
)
from decimal import Decimal
from accounts.constants import UserRole
from django.db.models.functions import Coalesce


class StationOperationalDashboardAPIView(APIView):

    permission_classes = [CanAccessStationOperationalDashboard]

    def get(self, request):
        user = request.user
        tenant = user.tenant

        if not tenant:
            return Response({"detail": "Utilisateur non autorisé."}, status=403)

        station_id = request.query_params.get("station_id")

        # ======================================================
        # 🎯 STATION
        # ======================================================
        if user.role == UserRole.ADMIN_TENANT_STATION:
            if not station_id:
                return Response({"detail": "station_id requis"}, status=400)

            station = Station.objects.filter(id=station_id, tenant=tenant).first()
            if not station:
                return Response({"detail": "Station invalide"}, status=404)
        else:
            station = user.station

        # ======================================================
        # 📅 PÉRIODE
        # ======================================================
        today = timezone.localdate()

        annee = int(request.query_params.get("annee", today.year))
        mois = int(request.query_params.get("mois", today.month))

        last_day = monthrange(annee, mois)[1]

        start_date = timezone.make_aware(datetime(annee, mois, 1))
        end_date = timezone.make_aware(datetime(annee, mois, last_day, 23, 59, 59))

        start_30j = timezone.now() - timedelta(days=30)

        # ======================================================
        # 1️⃣ FINANCES (SOURCE DE VÉRITÉ)
        # ======================================================
        finances_qs = TransactionStation.objects.filter(
            tenant=tenant,
            station=station,
            finance_status="CONFIRMEE"
        )

        recettes_month = finances_qs.filter(
            type="RECETTE",
            date__range=[start_date, end_date]
        ).aggregate(total=Sum("montant"))["total"] or 0

        depenses_month = finances_qs.filter(
            type="DEPENSE",
            date__range=[start_date, end_date]
        ).aggregate(total=Sum("montant"))["total"] or 0

        recettes_today = 0
        depenses_today = 0

        if annee == today.year and mois == today.month:
            recettes_today = finances_qs.filter(
                type="RECETTE",
                date__date=today
            ).aggregate(total=Sum("montant"))["total"] or 0

            depenses_today = finances_qs.filter(
                type="DEPENSE",
                date__date=today
            ).aggregate(total=Sum("montant"))["total"] or 0

        # ======================================================
        # 2️⃣ RELAIS
        # ======================================================
        relais_qs = RelaisEquipe.objects.filter(
            tenant=tenant,
            station=station,
            fin_relais__range=[start_date, end_date],
            status=FaitStatus.TRANSFERE
        )

        total_encaisse = (
            EncaissementRelais.objects.filter(
                relais_ilot__relais__station=station,
                relais_ilot__relais__status=FaitStatus.TRANSFERE,
                relais_ilot__relais__fin_relais__range=[start_date, end_date]
            ).aggregate(total=Sum("montant"))["total"] or 0
        )

        # ======================================================
        # DETTES CLIENTS
        # ======================================================

        dettes_total = (
            DetteStation.objects.filter(
                tenant=tenant,
                station=station,
                statut__in=[
                    DetteStation.Statut.EN_ATTENTE,
                    DetteStation.Statut.PARTIELLE,
                ]
            )
            .aggregate(
                total=Coalesce(
                    Sum(
                        F("montant_initial") - F("montant_regle")
                    ),
                    0,
                    output_field=DecimalField(
                        max_digits=14,
                        decimal_places=2
                    )
                )
            )["total"] or 0
        )

        # ======================================================
        # ECARTS RELAIS
        # ======================================================

        ecarts = RelaisEcart.objects.filter(
            tenant=tenant,
            relais__station=station,
            relais__status=FaitStatus.TRANSFERE,
            relais__fin_relais__range=[
                start_date,
                end_date
            ]
        )

        ecarts_total = sum(
            e.reste_a_rembourser
            for e in ecarts
        )

        ecarts_rembourses = sum(
            e.montant_rembourse
            for e in ecarts
        )

        # ======================================================
        # 3️⃣ VOLUME CARBURANT (MÉTIER)
        # ======================================================
        volume_qs = (
            RelaisIndex.objects
            .filter(
                relais_ilot__relais__station=station,
                relais_ilot__relais__status=FaitStatus.TRANSFERE,
                relais_ilot__relais__fin_relais__range=[start_date, end_date],
                index_pompe__produit__code__in=["ESSENCE", "GASOIL"]
            )
            .values("index_pompe__produit__code")
            .annotate(
                volume=Coalesce(
                    Sum(F("index_fin") - F("index_debut")),
                    0,
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            )
        )

        volume_map = {row["index_pompe__produit__code"]: row["volume"] for row in volume_qs}

        # ======================================================
        # 4️⃣ PRIX
        # ======================================================
        prix_qs = PrixCarburant.objects.filter(
            station=station,
            actif=True
        ).values("produit__code", "prix_unitaire")

        prix_map = {p["produit__code"]: p["prix_unitaire"] for p in prix_qs}

        volume_essence = volume_map.get("ESSENCE", 0)
        volume_gasoil = volume_map.get("GASOIL", 0)

        prix_essence = prix_map.get("ESSENCE", 0)
        prix_gasoil = prix_map.get("GASOIL", 0)

        ca_essence = volume_essence * prix_essence
        ca_gasoil = volume_gasoil * prix_gasoil

        ca_total = ca_essence + ca_gasoil

        # ======================================================
        # 5️⃣ AUTONOMIE
        # ======================================================
        conso_qs = (
            RelaisIndex.objects
            .filter(
                relais_ilot__relais__station=station,
                relais_ilot__relais__status=FaitStatus.TRANSFERE,
                relais_ilot__relais__fin_relais__gte=start_30j
            )
            .values("index_pompe__produit__code")
            .annotate(
                total=Coalesce(
                    Sum(F("index_fin") - F("index_debut")),
                    0,
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            )
        )

        conso_map = {r["index_pompe__produit__code"]: r["total"] for r in conso_qs}

        stock_qs = (
            Cuve.objects
            .filter(station=station)
            .values("produit__code")
            .annotate(
                stock=Coalesce(
                    Sum("stock_actuel"),
                    0,
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            )
        )

        stock_map = {r["produit__code"]: r["stock"] for r in stock_qs}

        autonomie = {}

        for p in ["ESSENCE", "GASOIL"]:
            conso = conso_map.get(p, 0)
            stock = stock_map.get(p, 0)

            conso_jour = conso / 30 if conso else 0
            jours = round(stock / conso_jour, 1) if conso_jour else None

            autonomie[p] = {
                "stock": stock,
                "conso_jour": round(conso_jour, 2),
                "jours": jours
            }
        # ======================================================
        # CMP par produit
        # ======================================================

        cmp_qs = (
            Depotage.objects
            .filter(
                station=station,
                statut=FaitStatus.TRANSFERE,
                cuve__produit__code__in=["ESSENCE", "GASOIL"]
            )
            .values("cuve__produit__code")
            .annotate(
                total_volume=Coalesce(
                    Sum("quantite_livree"),
                    0,
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                ),
                total_montant=Coalesce(
                    Sum("montant_total"),
                    0,
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            )
        )

        cmp_map = {}

        for row in cmp_qs:
            code = row["cuve__produit__code"]
            volume = row["total_volume"] or 0
            montant = row["total_montant"] or 0

            cmp_map[code] = (montant / volume) if volume > 0 else 0
        
        cmp_essence = cmp_map.get("ESSENCE", 0)
        cmp_gasoil = cmp_map.get("GASOIL", 0)

        # ======================================================
        # Valeur du stock
        # ======================================================

        valeur_stock_essence = (
            autonomie["ESSENCE"]["stock"] * cmp_essence
        )

        valeur_stock_gasoil = (
            autonomie["GASOIL"]["stock"] * cmp_gasoil
        )

        valeur_stock_totale = (
            valeur_stock_essence +
            valeur_stock_gasoil
        )

        # ======================================================
        # Coût des ventes
        # ======================================================

        cout_essence = volume_essence * cmp_essence
        cout_gasoil = volume_gasoil * cmp_gasoil

        # ======================================================
        # Marge réelle
        # ======================================================
        marge_essence = ca_essence - cout_essence
        marge_gasoil = ca_gasoil - cout_gasoil

        marge_totale = marge_essence + marge_gasoil

        tresorerie_nette = recettes_month - depenses_month

        # ======================================================
        # 6️⃣ SCORE
        # ======================================================
        score_tresorerie = 0

        if tresorerie_nette > 10_000_000:
            score_tresorerie = 40
        elif tresorerie_nette > 5_000_000:
            score_tresorerie = 30
        elif tresorerie_nette > 0:
            score_tresorerie = 20
        
        nb_relais = relais_qs.count()

        if nb_relais >= 20:
            score_activite = 20
        elif nb_relais >= 10:
            score_activite = 15
        elif nb_relais >= 5:
            score_activite = 10
        else:
            score_activite = 5

        min_auto = min(
            autonomie["ESSENCE"]["jours"] or 0,
            autonomie["GASOIL"]["jours"] or 0
        )

        if min_auto >= 15:
            score_autonomie = 20
        elif min_auto >= 10:
            score_autonomie = 15
        elif min_auto >= 5:
            score_autonomie = 10
        else:
            score_autonomie = 0

        score_stock = 0

        if valeur_stock_totale >= 30_000_000:
            score_stock = 20
        elif valeur_stock_totale >= 20_000_000:
            score_stock = 15
        elif valeur_stock_totale >= 10_000_000:
            score_stock = 10
        else:
            score_stock = 5

        score_ecarts = 20

        if ecarts_total > marge_totale:
            score_ecarts = 0
        elif ecarts_total > marge_totale * Decimal("0.5"):
            score_ecarts = 10

        health_score = score_stock + score_activite + score_autonomie + score_tresorerie + score_ecarts

        niveau = (
            "EXCELLENTE" if health_score >= 80 else
            "BONNE" if health_score >= 60 else
            "FRAGILE" if health_score >= 40 else
            "CRITIQUE"
        )

        # ======================================================
        # 🔹 RESPONSE CLEAN
        # ======================================================
        return Response({
            "finances": {
                "recettes": recettes_month,
                "depenses": depenses_month,
                "tresorerie_nette": tresorerie_nette
            },
            "carburant": {
                "essence": {
                    "volume": volume_essence,
                    "prix": prix_essence,
                    "ca": ca_essence,
                    "cmp": cmp_essence,
                    "cout": cout_essence,
                    "marge": marge_essence,
                },
                "gasoil": {
                    "volume": volume_gasoil,
                    "prix": prix_gasoil,
                    "ca": ca_gasoil,
                    "cmp": cmp_gasoil,
                    "cout": cout_gasoil,
                    "marge": marge_gasoil,
                },
                "total": {
                    "ca": ca_total,
                    "cout": cout_essence + cout_gasoil,
                    "marge": marge_totale
                }
            },
            "stock": {
                "essence": {
                    "quantite": autonomie["ESSENCE"]["stock"],
                    "valeur": valeur_stock_essence,
                },
                "gasoil": {
                    "quantite": autonomie["GASOIL"]["stock"],
                    "valeur": valeur_stock_gasoil,
                },
                "total": {
                    "quantite": (
                        autonomie["ESSENCE"]["stock"]
                        + autonomie["GASOIL"]["stock"]
                    ),
                    "valeur": valeur_stock_totale
                }
            },
            "relais": {
                "count": relais_qs.count(),
                "encaisse": total_encaisse
            },
            "dettes": {
                "total": dettes_total
            },

            "ecarts": {
                "total": ecarts_total,
                "ecarts_total": ecarts_total,
                "ecarts_rembourses": ecarts_rembourses,
            },
            "autonomie": autonomie,
            "performance": {
                "score": health_score,
                "niveau": niveau,
                "details": {
                    "tresorerie": score_tresorerie,
                    "activite": score_activite,
                    "autonomie": score_autonomie,
                    "stock": score_stock,
                    "ecarts": score_ecarts,
                }
            }
        })