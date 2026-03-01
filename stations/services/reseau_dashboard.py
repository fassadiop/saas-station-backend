from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from stations.models import RelaisEquipe
from finances_station.models import TransactionStation
from datetime import datetime


def dashboard_reseau(tenant, mois, annee):

    date_debut = datetime(annee, mois, 1)
    if mois == 12:
        date_fin = datetime(annee + 1, 1, 1)
    else:
        date_fin = datetime(annee, mois + 1, 1)

    # ==========================
    # CA total groupe
    # ==========================

    transactions = TransactionStation.objects.filter(
        tenant=tenant,
        date__gte=date_debut,
        date__lt=date_fin,
        type="RECETTE"
    )

    ca_total = transactions.aggregate(
        total=Coalesce(Sum("montant"), 0)
    )["total"]

    # ==========================
    # CA par station
    # ==========================

    ca_par_station = (
        transactions
        .values("station__id", "station__nom")
        .annotate(
            total_ca=Coalesce(Sum("montant"), 0)
        )
        .order_by("-total_ca")
    )

    # ==========================
    # Volume total groupe
    # ==========================

    relais = RelaisEquipe.objects.filter(
        tenant=tenant,
        fin_relais__gte=date_debut,
        fin_relais__lt=date_fin,
        status="TRANSFERE"
    )

    volume_total = sum(
        r.total_volume_vendu for r in relais
    )

    # ==========================
    # STATS
    # ==========================
    transactions = TransactionStation.objects.filter(
        tenant=tenant,
        date__gte=date_debut,
        date__lt=date_fin,
        type="RECETTE"
    )

    stats = transactions.aggregate(
        ca_total=Coalesce(Sum("montant"), 0),
        volume_total=Coalesce(Sum("volume"), 0),
    )

    # ==========================
    # Top 5 / Bottom 5
    # ==========================

    top_5 = list(ca_par_station[:5])
    bottom_5 = list(ca_par_station.order_by("total_ca")[:5])

    return {
        "ca_total": ca_total,
        "volume_total": volume_total,
        "ca_par_station": list(ca_par_station),
        "top_5": top_5,
        "bottom_5": bottom_5,
    }