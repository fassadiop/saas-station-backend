# stations/models.py

from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from stations.models_produit import PrixCarburant
from tenants.models import Tenant
from .constants import REGION_CHOICES
from django.utils import timezone
from decimal import Decimal
from django.db.models import Q, Sum, F, DecimalField, Value
from django.db.models.functions import Coalesce


# ============================================================
# WORKFLOW STATUS
# ============================================================

class FaitStatus(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    VALIDE = "VALIDE", "Validé"
    TRANSFERE = "TRANSFERE", "Transféré"
    CONFIRME = "CONFIRME", "Confirmé"


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
# ILOT
# ============================================================
class Ilot(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ilots"
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="ilots"
    )

    nom = models.CharField(max_length=100)

    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("station", "nom")
        ordering = ["nom"]

        indexes = [
            models.Index(fields=["tenant", "station"]),
        ]

    def __str__(self):
        return f"{self.station.nom} - {self.nom}"

    def clean(self):
        if self.station.tenant_id != self.tenant_id:
            raise ValidationError("Incohérence tenant / station.")
        
    def can_deactivate(self):
        return not self.pompes.filter(actif=True).exists()
    

class RelaisIlot(models.Model):

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        SOUMIS = "SOUMIS", "Soumis"
        VALIDE = "VALIDE", "Validé"
        TRANSFERE = "TRANSFERE", "Transféré"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="relais_ilots"
    )

    relais = models.ForeignKey(
        "stations.RelaisEquipe",
        on_delete=models.CASCADE,
        related_name="ilots"
    )

    ilot = models.ForeignKey(
        "stations.Ilot",
        on_delete=models.PROTECT,
        related_name="relais"
    )

    responsable = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        related_name="relais_ilots_responsable"
    )

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        related_name="relais_ilots_crees"
    )

    soumis_par = models.ForeignKey(
        "accounts.Utilisateur",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="relais_ilots_soumis"
    )

    valide_par = models.ForeignKey(
        "accounts.Utilisateur",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="relais_ilots_valides"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("relais", "ilot")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["tenant", "relais"]),
        ]

    # ======================================================
    # PROPRIÉTÉS AGRÉGÉES
    # ======================================================

    @property
    def total_volume_vendu(self):
        return sum(
            (index.volume_vendu or Decimal("0"))
            for index in self.indexes.all()
        )


    @property
    def total_theorique(self):
        return sum(
            (index.montant_theorique or Decimal("0"))
            for index in self.indexes.all()
        )


    @property
    def total_encaisse(self):
        return sum(
            (e.montant or Decimal("0"))
            for e in self.encaissements.all()
        )


    @property
    def total_versement(self):
        return sum(
            (v.montant_remis or Decimal("0"))
            for v in self.versements.all()
        )

    # ======================================================
    # VALIDATION STRUCTURELLE
    # ======================================================

    def clean(self):

        if self.relais.tenant_id != self.tenant_id:
            raise ValidationError("Incohérence tenant.")

        if self.ilot.station_id != self.relais.station_id:
            raise ValidationError(
                "L'îlot doit appartenir à la même station que le relais."
            )

        if self.responsable.tenant_id != self.tenant_id:
            raise ValidationError("Responsable hors tenant.")

    # ======================================================
    # MACHINE D'ÉTAT
    # ======================================================

    def changer_statut(self, nouveau_statut, user):

        transitions = {
            self.Statut.BROUILLON: [self.Statut.SOUMIS],
            self.Statut.SOUMIS: [self.Statut.VALIDE],
            self.Statut.VALIDE: [],
        }

        if nouveau_statut not in transitions[self.statut]:
            raise ValidationError("Transition invalide.")

        # -------------------------------------------------
        # COHÉRENCE AVEC RELAISEQUIPE
        # -------------------------------------------------

        if self.relais.status == "TRANSFERE":
            raise ValidationError(
                "Relais transféré : modification interdite."
            )

        # 🔒 Un ilot ne peut être soumis que si relais ouvert
        if nouveau_statut == self.Statut.SOUMIS:

            if self.relais.status not in ["BROUILLON", "SOUMIS"]:
                raise ValidationError(
                    "Impossible de soumettre : relais non ouvert."
                )

        # 🔒 Un ilot ne peut être validé que si relais déjà soumis
        if nouveau_statut == self.Statut.VALIDE:

            if self.relais.status not in ["SOUMIS", "VALIDE"]:
                raise ValidationError(
                    "Le relais doit être soumis avant validation des îlots."
                )

        ancien_statut = self.statut

        # -------------------------------------------------
        # SOUMISSION
        # -------------------------------------------------

        if nouveau_statut == self.Statut.SOUMIS:

            if not self.indexes.exists():
                raise ValidationError(
                    "Aucun index enregistré."
                )

            self.soumis_par = user

        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if nouveau_statut == self.Statut.VALIDE:

            if not self.indexes.exists():
                raise ValidationError(
                    "Impossible de valider : aucun index enregistré."
                )

            self.valide_par = user
            self.valide_le = timezone.now()

        self.statut = nouveau_statut
        self.save()

    # ======================================================
    # VERROUILLAGE GLOBAL
    # ======================================================

    def destroy(self, request, *args, **kwargs):

        instance = self.get_object()

        if instance.statut != RelaisIlot.Statut.BROUILLON:
            raise PermissionDenied(
                "Suppression interdite : RelaisIlot non en brouillon."
            )

        return super().destroy(request, *args, **kwargs)

    def __str__(self):
        return f"{self.relais} - {self.ilot.nom}"

