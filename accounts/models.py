from django.db import models
from django.contrib.auth.models import AbstractUser

from accounts.constants import UserRole


class Utilisateur(AbstractUser):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="utilisateurs",
        null=True
    )

    station = models.ForeignKey(
        "stations.Station",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    stations_administrees = models.ManyToManyField(
        "stations.Station",
        blank=True,
        related_name="admins"
    )

    ROLE_CHOICES = (
        ('SuperAdmin', 'SuperAdmin'),
        ('AdminTenantFinance', 'Administrateur Saas finance'),
        ('AdminTenantStation', 'Administrateur Saas station'),
        ('Tresorier', 'Trésorier'),



        # Station – hiérarchie
        ('Gerant', 'Chef de station'),
        ('Superviseur', 'Chef de piste'),

        # Station – opérationnel
        ('Pompiste', 'Agent de distribution'),
        ('Caissier', 'Vendeur boutique'),
        ('PersonnelEntretien', 'Nettoyage'),
        ('Securite', 'Prévention des risques'),

        # Autres
        ('Collecteur', 'Collecteur'),
        ('Lecteur', 'Lecteur'),
    )

    role = models.CharField(
        max_length=30,
        choices=UserRole.CHOICES,
        default='Lecteur'
    )

    MODULE_CHOICES = (
        ("finance", "Finance"),
        ("station", "Station"),
    )

    module = models.CharField(
        max_length=20,
        choices=MODULE_CHOICES,
        null=True,
        blank=True
    )

    def save(self, *args, **kwargs):
        if self.role in (
            UserRole.GERANT,
            UserRole.SUPERVISEUR,
            UserRole.POMPISTE,
            UserRole.CAISSIER,
            UserRole.PERSONNEL_ENTRETIEN,
            UserRole.SECURITE,
        ):
            self.module = "station"

        elif self.role == UserRole.ADMIN_TENANT_STATION:
            self.module = "admin-tenant-station"

        elif self.role == UserRole.ADMIN_TENANT_FINANCE:
            self.module = "finance"

        elif self.role == UserRole.SUPERADMIN:
            self.module = "admin"

        super().save(*args, **kwargs)
