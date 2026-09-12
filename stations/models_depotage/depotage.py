# stations/models_depotage/depotage.py

from django.db import models
from django.conf import settings

from stations.constants import DepotageStatus


class Depotage(models.Model):
    """
    Dépotage carburant (événement physique réel)

    - Déclenche une dépense financière à la confirmation
    - Impacte le stock cuve
    """

    # =========================
    # CONTEXTE
    # =========================
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="depotages"
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="depotages"
    )

    cuve = models.ForeignKey(
        "stations.Cuve",
        on_delete=models.PROTECT,
        related_name="depotages"
    )

    # =========================
    # TRANSPORT
    # =========================

    fournisseur = models.CharField(
        max_length=150
    )

    numero_camion = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    transporteur = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    chauffeur = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    date_depotage = models.DateTimeField()

    date_commande = models.DateField(
        null=True,
        blank=True,
        help_text="Date de la commande fournisseur"
    )

    # =========================
    # COMMANDE / LIVRAISON
    # =========================
    quantite_commandee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Quantité initialement commandée (optionnelle)"
    )

    quantite_livree = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    quantite_acceptee = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # =========================
    # CUVE (AVANT / APRÈS)
    # =========================
    jauge_avant = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    jauge_apres = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    variation_cuve = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Calculé : jauge_apres - jauge_avant"
    )

    # =========================
    # CONTRÔLES PHYSIQUES
    # =========================

    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Température carburant (°C)"
    )

    manquant_camion = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Quantité manquante camion (BL - volume mesuré)"
    )

    ecart_depotage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Ecart entre quantité acceptée et variation cuve"
    )

    # =========================
    # FINANCES
    # =========================
    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    montant_total = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    # =========================
    # JUSTIFICATIFS
    # =========================
    bon_livraison_numero = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    stock_applique = models.BooleanField(
        default=False,
        help_text="Indique si l'impact stock a déjà été appliqué"
    )

    # =========================
    # STATUT & TRAÇABILITÉ
    # =========================
    statut = models.CharField(
        max_length=20,
        choices=DepotageStatus.choices,
        default=DepotageStatus.BROUILLON
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="depotages_crees"
    )

    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depotages_valides"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # =========================
    # EXTENSION FUTURE
    # =========================
    reference_commande = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Référence commande fournisseur (phase 2)"
    )

    class Meta:
        ordering = ["-date_depotage"]
        verbose_name = "Dépotage"
        verbose_name_plural = "Dépotages"

    def __str__(self):
        return (
            f"Dépotage {self.cuve.produit.code} "
            f"– {self.station.nom} "
            f"– {self.date_depotage.date()}"
        )