# ============================================================
# POMPE
# ============================================================

class Pompe(models.Model):

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="pompes"
    )

    ilot = models.ForeignKey(
        "Ilot",
        on_delete=models.PROTECT,
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

    def clean(self):
        if self.ilot.station_id != self.station_id:
            raise ValidationError(
                "La pompe doit appartenir à un îlot de la même station."
            )


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

from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class RelaisEquipe(models.Model):

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        SOUMIS = "SOUMIS", "Soumis"
        VALIDE = "VALIDE", "Validé"
        TRANSFERE = "TRANSFERE", "Transféré"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="relais_equipes"
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="relais_equipes"
    )

    debut_relais = models.DateTimeField()
    fin_relais = models.DateTimeField()

    equipe_sortante = models.CharField(max_length=100)
    equipe_entrante = models.CharField(max_length=100)

    status = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.BROUILLON
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
            models.Index(
                fields=["tenant", "status", "fin_relais"],
                name="idx_tenant_status_periode"
            ),
        ]

    @property
    def date_relais(self):
        return self.fin_relais.date()

    # =====================================================
    # VALIDATION STRUCTURELLE
    # =====================================================

    def clean(self):
        if self.fin_relais <= self.debut_relais:
            raise ValidationError(
                "La fin du relais doit être postérieure au début."
            )

        # Interdiction chevauchement période
        conflits = RelaisEquipe.objects.filter(
            station=self.station,
            status__in=[
                self.Statut.BROUILLON,
                self.Statut.SOUMIS,
                self.Statut.VALIDE
            ],
            debut_relais__lt=self.fin_relais,
            fin_relais__gt=self.debut_relais
        )

        if self.pk:
            conflits = conflits.exclude(pk=self.pk)

        if conflits.exists():
            raise ValidationError(
                "Un autre relais actif chevauche cette période."
            )
        
    def _consolider_finances(self):

        from finances_station.models import TransactionStation
        from django.db import transaction
        from stations.models import Depense

        depenses = Depense.objects.filter(
            station=self.station,
            statut=Depense.Statut.VALIDE,
            date_depense__gte=self.debut_relais.date(),
            date_depense__lte=self.fin_relais.date()
        )

        from django.db.models import Sum

        total_depenses = depenses.aggregate(
            total=Sum("montant")
        )["total"] or 0
        

        with transaction.atomic():

            # -------------------------------------------------
            # RECETTE (VENTE THÉORIQUE)
            # -------------------------------------------------

            total_volume = Decimal("0")
            total_theorique = Decimal("0")

            indexes = RelaisIndex.objects.filter(
                relais_ilot__relais=self
            ).select_related(
                "index_pompe__produit"
            )

            for idx in indexes:

                if idx.index_fin is None:
                    continue

                volume = idx.index_fin - idx.index_debut

                if volume <= 0:
                    continue

                prix = PrixCarburant.objects.filter(
                    tenant=self.tenant,
                    station=self.station,
                    produit=idx.index_pompe.produit,
                    actif=True
                ).values_list("prix_unitaire", flat=True).first() or 0

                total_volume += volume
                total_theorique += volume * prix


            TransactionStation.objects.update_or_create(
                source_type="RelaisEquipe_RECETTE",
                source_id=self.id,
                defaults={
                    "tenant": self.tenant,
                    "station": self.station,
                    "type": "RECETTE",
                    "montant": total_theorique,
                    "volume": total_volume,
                    "date": self.fin_relais,
                    "finance_status": "CONFIRMEE",
                }
            )

            # -------------------------------------------------
            # DEPENSES (SOMME VALIDÉE)
            # -------------------------------------------------

            if total_depenses > 0:

                TransactionStation.objects.update_or_create(
                    source_type="RelaisEquipe_DEPENSE",
                    source_id=self.id,
                    defaults={
                        "tenant": self.tenant,
                        "station": self.station,
                        "type": "DEPENSE",
                        "montant": total_depenses,
                        "volume": None,
                        "date": self.fin_relais,
                        "finance_status": "CONFIRMEE",
                    }
                )

    # =====================================================
    # PROPRIÉTÉS AGRÉGÉES (via RelaisIlot)
    # =====================================================

    @property
    def total_volume_vendu(self):
        return sum(
            ilot.total_volume_vendu
            for ilot in self.ilots.all()
        )

    @property
    def total_theorique(self):
        return sum(
            ilot.total_theorique
            for ilot in self.ilots.all()
        )

    @property
    def total_encaisse(self):
        return sum(
            ilot.total_encaisse
            for ilot in self.ilots.all()
        )

    @property
    def total_depenses(self):
        from stations.models import Depense

        depenses = Depense.objects.filter(
            station=self.station,
            statut=Depense.Statut.VALIDE,
            date_depense__gte=self.debut_relais.date(),
            date_depense__lte=self.fin_relais.date()
        )

        return sum(dep.montant for dep in depenses)

    @property
    def total_dettes(self):
        return sum(
            dette.montant for dette in self.dettes.all()
        )
    
    @property
    def est_complet(self):
        try:
            self._valider_structure_complete()
            return True
        except ValidationError:
            return False

    # =====================================================
    # MACHINE D'ÉTATS INDUSTRIELLE
    # =====================================================

    def changer_statut(self, nouveau_statut, user):

        transitions = {
            self.Statut.BROUILLON: [self.Statut.SOUMIS],
            self.Statut.SOUMIS: [self.Statut.VALIDE],
            self.Statut.VALIDE: [self.Statut.TRANSFERE],
            self.Statut.TRANSFERE: [],
        }

        if nouveau_statut not in transitions[self.status]:
            raise ValidationError("Transition invalide.")

        ancien_statut = self.status

        # =========================================================
        # SOUMISSION : BROUILLON → SOUMIS
        # =========================================================

        if nouveau_statut == self.Statut.SOUMIS:

            self._valider_structure_complete()

            self.soumis_par = user
            self.soumis_le = timezone.now()

            self.status = nouveau_statut
            super().save()

            RelaisAudit.objects.create(
                relais=self,
                tenant=self.tenant,
                ancien_statut=ancien_statut,
                nouveau_statut=nouveau_statut,
                action="CHANGEMENT_STATUT",
                effectue_par=user,
            )

            return

        # =========================================================
        # VALIDATION : SOUMIS → VALIDE
        # =========================================================

        if nouveau_statut == self.Statut.VALIDE:

            with transaction.atomic():

                # -------------------------------------------------
                # 1. Validation structurelle
                # -------------------------------------------------

                self._valider_structure_complete()

                # -------------------------------------------------
                # 2. Récupération des index du relais
                # -------------------------------------------------

                indexes = list(
                    RelaisIndex.objects
                    .filter(
                        relais_ilot__relais=self
                    )
                    .select_related(
                        "index_pompe",
                        "index_pompe__pompe",
                        "index_pompe__produit",
                        "relais_ilot",
                    )
                )

                if not indexes:
                    raise ValidationError(
                        "Impossible de valider : aucun index enregistré."
                    )

                # -------------------------------------------------
                # 3. Contrôle de tous les index
                # -------------------------------------------------

                for idx in indexes:

                    if idx.index_fin is None:
                        raise ValidationError(
                            "Tous les index doivent être complétés avant validation."
                        )

                    if idx.index_fin < idx.index_debut:
                        raise ValidationError(
                            "Index fin doit être supérieur ou égal à index début."
                        )

                # -------------------------------------------------
                # 4. Verrouillage des IndexPompe
                # -------------------------------------------------

                index_pompe_ids = {
                    idx.index_pompe_id
                    for idx in indexes
                }

                index_pompes = {
                    index_pompe.id: index_pompe
                    for index_pompe in (
                        IndexPompe.objects
                        .select_for_update()
                        .filter(
                            id__in=index_pompe_ids,
                            actif=True,
                        )
                    )
                }

                if len(index_pompes) != len(index_pompe_ids):
                    raise ValidationError(
                        "Un ou plusieurs index pompe sont introuvables ou inactifs."
                    )

                # -------------------------------------------------
                # 5. Vérification de la continuité des index
                # -------------------------------------------------

                for idx in indexes:

                    index_pompe = index_pompes[idx.index_pompe_id]

                    if index_pompe.index_courant != idx.index_debut:
                        raise ValidationError(
                            f"Incohérence d'index pour "
                            f"{index_pompe.pompe.reference} "
                            f"({index_pompe.produit.code}, Face {index_pompe.face}). "
                            f"Index courant : {index_pompe.index_courant}, "
                            f"index début du relais : {idx.index_debut}."
                        )

                # -------------------------------------------------
                # 7. Validation du relais
                # -------------------------------------------------

                self.valide_par = user
                self.valide_le = timezone.now()
                self.status = nouveau_statut

                # Le relais est maintenant VALIDE.
                # bypass_validation permet de passer le verrouillage
                # du save() lorsque le statut devient VALIDE.
                super().save()

                # -------------------------------------------------
                # 8. Création / suppression des écarts
                # -------------------------------------------------

                for ilot in self.ilots.all():

                    ecart = (
                        ilot.total_encaisse
                        - ilot.total_theorique
                    )

                    if ecart != Decimal("0"):

                        type_ecart = (
                            RelaisEcart.TypeEcart.EXCEDENT
                            if ecart > 0
                            else RelaisEcart.TypeEcart.MANQUE
                        )

                        RelaisEcart.objects.update_or_create(
                            relais_ilot=ilot,
                            defaults={
                                "tenant": ilot.tenant,
                                "relais": self,
                                "responsable": ilot.responsable,
                                "type_ecart": type_ecart,
                                "montant_theorique": ilot.total_theorique,
                                "montant_encaisse": ilot.total_encaisse,
                                "montant": abs(ecart),
                                "date_relais": self.fin_relais.date(),
                                "created_by": user,
                            }
                        )

                    else:

                        RelaisEcart.objects.filter(
                            relais_ilot=ilot
                        ).delete()

                # -------------------------------------------------
                # 9. Audit
                # -------------------------------------------------

                RelaisAudit.objects.create(
                    relais=self,
                    tenant=self.tenant,
                    ancien_statut=ancien_statut,
                    nouveau_statut=nouveau_statut,
                    action="CHANGEMENT_STATUT",
                    effectue_par=user,
                )

            return

        # =========================================================
        # TRANSFERT : VALIDE → TRANSFERE
        # =========================================================

        if nouveau_statut == self.Statut.TRANSFERE:

            if self.stock_applique:
                raise ValidationError("Stock déjà appliqué.")

            if self.status != self.Statut.VALIDE:
                raise ValidationError(
                    "Le relais doit être validé avant transfert."
                )

            if not self.ilots.exists():
                raise ValidationError(
                    "Aucun îlot associé au relais."
                )

            from stations.services.stock import appliquer_stock_relais
            from finances_station.models import TransactionStation
            from stations.models import Depense

            depenses = Depense.objects.filter(
                station=self.station,
                statut=Depense.Statut.VALIDE,
                date_depense__gte=self.debut_relais.date(),
                date_depense__lte=self.fin_relais.date(),
            )

            total_depenses = depenses.aggregate(
                total=Sum("montant")
            )["total"] or 0

            with transaction.atomic():

                indexes = list(
                    RelaisIndex.objects
                    .select_related("index_pompe")
                    .filter(relais_ilot__relais=self)
                )

                if not indexes:
                    raise ValidationError(
                        "Impossible de transférer le relais : aucun index trouvé."
                    )

                for idx in indexes:
                    if idx.index_fin is None:
                        raise ValidationError(
                            "Impossible de transférer le relais : "
                            "tous les index doivent être complétés."
                        )

                    if idx.index_fin < idx.index_debut:
                        raise ValidationError(
                            "Impossible de transférer le relais : "
                            "un index fin est inférieur à l'index début."
                        )

                index_pompe_ids = [idx.index_pompe_id for idx in indexes]

                index_pompes = {
                    ip.id: ip
                    for ip in IndexPompe.objects
                    .select_for_update()
                    .filter(
                        id__in=index_pompe_ids,
                        actif=True,
                    )
                }

                if len(index_pompes) != len(set(index_pompe_ids)):
                    raise ValidationError(
                        "Impossible de transférer le relais : "
                        "un ou plusieurs index pompe sont introuvables ou inactifs."
                    )

                for idx in indexes:
                    index_pompe = index_pompes[idx.index_pompe_id]

                    if index_pompe.index_courant != idx.index_debut:
                        raise ValidationError(
                            f"Conflit d'index pour {index_pompe.pompe.reference} "
                            f"({idx.index_pompe.produit.code}) : "
                            f"l'index courant est {index_pompe.index_courant}, "
                            f"alors que l'index début du relais est {idx.index_debut}."
                        )

                # -------------------------------------------------
                # 1. Application stock
                # -------------------------------------------------

                appliquer_stock_relais(self)

                # Synchronisation des index officiels
                for idx in indexes:
                    index_pompe = index_pompes[idx.index_pompe_id]

                    index_pompe.index_courant = idx.index_fin
                    index_pompe.save(update_fields=["index_courant"])

                # -------------------------------------------------
                # 2. Calcul volume et recette réelle
                # -------------------------------------------------

                total_volume = Decimal("0")
                total_theorique = Decimal("0")

                from stations.services.stock import (
                    get_volumes_par_produit
                )

                volumes = get_volumes_par_produit(self)

                for produit_id, volume in volumes.items():

                    prix = (
                        PrixCarburant.objects
                        .filter(
                            tenant=self.tenant,
                            station=self.station,
                            produit_id=produit_id,
                            actif=True,
                        )
                        .values_list(
                            "prix_unitaire",
                            flat=True
                        )
                        .first()
                        or 0
                    )

                    total_volume += volume
                    total_theorique += volume * prix

                # -------------------------------------------------
                # 3. RECETTE
                # -------------------------------------------------

                TransactionStation.objects.update_or_create(
                    source_type="RelaisEquipe_RECETTE",
                    source_id=self.id,
                    defaults={
                        "tenant": self.tenant,
                        "station": self.station,
                        "type": "RECETTE",
                        "montant": total_theorique,
                        "volume": total_volume,
                        "date": self.fin_relais,
                        "finance_status": "CONFIRMEE",
                    }
                )

                # -------------------------------------------------
                # 4. RECETTE LUBRIFIANTS
                # -------------------------------------------------

                from stations.models_lubrifiant.vente import VenteLubrifiant

                total_lubrifiants = (
                    VenteLubrifiant.objects
                    .filter(
                        tenant=self.tenant,
                        station=self.station,
                        relais=self,
                    )
                    .aggregate(
                        total=Sum("montant")
                    )["total"] or Decimal("0")
                )

                TransactionStation.objects.update_or_create(
                    source_type="RelaisEquipe_LUBRIFIANTS",
                    source_id=self.id,
                    defaults={
                        "tenant": self.tenant,
                        "station": self.station,
                        "type": "RECETTE",
                        "montant": total_lubrifiants,
                        "volume": None,
                        "date": self.fin_relais,
                        "finance_status": "CONFIRMEE",
                    }
                )

                # -------------------------------------------------
                # 5. RECETTE OPÉRATIONS DE BAIE
                # -------------------------------------------------

                from stations.models_baie import OperationBaie

                total_baie = (
                    OperationBaie.objects
                    .filter(
                        tenant=self.tenant,
                        station=self.station,
                        relais=self,
                    )
                    .aggregate(
                        total=Sum("montant")
                    )["total"] or Decimal("0")
                )

                TransactionStation.objects.update_or_create(
                    source_type="RelaisEquipe_BAIE",
                    source_id=self.id,
                    defaults={
                        "tenant": self.tenant,
                        "station": self.station,
                        "type": "RECETTE",
                        "montant": total_baie,
                        "volume": None,
                        "date": self.fin_relais,
                        "finance_status": "CONFIRMEE",
                    }
                )

                # -------------------------------------------------
                # 6. DEPENSES VALIDÉES
                # -------------------------------------------------

                if total_depenses > 0:

                    TransactionStation.objects.update_or_create(
                        source_type="RelaisEquipe_DEPENSE",
                        source_id=self.id,
                        defaults={
                            "tenant": self.tenant,
                            "station": self.station,
                            "type": "DEPENSE",
                            "montant": total_depenses,
                            "volume": None,
                            "date": self.fin_relais,
                            "finance_status": "CONFIRMEE",
                        }
                    )

                self.stock_applique = True
                self.status = nouveau_statut

                super().save()

                # -------------------------------------------------
                # Audit
                # -------------------------------------------------

                RelaisAudit.objects.create(
                    relais=self,
                    tenant=self.tenant,
                    ancien_statut=ancien_statut,
                    nouveau_statut=nouveau_statut,
                    action="CHANGEMENT_STATUT",
                    effectue_par=user,
                )

            return

    
    # -------------------------------------------------
    # VALIDATION RELAIS
    # -------------------------------------------------
    def _valider_structure_complete(self):
        """
        Vérifie que le relais est exploitable métier.
        Tous les îlots doivent posséder des index complets.
        """

        ilots = self.ilots.all()

        if not ilots.exists():
            raise ValidationError(
                "Impossible de soumettre : aucun îlot associé."
            )

        for ilot in ilots:

            indexes = ilot.indexes.all()

            if not indexes.exists():
                raise ValidationError(
                    f"L'îlot '{ilot}' ne contient aucun index."
                )

            for idx in indexes:

                if idx.index_debut is None:
                    raise ValidationError(
                        f"Index début incomplet sur l'îlot '{ilot}'."
                    )

                if idx.index_fin is None:
                    raise ValidationError(
                        f"Index fin incomplet sur l'îlot '{ilot}'."
                    )

                if idx.index_fin < idx.index_debut:
                    raise ValidationError(
                        f"Index fin inférieur à l'index début "
                        f"sur l'îlot '{ilot}'."
                    )

    # =====================================================
    # VERROUILLAGE STRUCTUREL
    # =====================================================

    def delete(self, *args, **kwargs):

        if self.status in [
            self.Statut.VALIDE,
            self.Statut.TRANSFERE
        ]:
            raise ValidationError(
                "Suppression impossible : relais déjà validé ou transféré."
            )

        super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):

        bypass = kwargs.pop("bypass_validation", False)

        if self.pk and not bypass:
            ancien = RelaisEquipe.objects.get(pk=self.pk)

            if ancien.status not in [
                self.Statut.BROUILLON,
                self.Statut.SOUMIS,  # ✅ autoriser soumis
            ]:
                raise ValidationError(
                    "Modification impossible : relais validé ou transféré."
                )

        super().save(*args, **kwargs)


