# stations/services/operation_baie.py

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from stations.models_baie import OperationBaie


# ============================================================
# OPERATION DE BAIE
# ============================================================

@transaction.atomic
def enregistrer_operation_baie(
    *,
    tenant,
    station,
    prestation,
    quantite,
    relais=None,
    created_by=None,
):
    """
    Enregistre une opération de baie.

    L'opération peut être :
        - autonome : relais=None
        - intégrée à un relais : relais fourni

    Le prix unitaire est récupéré depuis le catalogue
    PrestationBaie.

    Le montant est calculé automatiquement :

        montant = quantite × prix_unitaire

    Aucune opération de stock n'est réalisée.
    """

    # ========================================================
    # QUANTITÉ
    # ========================================================

    quantite = Decimal(quantite)

    if quantite <= 0:
        raise ValidationError(
            "La quantité doit être supérieure à zéro."
        )

    # ========================================================
    # VÉRIFICATION TENANT / STATION
    # ========================================================

    if station.tenant_id != tenant.id:
        raise ValidationError(
            "La station n'appartient pas au tenant."
        )

    if not station.active:
        raise ValidationError(
            "Cette station est désactivée."
        )

    # ========================================================
    # VÉRIFICATION TENANT / PRESTATION
    # ========================================================

    if prestation.tenant_id != tenant.id:
        raise ValidationError(
            "La prestation n'appartient pas au tenant."
        )

    # ========================================================
    # VÉRIFICATION STATION / PRESTATION
    # ========================================================

    if prestation.station_id != station.id:
        raise ValidationError(
            "La prestation n'appartient pas à cette station."
        )

    # ========================================================
    # PRESTATION ACTIVE
    # ========================================================

    if not prestation.actif:
        raise ValidationError(
            "Cette prestation est désactivée."
        )

    # ========================================================
    # RELAIS OPTIONNEL
    # ========================================================

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
                "Une opération de baie ne peut être ajoutée "
                "qu'à un relais à l'état BROUILLON."
            )

    # ========================================================
    # PRIX COURANT DE LA PRESTATION
    # ========================================================

    prix_unitaire = Decimal(
        prestation.prix_unitaire
    )

    if prix_unitaire < 0:
        raise ValidationError(
            "Le prix unitaire de la prestation "
            "ne peut pas être négatif."
        )

    # ========================================================
    # DATE DE CRÉATION
    # ========================================================

    # L'opération n'a pas de date métier propre.
    # created_at est automatiquement renseigné par Django.
    #
    # La période métier est déterminée par le relais
    # lorsqu'un relais est utilisé.
    # ========================================================

    # ========================================================
    # MONTANT
    # ========================================================

    montant = (
        quantite * prix_unitaire
    ).quantize(Decimal("0.01"))

    # ========================================================
    # CRÉATION DE L'OPÉRATION
    # ========================================================

    operation = OperationBaie.objects.create(
        tenant=tenant,
        station=station,
        relais=relais,
        prestation=prestation,
        quantite=quantite,
        prix_unitaire=prix_unitaire,
        montant=montant,
        created_by=created_by,
    )

    return operation