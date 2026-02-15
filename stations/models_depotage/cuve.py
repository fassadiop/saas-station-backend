from django.db import models, transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from stations.models_produit import ProduitCarburant

class CuveStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active (ouverte)"
    STANDBY = "STANDBY", "En attente"
    EN_DEPOTAGE = "EN_DEPOTAGE", "En dépotage"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    HORS_SERVICE = "HORS_SERVICE", "Hors service"


ALLOWED_TRANSITIONS = {
    CuveStatus.STANDBY: [
        CuveStatus.ACTIVE,
        CuveStatus.EN_DEPOTAGE,
        CuveStatus.MAINTENANCE,
        CuveStatus.HORS_SERVICE,
    ],
    CuveStatus.ACTIVE: [
        CuveStatus.STANDBY,
        CuveStatus.MAINTENANCE,
        CuveStatus.HORS_SERVICE,
    ],
    CuveStatus.EN_DEPOTAGE: [
        CuveStatus.STANDBY,
    ],
    CuveStatus.MAINTENANCE: [
        CuveStatus.STANDBY,
        CuveStatus.HORS_SERVICE,
    ],
    CuveStatus.HORS_SERVICE: [
        CuveStatus.STANDBY,
    ],
}


class Cuve(models.Model):

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    station = models.ForeignKey("stations.Station", on_delete=models.CASCADE)
    produit = models.ForeignKey(
        "stations.ProduitCarburant",
        on_delete=models.PROTECT
    )

    capacite_max = models.DecimalField(max_digits=12, decimal_places=2)
    stock_actuel = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    seuil_alerte = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    statut = models.CharField(
        max_length=20,
        choices=CuveStatus.choices,
        default=CuveStatus.STANDBY
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["station", "produit"],
                condition=Q(statut=CuveStatus.ACTIVE),
                name="unique_active_cuve_per_product_station",
            )
        ]

    def changer_statut(self, nouveau_statut):

        if self.statut == nouveau_statut:
            return

        if nouveau_statut not in ALLOWED_TRANSITIONS.get(self.statut, []):
            raise ValidationError(
                f"Transition interdite : {self.statut} → {nouveau_statut}"
            )

        # Empêcher activation incohérente
        if nouveau_statut == CuveStatus.ACTIVE:
            if self.statut in [
                CuveStatus.HORS_SERVICE,
                CuveStatus.EN_DEPOTAGE,
                CuveStatus.MAINTENANCE,
            ]:
                raise ValidationError(
                    "Impossible d'activer cette cuve depuis son état actuel."
                )

            self._activer_cuve_unique()

        self.statut = nouveau_statut
        self.save(update_fields=["statut", "updated_at"])


    def _activer_cuve_unique(self):

        from stations.models_depotage.cuve import Cuve

        with transaction.atomic():
            Cuve.objects.filter(
                station=self.station,
                produit=self.produit,
                statut=CuveStatus.ACTIVE,
            ).exclude(id=self.id).update(
                statut=CuveStatus.STANDBY
            )