class RelaisJauge(models.Model):

    relais = models.ForeignKey(
        "stations.RelaisEquipe",
        on_delete=models.CASCADE,
        related_name="jauges"
    )

    produit = models.ForeignKey(
        "stations.ProduitCarburant",
        on_delete=models.PROTECT,
        related_name="jauges_relais"
    )

    jauge_debut = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    jauge_fin = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        db_table = "stations_relais_jauges"

        constraints = [
            models.UniqueConstraint(
                fields=["relais", "produit"],
                name="unique_jauge_produit_relais"
            )
        ]

        ordering = ["produit__code"]

    def __str__(self):
        return (
            f"{self.relais} - "
            f"{self.produit.code}"
        )


class RelaisIndex(models.Model):

    relais_ilot = models.ForeignKey(
        "stations.RelaisIlot",
        on_delete=models.CASCADE,
        related_name="indexes"
    )

    index_pompe = models.ForeignKey(
        "stations.IndexPompe",
        on_delete=models.PROTECT
    )

    index_debut = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    index_fin = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    retour_en_cuve = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

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
                fields=["relais_ilot", "index_pompe"],
                name="unique_index_per_relais_ilot"
            )
        ]

    @property
    def volume_vendu(self):

        if self.index_fin is None:
            return 0

        return self.index_fin - self.index_debut

    @property
    def volume_reellement_vendu(self):

        volume = self.volume_vendu

        if volume <= 0:
            return Decimal("0")

        retour = self.retour_en_cuve or Decimal("0")

        return volume - retour

    def clean(self):

        # 🔒 Vérifier cohérence station
        if self.index_pompe.pompe.station_id != self.relais_ilot.relais.station_id:
            raise ValidationError(
                "Index pompe invalide pour ce relais."
            )

        # 🔒 Vérifier index cohérent
        if (
            self.index_fin is not None
            and self.index_debut is not None
            and self.index_fin < self.index_debut
        ):
            raise ValidationError(
                "L'index fin doit être supérieur ou égal à l'index début."
            )

        # 🔒 Verrouillage si relais transféré
        if self.relais_ilot.relais.status == "TRANSFERE":
            raise ValidationError(
                "Relais transféré : modification interdite."
            )

        if (
            self.retour_en_cuve is not None
            and self.retour_en_cuve < 0
        ):
            raise ValidationError(
                "Le retour en cuve ne peut pas être négatif."
            )

        if (
            self.index_fin is not None
            and self.retour_en_cuve is not None
            and self.retour_en_cuve > self.volume_vendu
        ):
            raise ValidationError(
                "Le retour en cuve ne peut pas être supérieur au volume distribué."
            )


