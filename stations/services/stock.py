from django.db import transaction
from stations.models_depotage.cuve import Cuve
from rest_framework.exceptions import ValidationError
from stations.models_depotage.mouvement_stock import MouvementStock

@transaction.atomic
def appliquer_stock_relais(relais):
    if relais.stock_applique:
        return

    station = relais.station

    # ESSENCE
    if relais.volume_essence_vendu > 0:
        cuve_essence = Cuve.objects.select_for_update().get(
            station=station,
            produit="ESSENCE"
        )
        cuve_essence.stock_actuel -= relais.volume_essence_vendu
        cuve_essence.save(update_fields=["stock_actuel"])

    # GASOIL
    if relais.volume_gasoil_vendu > 0:
        cuve_gasoil = Cuve.objects.select_for_update().get(
            station=station,
            produit="GASOIL"
        )
        cuve_gasoil.stock_actuel -= relais.volume_gasoil_vendu
        cuve_gasoil.save(update_fields=["stock_actuel"])

    relais.stock_applique = True
    relais.save(update_fields=["stock_applique"])

@transaction.atomic
def appliquer_stock_depotage(depotage, user):
    """
    Applique l'impact stock d'un dépotage CONFIRME.
    Idempotent via depotage.stock_applique.
    """

    if depotage.stock_applique:
        raise ValidationError("Le stock a déjà été appliqué pour ce dépotage.")

    if depotage.statut != "CONFIRME":
        raise ValidationError("Le dépotage doit être confirmé avant transfert.")

    # Verrouillage cuve
    try:
        cuve = Cuve.objects.select_for_update().get(
            station=depotage.station,
            produit=depotage.produit,
            actif=True,
        )
    except Cuve.DoesNotExist:
        raise ValidationError(
            "Aucune cuve active trouvée pour ce produit."
        )

    # Volume réel accepté
    volume = depotage.quantite_acceptee

    if volume <= 0:
        raise ValidationError("Quantité acceptée invalide.")

    # Mouvement de stock (SOURCE DE VÉRITÉ)
    MouvementStock.objects.create(
        tenant=depotage.station.tenant,
        station=depotage.station,
        cuve=cuve,
        type_mouvement=MouvementStock.MOUVEMENT_ENTREE,
        quantite=depotage.quantite_acceptee,
        source_type="DEPOTAGE",
        source_id=depotage.id,
        date_mouvement=depotage.date_depotage,
    )

    # Mise à jour stock cuve
    cuve.stock_actuel = cuve.stock_actuel + volume
    cuve.save(update_fields=["stock_actuel", "updated_at"])

    # Marquage idempotence
    depotage.stock_applique = True
    depotage.statut = "TRANSFERE"
    depotage.save(update_fields=["stock_applique", "statut", "updated_at"])

    return cuve