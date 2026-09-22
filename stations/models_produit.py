# stations/models_produit.py

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

class ProduitCarburant(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="produits_carburant"
    )

    nom = models.CharField(max_length=50)
    code = models.CharField(max_length=20)

    seuil_critique_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        help_text="Seuil critique en pourcentage de la capacité totale"
    )

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code}"
    
    def peut_etre_desactive(self):
        from stations.models_depotage.cuve import Cuve, CuveStatus

        return not Cuve.objects.filter(
            produit=self,
            statut=CuveStatus.ACTIVE
        ).exists()

    def desactiver(self):
        if not self.peut_etre_desactive():
            raise ValidationError(
                "Impossible de désactiver : une cuve ACTIVE existe pour ce produit."
            )

        self.actif = False
        self.save(update_fields=["actif"])


class Lubrifiants(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="lubrifiants"
    )

    code = models.CharField(max_length=30)

    designation = models.CharField(max_length=100)

    nature = models.CharField(
        max_length=30,
        help_text="Contenu ou format du lubrifiant : 1L, 2L, 5L, 20L, 500g, etc."
    )

    unite = models.CharField(
        max_length=30,
        help_text="Unité de conditionnement : BIDON, BOUTEILLE, TUBE, CARTOUCHE, etc."
    )

    prix_vente = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    prix_achat = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    seuil_alerte = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.designation} ({self.nature})"


class PrixCarburant(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="prix_carburants"
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="prix_carburants"
    )

    produit = models.ForeignKey(
        ProduitCarburant,
        on_delete=models.CASCADE,
        related_name="prix"
    )

    prix_unitaire = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField(null=True, blank=True)

    actif = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_debut"]

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "station", "produit"],
                condition=Q(actif=True),
                name="unique_prix_actif_par_produit_tenant"
            )
        ]

    def clean(self):
        if self.produit.tenant_id != self.tenant_id:
            raise ValidationError("Produit invalide pour ce tenant.")

        if self.station.tenant_id != self.tenant_id:
            raise ValidationError("Station invalide pour ce tenant.")

    def activer(self):
        PrixCarburant.objects.filter(
            tenant=self.tenant,
            station=self.station,
            produit=self.produit,
            actif=True
        ).update(
            actif=False,
            date_fin=timezone.now()
        )

        self.actif = True
        self.date_debut = timezone.now()
        self.save()
