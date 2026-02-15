# stations/models.py

from datetime import timezone
from django.db import models
from tenants.models import Tenant
from .constants import REGION_CHOICES, RelaisStatus
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

    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom
    

class Pompe(models.Model):
    TYPE_POMPE_CHOICES = (
        ("SIMPLE", "Simple"),
        ("MIXTE", "Mixte"),
    )

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="pompes"
    )

    reference = models.CharField(
        max_length=50,
        help_text="Référence physique de la pompe (ex: P1, P2, Ilot A)"
    )

    type_pompe = models.CharField(
        max_length=10,
        choices=TYPE_POMPE_CHOICES
    )

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reference"]
        unique_together = ("station", "reference")

    def __str__(self):
        return f"{self.station.code_station} - {self.reference}"
    
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
        decimal_places=2,
        help_text="Index initial du compteur"
    )

    index_courant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Dernier index connu"
    )

    face = models.CharField(
        max_length=1,
        choices=FACE_CHOICES,
        default="A",
        help_text="Face du compteur (A / B)"
    )

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pompe", "carburant", "face"]

        constraints = [
            models.UniqueConstraint(
                fields=["pompe", "carburant", "face"],
                name="unique_index_par_face",
            )
        ]

    def __str__(self):
        return f"{self.pompe.reference} - {self.carburant}"


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

    # Encaissements généraux
    encaisse_liquide = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    encaisse_carte = models.DecimalField(
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

        ancien_statut = self.status

        transitions = {
            RelaisStatus.BROUILLON: [RelaisStatus.SOUMIS],
            RelaisStatus.SOUMIS: [RelaisStatus.VALIDE],
            RelaisStatus.VALIDE: [RelaisStatus.TRANSFERE],
            RelaisStatus.TRANSFERE: [],
        }

        if nouveau_statut not in transitions[self.status]:
            raise ValidationError(
                f"Transition invalide : {self.status} → {nouveau_statut}"
            )

        # 🔁 TRANSITION MÉTIER
        if nouveau_statut == RelaisStatus.SOUMIS:
            self.soumis_par = user
            self.soumis_le = timezone.now()

        if nouveau_statut == RelaisStatus.VALIDE:
            self.valide_par = user
            self.valide_le = timezone.now()

        if nouveau_statut == RelaisStatus.TRANSFERE:

            from stations.services.stock import appliquer_stock_relais
            from finances_station.models import TransactionStation

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
        self.save()

        # 🔎 AUDIT
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
    
    def save(self, *args, **kwargs):

        if self.pk:
            ancien = RelaisEquipe.objects.get(pk=self.pk)

            # 🔒 Interdit toute modification hors BROUILLON
            if ancien.status != RelaisStatus.BROUILLON:
                raise ValidationError(
                    "Modification impossible : relais non en brouillon."
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):

        if self.status != RelaisStatus.BROUILLON:
            raise ValidationError(
                "Suppression impossible : relais non en brouillon."
            )

        super().delete(*args, **kwargs)


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

    jauge_debut = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True
    )
    jauge_fin = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True
    )

    encaisse_ticket = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=0
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

        if self.index_debut < 0 or self.index_fin < 0:
            raise ValidationError(
                "Les index ne peuvent pas être négatifs."
            )

        if (
            self.jauge_debut is not None
            and self.jauge_fin is not None
            and self.jauge_fin > self.jauge_debut
        ):
            raise ValidationError(
                f"Jauge fin incohérente pour {self.produit.code}"
            )

        if self.produit.tenant_id != self.relais.tenant_id:
            raise ValidationError(
                "Produit incompatible avec le tenant."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def volume_vendu(self):
        return self.index_fin - self.index_debut

    @property
    def variation_cuve(self):
        if self.jauge_debut is None or self.jauge_fin is None:
            return None
        return self.jauge_debut - self.jauge_fin
    

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

