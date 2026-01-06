# saas-backend/stations/models_depotage/cuve.py

from django.db import models

class Cuve(models.Model):
    PRODUIT_ESSENCE = "ESSENCE"
    PRODUIT_GASOIL = "GASOIL"

    PRODUIT_CHOICES = [
        (PRODUIT_ESSENCE, "Essence"),
        (PRODUIT_GASOIL, "Gasoil"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="cuves",
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="cuves",
    )

    produit = models.CharField(
        max_length=20,
        choices=PRODUIT_CHOICES,
    )

    seuil_alerte = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    capacite_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Capacité maximale de la cuve",
    )

    stock_actuel = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Stock actuel en litres",
    )

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("station", "produit")
        ordering = ["station", "produit"]

    def __str__(self):
        return f"{self.station.nom} - {self.produit}"
