from django.db import models

class MouvementStock(models.Model):
    MOUVEMENT_ENTREE = "ENTREE"
    MOUVEMENT_SORTIE = "SORTIE"

    TYPE_CHOICES = [
        (MOUVEMENT_ENTREE, "Entrée"),
        (MOUVEMENT_SORTIE, "Sortie"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE
    )
    station = models.ForeignKey(
        "stations.Station", on_delete=models.CASCADE
    )
    cuve = models.ForeignKey(
        "stations.Cuve", on_delete=models.CASCADE
    )

    type_mouvement = models.CharField(
        max_length=10, choices=TYPE_CHOICES
    )

    quantite = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    source_type = models.CharField(
        max_length=50
    )
    source_id = models.PositiveIntegerField()

    date_mouvement = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_mouvement"]

