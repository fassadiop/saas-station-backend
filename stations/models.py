from django.db import models
from tenants.models import Tenant
from django.conf import settings

class FaitStatus(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    VALIDE = "VALIDE", "Validé"
    TRANSFERE = "TRANSFERE", "Transféré"


class Station(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    nom = models.CharField(max_length=150)
    adresse = models.TextField()
    responsable = models.CharField(max_length=150, blank=True)
    telephone = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class VenteCarburant(models.Model):
    PRODUIT_CHOICES = (
        ("Super", "Super"),
        ("Gasoil", "Gasoil"),
        ("Petrole", "Pétrole"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    station = models.ForeignKey(Station, on_delete=models.CASCADE)

    date = models.DateTimeField()
    produit = models.CharField(max_length=50, choices=PRODUIT_CHOICES)
    volume = models.DecimalField(max_digits=10, decimal_places=2)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)

    # 🔒 Flux métier
    status = models.CharField(
        max_length=20,
        choices=FaitStatus.choices,
        default=FaitStatus.BROUILLON
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ventes_creees"
    )
    soumis_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="ventes_soumises"
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="ventes_validees"
    )

    soumis_le = models.DateTimeField(null=True, blank=True)
    valide_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]


class Local(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    station = models.ForeignKey(Station, on_delete=models.CASCADE)
    nom = models.CharField(max_length=100)
    type_local = models.CharField(max_length=50)  # boutique, lavage, garage…
    loyer_mensuel = models.DecimalField(max_digits=12, decimal_places=2)
    occupe = models.BooleanField(default=True)

    def __str__(self):
        return self.nom


class ContratLocation(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    local = models.ForeignKey(Local, on_delete=models.CASCADE)
    locataire = models.CharField(max_length=150)
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["-date_debut"]
