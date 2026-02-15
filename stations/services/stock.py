# stations/services/stock.py

from django.db import transaction
from stations.models_depotage.cuve import Cuve, CuveStatus
from rest_framework.exceptions import ValidationError
from stations.models_depotage.mouvement_stock import MouvementStock

@transaction.atomic
def appliquer_stock_relais(relais):

    if relais.stock_applique:
        return

    for ligne in relais.produits.select_for_update():

        volume = ligne.volume_vendu

        if volume <= 0:
            continue

        cuve = Cuve.objects.select_for_update().get(
            station=relais.station,
            produit=ligne.produit,
            statut=CuveStatus.ACTIVE,
        )

        if cuve.stock_actuel < volume:
            raise ValidationError(
                f"Stock insuffisant pour {ligne.produit.code}"
            )

        cuve.stock_actuel -= volume
        cuve.save(update_fields=["stock_actuel", "updated_at"])

        MouvementStock.objects.create(
            tenant=relais.tenant,
            station=relais.station,
            cuve=cuve,
            type_mouvement=MouvementStock.MOUVEMENT_SORTIE,
            quantite=volume,
            source_type="RELAIS",
            source_id=relais.id,
            date_mouvement=relais.fin_relais,
        )

    relais.stock_applique = True
    relais.save(update_fields=["stock_applique"])



@transaction.atomic
def appliquer_stock_depotage(depotage, user):

    if depotage.stock_applique:
        raise ValidationError("Le stock a déjà été appliqué.")

    if depotage.statut != "CONFIRME":
        raise ValidationError("Le dépotage doit être confirmé.")

    cuve = Cuve.objects.select_for_update().get(id=depotage.cuve_id)

    if cuve.statut not in [
        CuveStatus.STANDBY,
        CuveStatus.ACTIVE,
    ]:
        raise ValidationError("La cuve n'est pas disponible pour dépotage.")

    volume = depotage.quantite_acceptee

    if volume <= 0:
        raise ValidationError("Quantité acceptée invalide.")

    # Mouvement stock (source de vérité)
    MouvementStock.objects.create(
        tenant=depotage.tenant,
        station=depotage.station,
        cuve=cuve,
        type_mouvement=MouvementStock.MOUVEMENT_ENTREE,
        quantite=volume,
        source_type="DEPOTAGE",
        source_id=depotage.id,
        date_mouvement=depotage.date_depotage,
    )

    cuve.stock_actuel += volume
    cuve.save(update_fields=["stock_actuel", "updated_at"])

    depotage.stock_applique = True
    depotage.statut = "TRANSFERE"
    depotage.save(update_fields=["stock_applique", "statut", "updated_at"])

    return cuve
