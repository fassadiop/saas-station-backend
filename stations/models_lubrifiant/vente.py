# stations/models_lubrifiant/vente.py

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class Statut(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    VALIDE = "VALIDE", "Validé"
    TRANSFERE = "TRANSFERE", "Transféré"


class VenteLubrifiant(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ventes_lubrifiants",
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="ventes_lubrifiants",
    )

    relais = models.ForeignKey(
        "stations.RelaisEquipe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventes_lubrifiants",
    )

    lubrifiant = models.ForeignKey(
        "stations.Lubrifiants",
        on_delete=models.PROTECT,
        related_name="ventes",
    )

    quantite = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    prix_unitaire = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    date_vente = models.DateTimeField()

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventes_lubrifiants_creees",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_vente", "-id"]

    def clean(self):
        if self.quantite <= 0:
            raise ValidationError(
                {"quantite": "La quantité doit être supérieure à zéro."}
            )

        if self.prix_unitaire < 0:
            raise ValidationError(
                {
                    "prix_unitaire":
                    "Le prix unitaire ne peut pas être négatif."
                }
            )

        montant_calcule = self.quantite * self.prix_unitaire

        if self.montant != montant_calcule:
            raise ValidationError(
                {
                    "montant":
                    "Le montant doit être égal à quantité × prix unitaire."
                }
            )

        if self.station_id and self.tenant_id:
            if self.station.tenant_id != self.tenant_id:
                raise ValidationError(
                    "La station n'appartient pas au tenant."
                )

        if self.lubrifiant_id and self.tenant_id:
            if self.lubrifiant.tenant_id != self.tenant_id:
                raise ValidationError(
                    "Le lubrifiant n'appartient pas au tenant."
                )

        if self.relais_id and self.station_id:
            if self.relais.station_id != self.station_id:
                raise ValidationError(
                    "Le relais n'appartient pas à cette station."
                )

        if self.relais_id and self.tenant_id:
            if self.relais.tenant_id != self.tenant_id:
                raise ValidationError(
                    "Le relais n'appartient pas au tenant."
                )

    def save(self, *args, **kwargs):
        self.montant = (
            Decimal(self.quantite) *
            Decimal(self.prix_unitaire)
        ).quantize(Decimal("0.01"))

        self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.lubrifiant} - "
            f"{self.quantite} × {self.prix_unitaire} = "
            f"{self.montant}"
        )