# stations/models_baie/operation.py

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class OperationBaie(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="operations_baie",
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="operations_baie",
    )

    relais = models.ForeignKey(
        "stations.RelaisEquipe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operations_baie",
    )

    prestation = models.ForeignKey(
        "stations.PrestationBaie",
        on_delete=models.PROTECT,
        related_name="operations",
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

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operations_baie_creees",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=["tenant", "station"],
                name="idx_operation_baie_station",
            ),
            models.Index(
                fields=["relais"],
                name="idx_operation_baie_relais",
            ),
            models.Index(
                fields=["prestation"],
                name="idx_operation_baie_prestation",
            ),
        ]

    def clean(self):

        # ==================================================
        # QUANTITÉ
        # ==================================================

        if self.quantite <= 0:
            raise ValidationError(
                {
                    "quantite": (
                        "La quantité doit être supérieure à zéro."
                    )
                }
            )

        # ==================================================
        # PRIX UNITAIRE
        # ==================================================

        if self.prix_unitaire < 0:
            raise ValidationError(
                {
                    "prix_unitaire": (
                        "Le prix unitaire ne peut pas être négatif."
                    )
                }
            )

        # ==================================================
        # MONTANT
        # ==================================================

        montant_calcule = (
            Decimal(self.quantite)
            * Decimal(self.prix_unitaire)
        ).quantize(Decimal("0.01"))

        if self.montant != montant_calcule:
            raise ValidationError(
                {
                    "montant": (
                        "Le montant doit être égal à "
                        "quantité × prix unitaire."
                    )
                }
            )

        # ==================================================
        # TENANT / STATION
        # ==================================================

        if self.station_id and self.tenant_id:

            if self.station.tenant_id != self.tenant_id:
                raise ValidationError(
                    "La station n'appartient pas au tenant."
                )

        # ==================================================
        # TENANT / PRESTATION
        # ==================================================

        if self.prestation_id and self.tenant_id:

            if self.prestation.tenant_id != self.tenant_id:
                raise ValidationError(
                    "La prestation n'appartient pas au tenant."
                )

        # ==================================================
        # STATION / PRESTATION
        # ==================================================

        if self.prestation_id and self.station_id:

            if self.prestation.station_id != self.station_id:
                raise ValidationError(
                    "La prestation n'appartient pas à cette station."
                )

        # ==================================================
        # RELAIS FACULTATIF
        # ==================================================

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
            Decimal(self.quantite)
            * Decimal(self.prix_unitaire)
        ).quantize(Decimal("0.01"))

        self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.prestation.designation} - "
            f"{self.quantite} × {self.prix_unitaire} = "
            f"{self.montant}"
        )