# ============================================================
# RELAIS INDEX PHOTO
# ============================================================
class RelaisIndexPhoto(models.Model):

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        OCR_EFFECTUE = "OCR_EFFECTUE", "OCR effectué"
        VALIDE = "VALIDE", "Validé"
        REJETE = "REJETE", "Rejeté"

    relais_index = models.ForeignKey(
        "stations.RelaisIndex",
        on_delete=models.PROTECT,
        related_name="photos",
    )

    photo = models.ImageField(
        upload_to="relais/indexes/%Y/%m/%d/",
    )

    valeur_ocr = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    confiance_ocr = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    valeur_validee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    date_capture = models.DateTimeField(
        auto_now_add=True,
    )

    capture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="photos_indexes_capturees",
    )

    validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="photos_indexes_validees",
    )

    date_validation = models.DateTimeField(
        null=True,
        blank=True,
    )

    commentaire_validation = models.TextField(
        blank=True,
        default="",
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
    )

    class Meta:
        ordering = ["-date_capture"]

        indexes = [
            models.Index(
                fields=["relais_index", "date_capture"]
            ),
            models.Index(
                fields=["statut"]
            ),
        ]

    def __str__(self):
        return (
            f"Photo index {self.relais_index_id} "
            f"- {self.date_capture}"
        )


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
            models.Index(fields=["tenant", "relais"]),
            models.Index(fields=["relais", "date_action"]),
        ]

    def __str__(self):
        return (
            f"{self.relais.id} "
            f"{self.ancien_statut} → {self.nouveau_statut}"
        )


