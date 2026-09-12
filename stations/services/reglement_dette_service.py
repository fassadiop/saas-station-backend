# stations/services/reglement_dette_service.py

from django.db import transaction
from django.core.exceptions import ValidationError
from stations.models import ReglementDette


def regler_dette(*, dette, montant, mode_paiement, user):

    if montant <= 0:
        raise ValidationError("Montant invalide.")

    if montant > dette.montant_restant:
        raise ValidationError(
            "Montant supérieur au restant."
        )

    if dette.statut == "REGLEE":
        raise ValidationError(
            "Cette dette est déjà réglée."
        )

    with transaction.atomic():

        reglement = ReglementDette.objects.create(
            tenant=user.tenant,
            dette=dette,
            montant=montant,
            mode_paiement=mode_paiement,
            created_by=user
        )

        # Mise à jour de la dette
        dette.appliquer_reglement(montant)

    return reglement