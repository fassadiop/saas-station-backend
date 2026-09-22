# stations/models_lubrifiant/stock.py

from django.core.exceptions import ValidationError
from django.db import models


class StockLubrifiant(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="stocks_lubrifiants",
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="stocks_lubrifiants",
    )

    lubrifiant = models.ForeignKey(
        "stations.Lubrifiants",
        on_delete=models.PROTECT,
        related_name="stocks",
    )

    stock_actuel = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "station", "lubrifiant"],
                name="unique_stock_lubrifiant_station",
            ),
        ]
        ordering = ["station", "lubrifiant"]

    def clean(self):
        if self.stock_actuel < 0:
            raise ValidationError(
                {"stock_actuel": "Le stock ne peut pas être négatif."}
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
            f"{self.station} - "
            f"{self.lubrifiant} - "
            f"{self.stock_actuel}"
        )