class CategorieDepense(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="categories_depense"
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="categories_depense"
    )

    nom = models.CharField(max_length=100)
    actif = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("station", "nom")
        ordering = ["nom"]

        indexes = [
            models.Index(fields=["tenant", "station"]),
        ]


class Depense(models.Model):

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        VALIDE = "VALIDE", "Validé"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="depenses"
    )

    relais = models.ForeignKey(
        "stations.RelaisEquipe",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="depenses",
    )

    categorie = models.ForeignKey(
        "stations.CategorieDepense",
        on_delete=models.PROTECT
    )

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    description = models.TextField(blank=True)

    date_depense = models.DateField()

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.BROUILLON
    )

    # contre écriture
    depense_reference = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="corrections"
    )

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        related_name="depenses_creees"
    )

    validated_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="depenses_validees"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stations_depenses"
        ordering = ["-date_depense", "-id"]
        indexes = [
            models.Index(fields=["tenant", "station"]),
            models.Index(fields=["tenant", "statut"]),
            models.Index(fields=["station", "date_depense"]),
        ]

    def save(self, *args, **kwargs):

        if self.pk:
            ancien = Depense.objects.get(pk=self.pk)

            if ancien.statut == self.Statut.VALIDE:
                raise ValidationError(
                    "Dépense validée : modification interdite."
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):

        if self.statut == self.Statut.VALIDE:
            raise ValidationError(
                "Dépense validée : suppression interdite."
            )

        super().delete(*args, **kwargs)

    def valider(self, user):

        if self.statut != self.Statut.BROUILLON:
            raise ValidationError("Dépense déjà validée.")

        from finances_station.models import TransactionStation
        from django.db import transaction

        with transaction.atomic():

            self.statut = self.Statut.VALIDE
            self.validated_by = user
            self.validated_at = timezone.now()

            super().save()

            TransactionStation.objects.create(
                tenant=self.tenant,
                station=self.station,
                type="DEPENSE",
                montant=self.montant,
                volume=None,
                date=self.date_depense,
                source_type="DEPENSE_STATION",
                source_id=self.id,
                finance_status="CONFIRMEE"
            )

    def contre_ecriture(self, user):

        if self.statut != self.Statut.VALIDE:
            raise ValidationError("Seules les dépenses validées peuvent être corrigées.")

        return Depense.objects.create(
            tenant=self.tenant,
            station=self.station,
            categorie=self.categorie,
            montant=-self.montant,
            description=f"Contre-écriture : {self.description}",
            date_depense=timezone.now().date(),
            statut=self.Statut.BROUILLON,
            depense_reference=self,
            created_by=user
        )


