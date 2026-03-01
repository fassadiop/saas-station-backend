from django.db import models
from tenants.models import Tenant
from stations.models import Station
from stations.models_produit import ProduitCarburant


class ObjectifStation(models.Model):

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="objectifs_stations"
    )

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="objectifs"
    )

    produit = models.ForeignKey(
        ProduitCarburant,
        on_delete=models.CASCADE,
        related_name="objectifs"
    )

    annee = models.IntegerField()
    mois = models.IntegerField()

    volume_cible = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    ca_cible = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            "tenant",
            "station",
            "produit",
            "annee",
            "mois",
        )
        indexes = [
            models.Index(fields=["tenant", "annee", "mois"]),
        ]

    def __str__(self):
        return f"{self.station.nom} - {self.mois}/{self.annee}"