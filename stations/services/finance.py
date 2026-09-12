# stations/services/finance.py

from django.db.models import Sum
from finances_station.models import TransactionStation
from stations.models import EncaissementRelais


def appliquer_finance_relais(relais):

    total = (
        EncaissementRelais.objects
        .filter(relais_ilot__relais=relais)
        .aggregate(total=Sum("montant"))
        .get("total")
    )

    total = total or 0

    if total <= 0:
        return

    TransactionStation.objects.create(
        tenant=relais.tenant,
        station=relais.station,
        type="RECETTE",
        montant=total,
        source_type="RelaisEquipe_RECETTE",
        source_id=relais.id,
        date=relais.fin_relais
    )