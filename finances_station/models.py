# saas-backend/finances_station/models.py
from django.db import models
from tenants.models import Tenant
from stations.models import Station


class TransactionStation(models.Model):
    FINANCE_STATUS = (
        ("PROVISOIRE", "Provisoire"),
        ("CONFIRMEE", "Confirmée"),
    )

    finance_status = models.CharField(
        max_length=15,
        choices=FINANCE_STATUS,
        default="PROVISOIRE"
    )
    TYPE_CHOICES = (
        ("RECETTE", "Recette"),
        ("DEPENSE", "Dépense"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    station = models.ForeignKey(Station, on_delete=models.CASCADE)

    type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    # 🔗 Traçabilité source STATION
    source_type = models.CharField(max_length=50)
    source_id = models.PositiveIntegerField()

    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("source_type", "source_id")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.type} - {self.montant} ({self.station})"
