# stations/services/stock_lubrifiant.py

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.db.models import F
from rest_framework.exceptions import ValidationError

from stations.models_lubrifiant.stock import StockLubrifiant
from stations.models_lubrifiant.mouvement import MouvementStockLubrifiant


# ============================================================
# ENTRÉE STOCK LUBRIFIANT
# ============================================================

@transaction.atomic
def entree_stock_lubrifiant(
    *,
    tenant,
    station,
    lubrifiant,
    quantite,
    source_type,
    source_id,
    date_mouvement,
):
    """
    Enregistre une entrée de stock pour un lubrifiant.

    Opérations réalisées dans une seule transaction :
        1. Vérification de la quantité
        2. Récupération / création du stock
        3. Verrouillage du stock
        4. Création du mouvement d'entrée
        5. Mise à jour du stock
    """

    quantite = Decimal(quantite)

    if quantite <= 0:
        raise ValidationError(
            "La quantité d'entrée doit être supérieure à zéro."
        )

    if date_mouvement is None:
        date_mouvement = timezone.now()

    # --------------------------------------------------------
    # STOCK
    # --------------------------------------------------------

    stock, _ = StockLubrifiant.objects.get_or_create(
        tenant=tenant,
        station=station,
        lubrifiant=lubrifiant,
        defaults={
            "stock_actuel": Decimal("0.00"),
        },
    )

    # Verrouillage du stock
    stock = (
        StockLubrifiant.objects
        .select_for_update()
        .get(pk=stock.pk)
    )

    # --------------------------------------------------------
    # MOUVEMENT
    # --------------------------------------------------------

    mouvement = MouvementStockLubrifiant.objects.create(
        tenant=tenant,
        station=station,
        lubrifiant=lubrifiant,
        type_mouvement=MouvementStockLubrifiant.MOUVEMENT_ENTREE,
        quantite=quantite,
        source_type=source_type,
        source_id=source_id,
        date_mouvement=date_mouvement,
    )

    # --------------------------------------------------------
    # MISE À JOUR STOCK
    # --------------------------------------------------------

    stock.stock_actuel = F("stock_actuel") + quantite
    stock.save(
        update_fields=[
            "stock_actuel",
            "updated_at",
        ]
    )

    return mouvement


# ============================================================
# SORTIE STOCK LUBRIFIANT
# ============================================================

@transaction.atomic
def sortie_stock_lubrifiant(
    *,
    tenant,
    station,
    lubrifiant,
    quantite,
    source_type,
    source_id,
    date_mouvement,
):
    """
    Enregistre une sortie de stock pour un lubrifiant.

    Le stock est verrouillé avant le contrôle de disponibilité.

    Opérations réalisées dans une seule transaction :
        1. Vérification de la quantité
        2. Récupération du stock
        3. Verrouillage du stock
        4. Vérification du stock disponible
        5. Création du mouvement de sortie
        6. Mise à jour du stock
    """

    quantite = Decimal(quantite)

    if quantite <= 0:
        raise ValidationError(
            "La quantité de sortie doit être supérieure à zéro."
        )

    if date_mouvement is None:
        date_mouvement = timezone.now()

    # --------------------------------------------------------
    # STOCK
    # --------------------------------------------------------

    try:
        stock = (
            StockLubrifiant.objects
            .select_for_update()
            .get(
                tenant=tenant,
                station=station,
                lubrifiant=lubrifiant,
            )
        )
    except StockLubrifiant.DoesNotExist:
        raise ValidationError(
            "Aucun stock n'existe pour ce lubrifiant dans cette station."
        )

    # --------------------------------------------------------
    # VÉRIFICATION DISPONIBILITÉ
    # --------------------------------------------------------

    if stock.stock_actuel < quantite:
        raise ValidationError(
            f"Stock insuffisant pour le lubrifiant "
            f"{lubrifiant.code}. "
            f"Stock disponible : {stock.stock_actuel}."
        )

    # --------------------------------------------------------
    # MOUVEMENT
    # --------------------------------------------------------

    mouvement = MouvementStockLubrifiant.objects.create(
        tenant=tenant,
        station=station,
        lubrifiant=lubrifiant,
        type_mouvement=MouvementStockLubrifiant.MOUVEMENT_SORTIE,
        quantite=quantite,
        source_type=source_type,
        source_id=source_id,
        date_mouvement=date_mouvement,
    )

    # --------------------------------------------------------
    # MISE À JOUR STOCK
    # --------------------------------------------------------

    stock.stock_actuel = F("stock_actuel") - quantite
    stock.save(
        update_fields=[
            "stock_actuel",
            "updated_at",
        ]
    )

    return mouvement