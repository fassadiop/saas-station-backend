# stations/services/stock.py

from decimal import Decimal
from django.db import transaction
from django.db.models import F, Sum
from rest_framework.exceptions import ValidationError

from stations.models import RelaisEquipe
from stations.models_depotage.cuve import Cuve, CuveStatus
from stations.models_depotage.mouvement_stock import MouvementStock


# ============================================================
# STOCK GLOBAL PRODUIT
# ============================================================

def get_stock_global_produit(station, produit):
    """
    Stock global réel exploitable :
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
        .aggregate(total=Sum("stock_actuel"))
        .get("total")
    )

    return total or Decimal("0.00")


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

    stock_global = get_stock_global_produit(station, produit)

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
    """
    Déduit le volume vendu de la cuve ACTIVE uniquement.
    Vérifie stock global + seuil critique avant déduction.
    """

    if relais.stock_applique:
        raise ValidationError(
            "Le stock de ce relais a déjà été appliqué."
        )

    # 🔁 Nouvelle source des lignes
    lignes = (
        relais.indexes
        .select_related("index_pompe__produit")
        .select_for_update()
    )

    for ligne in lignes:

        # Volume vendu via les index
        volume_total = (
            ligne.index_fin - ligne.index_debut
        )

        if volume_total is None or volume_total <= 0:
            continue

        volume_total = Decimal(volume_total)

        produit = ligne.index_pompe.produit

        # ============================================
        # 1️⃣ CONTRÔLE STOCK GLOBAL
        # ============================================

        stock_global = get_stock_global_produit(
            station=relais.station,
            produit=produit,
        )

        if stock_global < volume_total:
            raise ValidationError(
                f"Stock global insuffisant pour "
                f"{produit.code}. "
                f"Disponible: {stock_global} | "
                f"Demandé: {volume_total}"
            )

        # ============================================
        # 2️⃣ CONTRÔLE SEUIL CRITIQUE
        # ============================================

        if is_stock_critique(
            station=relais.station,
            produit=produit,
            volume_a_deduire=volume_total,
        ):
            raise ValidationError(
                f"Stock critique atteint pour "
                f"{produit.code}. "
                f"Relais bloqué."
            )

        # ============================================
        # 3️⃣ DÉDUCTION CUVE ACTIVE
        # ============================================

        cuve_active = (
            Cuve.objects
            .select_for_update()
            .filter(
                station=relais.station,
                produit=produit,
                statut=CuveStatus.ACTIVE,
            )
            .first()
        )

        if not cuve_active:
            raise ValidationError(
                f"Aucune cuve ACTIVE pour "
                f"{produit.code}."
            )

        if cuve_active.stock_actuel < volume_total:
            raise ValidationError(
                f"La cuve active ne contient pas "
                f"assez de stock pour "
                f"{produit.code}. "
                f"Stock cuve: {cuve_active.stock_actuel}"
            )

        # Déduction atomique
        cuve_active.stock_actuel = F("stock_actuel") - volume_total
        cuve_active.save(update_fields=["stock_actuel", "updated_at"])

        # Mouvement stock
        MouvementStock.objects.create(
            tenant=relais.tenant,
            station=relais.station,
            cuve=cuve_active,
            type_mouvement=MouvementStock.MOUVEMENT_SORTIE,
            quantite=volume_total,
            source_type="RELAIS",
            source_id=relais.id,
            date_mouvement=relais.fin_relais,
        )

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
