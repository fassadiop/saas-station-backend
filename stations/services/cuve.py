from django.db import transaction
from django.core.exceptions import ValidationError

from stations.models_depotage.cuve import Cuve, CuveStatus


@transaction.atomic
def changer_statut_cuve(cuve: Cuve, nouveau_statut: str):
    """
    Service métier sécurisé pour changer le statut d'une cuve.

    Centralise :
    - validation transition
    - gestion unicité ACTIVE
    - cohérence transactionnelle
    """

    if cuve.statut == nouveau_statut:
        return cuve

    # Validation transition
    cuve.changer_statut(nouveau_statut)

    return cuve
