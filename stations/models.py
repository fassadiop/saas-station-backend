# stations/models.py

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from stations.models_produit import PrixCarburant
from tenants.models import Tenant
from .constants import REGION_CHOICES
from stations.services.stock import appliquer_stock_relais


# ============================================================
# WORKFLOW STATUS
# ============================================================

class FaitStatus(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    VALIDE = "VALIDE", "Validé"
    TRANSFERE = "TRANSFERE", "Transféré"


# ============================================================
# STATION
# ============================================================

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

    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


# ============================================================
# POMPE
# ============================================================

class Pompe(models.Model):

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="pompes"
    )

    reference = models.CharField(
        max_length=50,
        help_text="Référence physique de la pompe (ex: P1, P2)"
    )

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reference"]
        unique_together = ("station", "reference")

    def __str__(self):
        return f"{self.station.nom} - {self.reference}"


# ============================================================
# INDEX POMPE (DYNAMIQUE PAR PRODUIT)
# ============================================================

class IndexPompe(models.Model):

    FACE_CHOICES = (
        ("A", "Face A"),
        ("B", "Face B"),
    )

    pompe = models.ForeignKey(
        Pompe,
        on_delete=models.PROTECT,
        related_name="index_pompes"
    )

    produit = models.ForeignKey(
        "stations.ProduitCarburant",
        on_delete=models.PROTECT
    )

    index_initial = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    index_courant = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    face = models.CharField(
        max_length=1,
        choices=FACE_CHOICES,
        default="A"
    )

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pompe", "produit", "face"]
        constraints = [
            models.UniqueConstraint(
                fields=["pompe", "produit", "face"],
                name="unique_index_par_face",
            )
        ]

    def __str__(self):
        return f"{self.pompe.reference} - {self.produit.code}"
    
    def clean(self):

        # 🔒 Vérifier que le produit appartient au même tenant que la station
        if self.produit.tenant_id != self.pompe.station.tenant_id:
            raise ValidationError(
                "Produit incompatible avec la station."
            )

        # 🔒 Limite à 2 index maximum par pompe
        total_index = IndexPompe.objects.filter(
            pompe=self.pompe
        ).exclude(pk=self.pk).count()

        if total_index >= 2:
            raise ValidationError(
                "Une pompe ne peut avoir plus de 2 index."
            )

        # 🔒 Limite à 2 produits maximum par pompe
        produits_existants = set(
            IndexPompe.objects.filter(
                pompe=self.pompe
            )
            .exclude(pk=self.pk)
            .values_list("produit_id", flat=True)
        )

        if self.produit_id not in produits_existants:
            if len(produits_existants) >= 2:
                raise ValidationError(
                    "Une pompe ne peut distribuer plus de 2 produits."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# ============================================================
# RELAIS EQUIPE (MOTEUR OFFICIEL)
# ============================================================

class RelaisEquipe(models.Model):

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

    debut_relais = models.DateTimeField()
    fin_relais = models.DateTimeField()

    equipe_sortante = models.CharField(max_length=100)
    equipe_entrante = models.CharField(max_length=100)

    encaisse_liquide = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    encaisse_carte = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    encaisse_ticket = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    status = models.CharField(
        max_length=20,
        choices=FaitStatus.choices,
        default=FaitStatus.BROUILLON
    )

    stock_applique = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="relais_crees"
    )

    soumis_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="relais_soumis"
    )

    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="relais_valides"
    )

    soumis_le = models.DateTimeField(null=True, blank=True)
    valide_le = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["station", "debut_relais", "fin_relais"],
                name="idx_station_periode_relais"
            ),
        ]

    def clean(self):
        if self.fin_relais <= self.debut_relais:
            raise ValidationError(
                "La fin du relais doit être postérieure au début."
            )

    def changer_statut(self, nouveau_statut, user):

        transitions = {
            FaitStatus.BROUILLON: [FaitStatus.SOUMIS],
            FaitStatus.SOUMIS: [FaitStatus.VALIDE],
            FaitStatus.VALIDE: [FaitStatus.TRANSFERE],
            FaitStatus.TRANSFERE: [],
        }

        if nouveau_statut not in transitions[self.status]:
            raise ValidationError("Transition invalide.")

        ancien_statut = self.status

        if nouveau_statut == FaitStatus.SOUMIS:
            self.soumis_par = user
            self.soumis_le = timezone.now()

        if nouveau_statut == FaitStatus.VALIDE:
            self.valide_par = user
            self.valide_le = timezone.now()

            if not self.produits.exists():
                raise ValidationError("Aucun produit dans le relais.")

            for produit_relais in self.produits.all():

                prix = PrixCarburant.objects.filter(
                    tenant=self.tenant,
                    station=self.station,
                    produit=produit_relais.produit,
                    actif=True
                ).first()

                if not prix:
                    raise ValidationError(
                        f"Aucun prix actif défini pour {produit_relais.produit.code}"
                    )

                produit_relais.prix_unitaire = prix.prix_unitaire
                produit_relais.montant_theorique = (
                    produit_relais.volume_vendu * prix.prix_unitaire
                )

                produit_relais.save(
                    update_fields=["prix_unitaire", "montant_theorique"],
                    bypass_lock=True
                )
        from finances_station.models import TransactionStation
        if nouveau_statut == FaitStatus.TRANSFERE:

            appliquer_stock_relais(self)

            TransactionStation.objects.get_or_create(
                source_type="RelaisEquipe",
                source_id=self.id,
                defaults={
                    "tenant": self.tenant,
                    "station": self.station,
                    "type": "RECETTE",
                    "montant": self.total_encaisse,
                    "date": self.fin_relais,
                    "finance_status": "PROVISOIRE",
                }
            )

            self.stock_applique = True

        self.status = nouveau_statut
        super().save(update_fields=[
            "status",
            "soumis_par",
            "soumis_le",
            "valide_par",
            "valide_le",
            "stock_applique"
        ])

        RelaisAudit.objects.create(
            relais=self,
            tenant=self.tenant,
            ancien_statut=ancien_statut,
            nouveau_statut=nouveau_statut,
            action="CHANGEMENT_STATUT",
            effectue_par=user
        )

    @property
    def total_volume_vendu(self):
        return sum(p.volume_vendu for p in self.produits.all())

    @property
    def total_encaisse(self):
        return (
            self.encaisse_liquide
            + self.encaisse_carte
            + sum(p.encaisse_ticket for p in self.produits.all())
        )
    
    @property
    def total_theorique(self):
        return sum(
            p.montant_theorique or 0
            for p in self.produits.all()
        )

    @property
    def ecart_caisse(self):
        return self.total_encaisse - self.total_theorique

    def save(self, *args, **kwargs):
        if self.pk:
            ancien = RelaisEquipe.objects.get(pk=self.pk)
            if ancien.status != FaitStatus.BROUILLON:
                raise ValidationError(
                    "Modification impossible : relais non en brouillon."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != FaitStatus.BROUILLON:
            raise ValidationError(
                "Suppression impossible : relais non en brouillon."
            )
        super().delete(*args, **kwargs)


# ============================================================
# RELAIS PRODUIT
# ============================================================

class RelaisProduit(models.Model):

    relais = models.ForeignKey(
        RelaisEquipe,
        on_delete=models.CASCADE,
        related_name="produits"
    )

    produit = models.ForeignKey(
        "stations.ProduitCarburant",
        on_delete=models.PROTECT
    )

    index_debut = models.DecimalField(max_digits=12, decimal_places=2)
    index_fin = models.DecimalField(max_digits=12, decimal_places=2)

    prix_unitaire = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    montant_theorique = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["relais", "produit"],
                name="unique_produit_per_relais"
            )
        ]

    def clean(self):
        if self.index_fin < self.index_debut:
            raise ValidationError(
                f"Index fin < début pour {self.produit.code}"
            )
        if self.produit.tenant_id != self.relais.tenant_id:
            raise ValidationError(
                "Produit incompatible avec le tenant."
            )

    def save(self, *args, bypass_lock=False, **kwargs):

        # 🔒 Bloquer modification si relais non brouillon
        if not bypass_lock and self.pk:
            ancien = RelaisProduit.objects.get(pk=self.pk)
            if ancien.relais.status != FaitStatus.BROUILLON:
                raise ValidationError(
                    "Modification impossible : relais non en brouillon."
                )

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def volume_vendu(self):
        return self.index_fin - self.index_debut


# ============================================================
# AUDIT
# ============================================================

class RelaisAudit(models.Model):

    relais = models.ForeignKey(
        RelaisEquipe,
        on_delete=models.CASCADE,
        related_name="audits"
    )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE
    )

    ancien_statut = models.CharField(max_length=20)
    nouveau_statut = models.CharField(max_length=20)

    action = models.CharField(max_length=50)

    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL
    )

    date_action = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_action"]
        indexes = [
            models.Index(fields=["relais", "date_action"])
        ]

    def __str__(self):
        return (
            f"{self.relais.id} "
            f"{self.ancien_statut} → {self.nouveau_statut}"
        )
