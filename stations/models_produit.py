# stations/models_produit.py

from django.db import models

class ProduitCarburant(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="produits_carburant"
    )

    nom = models.CharField(max_length=50)
    code = models.CharField(max_length=20)

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code}"


