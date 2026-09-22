# stations/models_lubrifiant/mouvement.py

from django.core.exceptions import ValidationError
from django.db import models


class MouvementStockLubrifiant(models.Model):
    MOUVEMENT_ENTREE = "ENTREE"
    MOUVEMENT_SORTIE = "SORTIE"

    TYPE_CHOICES = [
        (MOUVEMENT_ENTREE, "Entrée"),
        (MOUVEMENT_SORTIE, "Sortie"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="mouvements_stock_lubrifiants",
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="mouvements_stock_lubrifiants",
    )

    lubrifiant = models.ForeignKey(
        "stations.Lubrifiants",
        on_delete=models.PROTECT,
        related_name="mouvements_stock",
    )

    type_mouvement = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
    )

    quantite = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    source_type = models.CharField(
        max_length=50,
    )

    source_id = models.PositiveIntegerField()

    date_mouvement = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_mouvement", "-id"]

        indexes = [
            models.Index(
                fields=["tenant", "station", "lubrifiant"]
            ),
            models.Index(
                fields=["source_type", "source_id"]
            ),
        ]

    def clean(self):
        if self.quantite <= 0:
            raise ValidationError(
                {"quantite": "La quantité doit être supérieure à zéro."}
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

    def __str__(self):
        return (
            f"{self.type_mouvement} - "
            f"{self.lubrifiant} - "
            f"{self.quantite}"
        )