from django.db import models
from tenants.models import Tenant
from .constants import REGION_CHOICES
from django.conf import settings
from django.core.exceptions import ValidationError


class FaitStatus(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    VALIDE = "VALIDE", "Validé"
    TRANSFERE = "TRANSFERE", "Transféré"


class Station(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="stations"
    )

    nom = models.CharField(max_length=150)

    region = models.CharField(
        max_length=100,
        choices=REGION_CHOICES,
        blank=True,
        null=True
    )

    departement = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

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

class RelaisEquipe(models.Model):
    """
    Relais d’exploitation entre deux équipes.
    Basé sur index pompes + encaissements.
    Le jaugeage cuves est optionnel et non bloquant.
    """

    # ======================
    # CONTEXTE
    # ======================
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="relais_equipes"
    )
    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="relais_equipes"
    )

    # ======================
    # PÉRIODE
    # ======================
    debut_relais = models.DateTimeField()
    fin_relais = models.DateTimeField()

    equipe_sortante = models.CharField(max_length=100)
    equipe_entrante = models.CharField(max_length=100)

    # ======================
    # INDEX POMPES (OBLIGATOIRES)
    # ======================
    index_essence_debut = models.DecimalField(max_digits=12, decimal_places=2)
    index_essence_fin = models.DecimalField(max_digits=12, decimal_places=2)

    index_gasoil_debut = models.DecimalField(max_digits=12, decimal_places=2)
    index_gasoil_fin = models.DecimalField(max_digits=12, decimal_places=2)

    # ======================
    # JAUGEAGE CUVES (OPTIONNEL)
    # ======================
    jauge_essence_debut = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    jauge_essence_fin = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    jauge_gasoil_debut = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    jauge_gasoil_fin = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # ======================
    # ENCAISSEMENTS
    # ======================
    encaisse_liquide = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    encaisse_carte = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    encaisse_ticket_essence = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    encaisse_ticket_gasoil = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    # ======================
    # WORKFLOW
    # ======================
    status = models.CharField(
        max_length=20,
        choices=FaitStatus.choices,
        default=FaitStatus.BROUILLON
    )

    stock_applique = models.BooleanField(
        default=False,
        help_text="Indique si le stock a déjà été décrémenté pour ce relais"
    )

    # ======================
    # TRAÇABILITÉ
    # ======================
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="relais_crees"
    )
    soumis_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="relais_soumis"
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="relais_valides"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    soumis_le = models.DateTimeField(null=True, blank=True)
    valide_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-debut_relais"]
        verbose_name = "Relais d’équipe"
        verbose_name_plural = "Relais d’équipes"
        indexes = [
            models.Index(fields=["station", "debut_relais"]),
        ]

    # ======================
    # VALIDATIONS MÉTIER
    # ======================
    def clean(self):
        if self.fin_relais <= self.debut_relais:
            raise ValidationError(
                "La fin du relais doit être postérieure au début."
            )

        if self.index_essence_fin < self.index_essence_debut:
            raise ValidationError(
                "Index essence fin < début."
            )

        if self.index_gasoil_fin < self.index_gasoil_debut:
            raise ValidationError(
                "Index gasoil fin < début."
            )

    # ======================
    # CALCULS AUTOMATIQUES
    # ======================
    @property
    def volume_essence_vendu(self):
        return self.index_essence_fin - self.index_essence_debut

    @property
    def volume_gasoil_vendu(self):
        return self.index_gasoil_fin - self.index_gasoil_debut

    @property
    def total_encaisse(self):
        return (
            self.encaisse_liquide
            + self.encaisse_carte
            + self.encaisse_ticket_essence
            + self.encaisse_ticket_gasoil
        )

    @property
    def variation_cuve_essence(self):
        if self.jauge_essence_debut is None or self.jauge_essence_fin is None:
            return None
        return self.jauge_essence_debut - self.jauge_essence_fin

    @property
    def variation_cuve_gasoil(self):
        if self.jauge_gasoil_debut is None or self.jauge_gasoil_fin is None:
            return None
        return self.jauge_gasoil_debut - self.jauge_gasoil_fin

    def __str__(self):
        return f"Relais {self.station.nom} ({self.debut_relais:%d/%m %H:%M})"


class JustificationDepotage(models.Model):
    depotage = models.OneToOneField(
        "Depotage",
        on_delete=models.CASCADE,
        related_name="justification"
    )

    motif = models.CharField(max_length=255)
    commentaire = models.TextField(blank=True)

    justifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Justification de dépotage"
        verbose_name_plural = "Justifications de dépotage"