class ModePaiement(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="modes_paiement"
    )

    nom = models.CharField(max_length=100)

    code = models.CharField(
        max_length=50
    )

    actif = models.BooleanField(
        default=True,
        db_index=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        unique_together = ("tenant", "code")
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class EncaissementRelais(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE
    )

    relais_ilot = models.ForeignKey(
        "stations.RelaisIlot",
        on_delete=models.CASCADE,
        related_name="encaissements"
    )

    mode_paiement = models.ForeignKey(
        ModePaiement,
        on_delete=models.PROTECT
    )

    montant = models.DecimalField(max_digits=14, decimal_places=2)

    date = models.DateField()

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "relais_ilot"]),
        ]

    def clean(self):
        if self.relais_ilot.relais.status == "TRANSFERE":
            raise ValidationError(
                "Relais transféré : modification interdite."
            )
        
    def save(self, *args, **kwargs):

        if self.relais_ilot.relais.status == "TRANSFERE":
            raise ValidationError(
                "Relais transféré : modification interdite."
            )

        super().save(*args, **kwargs)


    def delete(self, *args, **kwargs):

        if self.relais_ilot.relais.status == "TRANSFERE":
            raise ValidationError(
                "Relais transféré : suppression interdite."
            )

        super().delete(*args, **kwargs)


