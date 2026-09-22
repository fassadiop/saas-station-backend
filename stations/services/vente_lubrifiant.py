# stations/services/vente_lubrifiant.py

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from stations.models_lubrifiant.vente import VenteLubrifiant

from stations.services.stock_lubrifiant import (
    sortie_stock_lubrifiant,
)


# ============================================================
# VENTE LUBRIFIANT
# ============================================================

@transaction.atomic
def vendre_lubrifiant(
    *,
    tenant,
    station,
    lubrifiant,
    quantite,
    relais=None,
    created_by=None,
    date_vente=None,
):
    """
    Enregistre une vente de lubrifiant et applique
    automatiquement la sortie de stock.

    La vente et la sortie de stock sont réalisées
    dans une seule transaction.

    Si le stock est insuffisant :
        - la sortie est refusée ;
        - la vente est annulée ;
        - aucun mouvement de stock n'est conservé.
    """

    quantite = Decimal(quantite)

    if quantite <= 0:
        raise ValidationError(
            "La quantité vendue doit être supérieure à zéro."
        )

    # --------------------------------------------------------
    # VÉRIFICATION TENANT / STATION / LUBRIFIANT
    # --------------------------------------------------------

    if station.tenant_id != tenant.id:
        raise ValidationError(
            "La station n'appartient pas au tenant."
        )

    if lubrifiant.tenant_id != tenant.id:
        raise ValidationError(
            "Le lubrifiant n'appartient pas au tenant."
        )

    if not lubrifiant.actif:
        raise ValidationError(
            "Ce lubrifiant n'est pas actif."
        )

    # --------------------------------------------------------
    # RELAIS OPTIONNEL
    # --------------------------------------------------------

    if relais is not None:

        if relais.tenant_id != tenant.id:
            raise ValidationError(
                "Le relais n'appartient pas au tenant."
            )

        if relais.station_id != station.id:
            raise ValidationError(
                "Le relais n'appartient pas à cette station."
            )

        if relais.status != relais.Statut.BROUILLON:
            raise ValidationError(
                "Une vente de lubrifiant ne peut être ajoutée "
                "qu'à un relais à l'état BROUILLON."
            )

    # --------------------------------------------------------
    # PRIX COURANT
    # --------------------------------------------------------

    prix_unitaire = Decimal(lubrifiant.prix_vente)

    if prix_unitaire < 0:
        raise ValidationError(
            "Le prix de vente du lubrifiant ne peut pas être négatif."
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if date_vente is None:
        date_vente = timezone.now()

    # --------------------------------------------------------
    # CRÉATION DE LA VENTE
    # --------------------------------------------------------
    #
    # La vente est créée avant le mouvement afin de disposer
    # de son ID comme source_id du mouvement de stock.
    #
    # Si la sortie de stock échoue, la transaction complète
    # est annulée.
    # --------------------------------------------------------

    montant = quantite * prix_unitaire

    vente = VenteLubrifiant.objects.create(
        tenant=tenant,
        station=station,
        relais=relais,
        lubrifiant=lubrifiant,
        quantite=quantite,
        prix_unitaire=prix_unitaire,
        montant=montant,
        date_vente=date_vente,
        created_by=created_by,
    )

    # --------------------------------------------------------
    # SORTIE DE STOCK
    # --------------------------------------------------------

    sortie_stock_lubrifiant(
        tenant=tenant,
        station=station,
        lubrifiant=lubrifiant,
        quantite=quantite,
        source_type="VENTE_LUBRIFIANT",
        source_id=vente.id,
        date_mouvement=date_vente,
    )

    return vente