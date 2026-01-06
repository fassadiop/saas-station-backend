# dashboard/views.py
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from core.models import Transaction, Projet, Membre, Cotisation
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from stations.models import Station
from finances_station.models import TransactionStation
from .permissions import IsAdminTenantFinance, IsAdminTenantStation
from .utils.periods import get_period_dates

from dashboard.utils.aggregations import sum_montant

Utilisateur = get_user_model()

class DashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminTenantFinance]

    def get(self, request):
        user = request.user
        tenant = user.tenant

        if not tenant:
            return Response(
                {"detail": "Utilisateur sans tenant"},
                status=403
            )

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        qs_transactions = Transaction.objects.filter(tenant=tenant)

        if start_date:
            qs_transactions = qs_transactions.filter(date__gte=start_date)
        if end_date:
            qs_transactions = qs_transactions.filter(date__lte=end_date)

        total_recettes = (
            qs_transactions
            .filter(type="Recette")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        total_depenses = (
            qs_transactions
            .filter(type="Depense")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        solde = total_recettes - total_depenses

        membres_total = Membre.objects.filter(tenant=tenant).count()

        membres_a_jour = (
            Cotisation.objects
            .filter(membre__tenant=tenant, statut="Payé")
            .values("membre")
            .distinct()
            .count()
        )

        taux_cotisation = (
            round((membres_a_jour / membres_total) * 100, 2)
            if membres_total > 0 else 0
        )

        # (le reste du code métier est CONSERVÉ tel quel)

        return Response({
            "global": {
                "recettes": float(total_recettes),
                "depenses": float(total_depenses),
                "solde": float(solde),
                "taux_cotisation": taux_cotisation,
            },
            # ...
        })


class AdminTenantStationDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminTenantStation]

    def get(self, request):
        station_id = request.query_params.get("station_id")
        period = request.query_params.get("period", "month")

        if not station_id:
            return Response(
                {"detail": "station_id est requis"},
                status=400
            )

        station = get_object_or_404(
            Station,
            id=station_id,
            tenant_id=request.user.tenant_id
        )

        start_date, end_date = get_period_dates(period)

        transactions = TransactionStation.objects.filter(
            tenant_id=request.user.tenant_id,
            station_id=station.id,
            date__range=(start_date, end_date)
        )

        recettes = transactions.filter(type="RECETTE")
        depenses = transactions.filter(type="DEPENSE")

        return Response({
            "station": {
                "id": station.id,
                "nom": station.nom,
                "adresse": station.adresse,
                "active": station.active,
            },
            "periode": {
                "start": start_date,
                "end": end_date,
                "type": period,
            },
            "synthese": {
                "recettes": sum_montant(recettes),
                "depenses": sum_montant(depenses),
                "solde": sum_montant(recettes) - sum_montant(depenses),
                "transactions": transactions.count(),
            },
        })