class Versement(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE
    )

    relais_ilot = models.ForeignKey(
        "stations.RelaisIlot",
        on_delete=models.CASCADE,
        related_name="versements"
    )

    montant_remis = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    date_versement = models.DateField()

    reference = models.CharField(max_length=100)

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("relais_ilot",)
        indexes = [
            models.Index(fields=["tenant", "relais_ilot"]),
        ]

    def clean(self):

        relais = self.relais_ilot.relais

        # Vérifier s'il existe déjà un versement
        versement_existant = Versement.objects.filter(
            relais_ilot=self.relais_ilot
        ).exclude(pk=self.pk).exists()

        # Interdiction seulement dans ce cas précis
        if relais.status == "TRANSFERE" and versement_existant:
            raise ValidationError(
                "Un versement existe déjà pour cet îlot (relais transféré)."
            )
        
    def save(self, *args, **kwargs):

        self.clean()

        super().save(*args, **kwargs)


    def delete(self, *args, **kwargs):

        relais = self.relais_ilot.relais

        if self.relais_ilot.relais.status == "TRANSFERE":
            raise ValidationError(
                "Relais transféré : suppression interdite."
            )

        super().delete(*args, **kwargs)


class VersementDetail(models.Model):

    versement = models.ForeignKey(
        "stations.Versement",
        on_delete=models.CASCADE,
        related_name="details"
    )

    mode_paiement = models.ForeignKey(
        "stations.ModePaiement",
        on_delete=models.PROTECT
    )

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    class Meta:
        unique_together = ("versement", "mode_paiement")

    def __str__(self):
        return f"{self.mode_paiement.nom} - {self.montant}"
        

class ClientStation(models.Model):

    class TypeClient(models.TextChoices):
        PARTICULIER = "PARTICULIER", "Particulier"
        ENTREPRISE = "ENTREPRISE", "Entreprise"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="clients_station"
    )

    type_client = models.CharField(
        max_length=20,
        choices=TypeClient.choices,
        default=TypeClient.PARTICULIER
    )

    nom = models.CharField(max_length=150)

    cni = models.CharField(max_length=20, blank=True)

    telephone = models.CharField(max_length=30, blank=True)

    email = models.EmailField(
        blank=True,
        null=True
    )

    adresse = models.CharField(
        max_length=255,
        blank=True
    )

    registre_commerce = models.CharField(
        max_length=100,
        blank=True
    )

    plafond_credit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    actif = models.BooleanField(default=True)

    agree_par_admin = models.BooleanField(default=False)

    station_limitee = models.ForeignKey(
        "stations.Station",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cni"],
                name="unique_client_cni_par_tenant"
            ),
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=Q(email__isnull=False),
                name="unique_client_email_par_tenant"
            ),
        ]

        indexes = [
            models.Index(fields=["tenant"]),
            models.Index(fields=["tenant", "actif"]),
            models.Index(fields=["tenant", "agree_par_admin"]),
        ]

    def __str__(self):
        return self.nom

    @property
    def total_dette_active(self):

        return (
            self.dettes
            .filter(statut__in=["EN_ATTENTE", "PARTIELLE"])
            .aggregate(
                total=Coalesce(
                    Sum(
                        F("montant_initial") - F("montant_regle"),
                        output_field=DecimalField()
                    ),
                    Value(0),
                    output_field=DecimalField()
                )
            )["total"]
        )
    
    @property
    def credit_disponible(self):
        return max(
            self.plafond_credit -
            self.total_dette_active,
            0
        )


class DetteStation(models.Model):

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        PARTIELLE = "PARTIELLE", "Partiellement réglée"
        REGLEE = "REGLEE", "Réglée"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.CASCADE,
        related_name="dettes"
    )

    relais = models.ForeignKey(
        "stations.RelaisEquipe",
        on_delete=models.PROTECT,
        related_name="dettes",
    )

    client = models.ForeignKey(
        "stations.ClientStation",
        on_delete=models.PROTECT,
        related_name="dettes"
    )

    transaction = models.ForeignKey(
        "finances_station.TransactionStation",
        on_delete=models.PROTECT,
        related_name="dettes"
    )

    produit = models.ForeignKey(
        "stations.ProduitCarburant",
        on_delete=models.PROTECT,
        related_name="dettes"
    )

    prix_unitaire = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    volume = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    montant_initial = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    montant_regle = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE
    )

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "station"]),
            models.Index(fields=["tenant", "client"]),
            models.Index(fields=["statut"]),
        ]

    def clean(self):

        if not self.client.agree_par_admin:
            raise ValidationError(
                "Client non validé par l'administrateur."
            )

        if self.montant_initial <= 0:
            raise ValidationError(
                "Montant invalide."
            )

        if self.volume <= 0:
            raise ValidationError(
                "Volume invalide."
            )

        # contrôle plafond crédit
        total = self.client.total_dette_active + self.montant_initial

        if total > self.client.plafond_credit:
            raise ValidationError(
                "Plafond de crédit dépassé."
            )
        
        if self.client.station_limitee:

            if self.client.station_limitee != self.station:

                raise ValidationError(
                    "Ce client est limité à une autre station."
                )

    @property
    def montant_restant(self):
        return self.montant_initial - self.montant_regle

    def appliquer_reglement(self, montant):

        if montant <= 0:
            raise ValidationError("Montant invalide.")

        if montant > self.montant_restant:
            raise ValidationError(
                "Montant supérieur au restant."
            )

        self.montant_regle += montant

        if self.montant_restant == 0:
            self.statut = self.Statut.REGLEE
        else:
            self.statut = self.Statut.PARTIELLE

        self.save(update_fields=[
            "montant_regle",
            "statut"
        ])

    def save(self, *args, **kwargs):

        if self.pk:

            ancien = DetteStation.objects.get(pk=self.pk)

            if ancien.transaction.finance_status == "CONFIRMEE":

                update_fields = kwargs.get(
                    "update_fields"
                )

                champs_autorises = {
                    "montant_regle",
                    "statut",
                }

                if update_fields:

                    if not set(update_fields).issubset(
                        champs_autorises
                    ):
                        raise ValidationError(
                            "Transaction confirmée : modification interdite."
                        )

                else:
                    raise ValidationError(
                        "Transaction confirmée : modification interdite."
                    )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):

        if self.transaction.finance_status == "CONFIRMEE":
            raise ValidationError(
                "Transaction confirmée : suppression interdite."
            )

        super().delete(*args, **kwargs)


