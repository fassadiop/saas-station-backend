# stations/services/stock.py

from decimal import Decimal
from django.db import transaction
from django.db.models import F, Sum
from rest_framework.exceptions import ValidationError
from collections import defaultdict

from stations.models import RelaisEquipe, RelaisIndex
from stations.models_depotage.cuve import Cuve, CuveStatus
from stations.models_depotage.mouvement_stock import MouvementStock
import logging
logger = logging.getLogger(__name__)

# ============================================================
# STOCK GLOBAL PRODUIT
# ============================================================

def get_volumes_par_produit(relais):
    """
    Source UNIQUE de calcul des volumes vendus par produit.
    Filtre strict des lignes invalides.
    """

    volumes = defaultdict(Decimal)

    lignes = (
        RelaisIndex.objects
        .filter(relais_ilot__relais=relais)
        .select_related("index_pompe__produit")
    )

    for ligne in lignes:

        # 🔒 index non terminé
        if ligne.index_fin is None:
            continue

        volume = Decimal(ligne.index_fin - ligne.index_debut)

        # 🔒 volume nul ou négatif
        if volume <= 0:
            continue

        # 🔥 FILTRE MÉTIER CRITIQUE (anti-bruit)
        if volume < Decimal("0.01"):
            continue

        produit = ligne.index_pompe.produit
        volumes[produit.id] += volume

    return volumes

def get_stock_exploitable_produit(station, produit):
    """
    Stock réellement vendable :
    UNIQUEMENT la cuve ACTIVE
    """
    cuve = (
        Cuve.objects
        .filter(
            station=station,
            produit=produit,
            statut=CuveStatus.ACTIVE,
        )
        .first()
    )

    if not cuve:
        return Decimal("0.00")

    return cuve.stock_actuel


# ============================================================
# CAPACITÉ TOTALE PRODUIT
# ============================================================

def get_capacite_totale_produit(station, produit):
    """
    Capacité totale exploitable :
    ACTIVE + STANDBY
    """

    total = (
        Cuve.objects
        .filter(
            station=station,
            produit=produit,
            statut__in=[
                CuveStatus.ACTIVE,
                CuveStatus.STANDBY,
            ],
        )
        .aggregate(total=Sum("capacite_max"))
        .get("total")
    )

    return total or Decimal("0.00")


# ============================================================
# SEUIL CRITIQUE RÉEL (en litres)
# ============================================================

def get_seuil_critique_reel(station, produit):

    capacite_totale = get_capacite_totale_produit(station, produit)

    if capacite_totale <= 0:
        return Decimal("0.00")

    return (
        Decimal(produit.seuil_critique_percent)
        / Decimal("100")
    ) * capacite_totale


# ============================================================
# VERIFICATION SEUIL CRITIQUE
# ============================================================

def is_stock_critique(station, produit, volume_a_deduire=Decimal("0.00")):
    """
    Vérifie si le stock passe sous le seuil critique
    après déduction éventuelle.
    """

    stock_global = get_stock_exploitable_produit(station, produit)

    if stock_global <= 0:
        return True

    seuil = get_seuil_critique_reel(station, produit)

    stock_apres = stock_global - Decimal(volume_a_deduire)

    return stock_apres <= seuil


# ============================================================
# RELAIS → SORTIE STOCK
# ============================================================

@transaction.atomic
def appliquer_stock_relais(relais):

    if relais.stock_applique:
        raise ValidationError("Stock déjà appliqué.")

    lignes = (
        RelaisIndex.objects
        .select_related("index_pompe__produit")
        .select_for_update()
        .filter(relais_ilot__relais=relais)
    )

    # ✅ volumes DOIT être ici (avant toute utilisation)
    volumes = defaultdict(Decimal)

    # ======================================================
    # 1️⃣ AGRÉGATION
    # ======================================================
    for ligne in lignes:

        if ligne.index_fin is None:
            continue

        volume = Decimal(ligne.volume_vendu or 0)

        if volume <= 0:
            continue

        if volume < Decimal("0.5"):
            continue

        produit = ligne.index_pompe.produit
        volumes[produit.id] += volume

    
    logger.warning(f"[VOLUMES RELAIS] {volumes}")
    # ======================================================
    # 2️⃣ DEBUG (optionnel)
    # ======================================================
    # print(volumes)  # ou logger.warning(volumes)

    # ======================================================
    # 3️⃣ CUVE
    # ======================================================
    cuves = (
        Cuve.objects
        .select_for_update()
        .filter(
            station=relais.station,
            statut=CuveStatus.ACTIVE
        )
    )

    cuves_map = {c.produit_id: c for c in cuves}

    # ======================================================
    # 4️⃣ VÉRIFICATION
    # ======================================================
    for produit_id, volume in volumes.items():

        cuve = cuves_map.get(produit_id)

        if not cuve:
            raise ValidationError(
                "Aucune cuve ACTIVE pour ce produit."
            )

        if cuve.stock_actuel < volume:
            raise ValidationError(
                f"Stock insuffisant pour {cuve.produit.code}"
            )

    # ======================================================
    # 5️⃣ DÉDUCTION
    # ======================================================
    for produit_id, volume in volumes.items():

        cuve = cuves_map[produit_id]

        cuve.stock_actuel = F("stock_actuel") - volume
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

    # ======================================================
    # 6️⃣ FINAL
    # ======================================================
    # relais.stock_applique = True
    # relais.save(update_fields=["stock_applique"])
    RelaisEquipe.objects.filter(pk=relais.pk).update(
    stock_applique=True
)

# ============================================================
# DEPOTAGE → ENTRÉE STOCK
# ============================================================

@transaction.atomic
def appliquer_stock_depotage(depotage, user):

    if depotage.stock_applique:
        raise ValidationError(
            "Le stock a déjà été appliqué "
            "pour ce dépotage."
        )

    if depotage.statut != "CONFIRME":
        raise ValidationError(
            "Le dépotage doit être confirmé "
            "avant application du stock."
        )

    cuve = Cuve.objects.select_for_update().get(
        id=depotage.cuve_id
    )

    if cuve.statut not in (
        CuveStatus.STANDBY,
        CuveStatus.ACTIVE,
    ):
        raise ValidationError(
            "La cuve n'est pas disponible "
            "pour dépotage."
        )

    volume = depotage.quantite_acceptee

    if volume is None or volume <= 0:
        raise ValidationError(
            "Quantité acceptée invalide."
        )

    volume = Decimal(volume)

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

    cuve.stock_actuel = F("stock_actuel") + volume
    cuve.save(update_fields=["stock_actuel", "updated_at"])

    depotage.stock_applique = True
    depotage.statut = "TRANSFERE"
    depotage.save(
        update_fields=[
            "stock_applique",
            "statut",
            "updated_at",
        ]
    )

    return cuve
