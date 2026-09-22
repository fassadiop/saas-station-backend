# stations/models_baie/prestation.py

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class PrestationBaie(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="prestations_baie",
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="prestations_baie",
    )

    code = models.CharField(
        max_length=30,
    )

    designation = models.CharField(
        max_length=100,
    )

    unite = models.CharField(
        max_length=30,
        default="UNITE",
    )

    prix_unitaire = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0")),
        ],
    )

    actif = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "station", "code"],
                name="unique_prestation_baie_station_code",
            ),
        ]

        ordering = ["code"]

        indexes = [
            models.Index(
                fields=["tenant", "station", "actif"],
                name="idx_prest_baie_station_actif",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.designation}"