class ReglementDette(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE
    )

    dette = models.ForeignKey(
        "stations.DetteStation",
        on_delete=models.CASCADE,
        related_name="reglements"
    )

    mode_paiement = models.ForeignKey(
        "stations.ModePaiement",
        on_delete=models.PROTECT,
        related_name="reglements_dette"
    )

    reference_paiement = models.CharField(
        max_length=100,
        blank=True
    )

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        indexes = [
            models.Index(fields=["tenant"]),
            models.Index(fields=["dette"]),
        ]

    def __str__(self):
        return f"Reglement {self.montant} - Dette {self.dette_id}"



class RelaisEcart(models.Model):

    class TypeEcart(models.TextChoices):
        MANQUE = "MANQUE", "Manque"
        EXCEDENT = "EXCEDENT", "Excédent"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="relais_ecarts"
    )

    relais = models.ForeignKey(
        "stations.RelaisEquipe",
        on_delete=models.CASCADE,
        related_name="ecarts",
        null=True,
        blank=True
    )

    relais_ilot = models.OneToOneField(
        "stations.RelaisIlot",
        on_delete=models.CASCADE,
        related_name="ecart"
    )

    responsable = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        related_name="ecarts_relais"
    )

    type_ecart = models.CharField(
        max_length=20,
        choices=TypeEcart.choices
    )

    montant_theorique = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        null=True,
        blank=True
    )

    montant_encaisse = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        null=True,
        blank=True
    )

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    date_relais = models.DateField(
        null=True,
        blank=True
    )

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        related_name="ecarts_crees",
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-date_relais", "-created_at"]

        indexes = [
            models.Index(fields=["tenant", "responsable"]),
            models.Index(fields=["tenant", "date_relais"]),
            models.Index(fields=["relais"]),
        ]

    def __str__(self):
        return (
            f"{self.relais.id} - "
            f"{self.responsable.username} - "
            f"{self.type_ecart} - "
            f"{self.montant}"
        )
    
    @property
    def montant_rembourse(self):

        return sum(
            r.montant
            for r in self.remboursements.all()
        )

    @property
    def reste_a_rembourser(self):

        return (
            self.montant
            - self.montant_rembourse
        )

    @property
    def est_solde(self):

        return self.reste_a_rembourser <= 0


class RemboursementEcart(models.Model):

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="remboursements_ecarts"
    )

    ecart = models.ForeignKey(
        "stations.RelaisEcart",
        on_delete=models.PROTECT,
        related_name="remboursements"
    )

    responsable = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        related_name="remboursements_ecarts"
    )

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    date_remboursement = models.DateField()

    commentaire = models.TextField(
        blank=True,
        null=True
    )

    created_by = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.PROTECT,
        related_name="remboursements_ecarts_crees"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-date_remboursement"]

    def __str__(self):
        return (
            f"{self.responsable} - "
            f"{self.montant}"
        )
    
    def save(self, *args, **kwargs):

        creation = self.pk is None

        self.full_clean()

        with transaction.atomic():

            super().save(*args, **kwargs)

            if creation:

                from finances_station.models import TransactionStation

                TransactionStation.objects.create(
                    tenant=self.tenant,
                    station=self.ecart.relais.station,
                    type="RECETTE",
                    montant=self.montant,
                    volume=None,
                    date=timezone.now(),
                    source_type="REMBOURSEMENT_ECART",
                    source_id=self.id,
                    finance_status="CONFIRMEE",
                )

    def clean(self):

        if self.montant <= 0:
            raise ValidationError(
                "Montant invalide."
            )

        if self.montant > self.ecart.reste_a_rembourser:
            raise ValidationError(
                "Le remboursement dépasse le solde restant."
            )


class Notification(models.Model):
    TYPE_CHOICES = [
        ("RELAIS_A_VALIDER", "Relais à valider"),
        ("RELAIS_A_TRANSFERER", "Relais à transférer"),
        ("DEPOTAGE_A_VALIDER", "Dépotage à valider"),
        ("DEPOTAGE_A_TRANSFERER", "Dépotage à transférer"),
        ("STOCK_CRITIQUE", "Stock critique"),
    ]

    ROLE_CHOICES = [
        ("POMPISTE", "Pompiste"),
        ("SUPERVISEUR", "Superviseur"),
        ("GERANT", "Gérant"),
    ]

    tenant_id = models.UUIDField()
    station_id = models.UUIDField()

    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    message = models.TextField()

    role_cible = models.CharField(max_length=30, choices=ROLE_CHOICES)

    lien = models.CharField(max_length=255, null=True, blank=True)

    lu = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


from stations.models_lubrifiant import (
    StockLubrifiant,
    MouvementStockLubrifiant,
    VenteLubrifiant,
)