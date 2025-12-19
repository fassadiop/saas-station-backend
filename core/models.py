import uuid
import os
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from django.conf import settings

from tenants.models import Tenant


# class Tenant(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     nom = models.CharField(max_length=150, unique=True)
#     type_structure = models.CharField(max_length=50)
#     date_creation = models.DateField(auto_now_add=True)
#     devise = models.CharField(max_length=10, default='XOF')
#     actif = models.BooleanField(default=True)
    
#     created_by = models.ForeignKey(
#         'accounts.Utilisateur',
#         on_delete=models.SET_NULL,
#         null=True,
#         related_name="tenants_crees"
#     )

#     def __str__(self):
#         return self.nom

# class Utilisateur(AbstractUser):
#     tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="utilisateurs", null=True)
#     ROLE_CHOICES = (
#         ('SuperAdmin','SuperAdmin'),
#         ('AdminTenant','AdminTenant'),
#         ('Tresorier','Tresorier'),
#         ('Collecteur','Collecteur'),
#         ('Lecteur','Lecteur'),
#     )
#     role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Lecteur')

class Membre(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="membres")
    nom_membre = models.CharField(max_length=100)
    contact = models.CharField(max_length=50, blank=True)
    statut = models.CharField(max_length=20, default='Actif')

class Projet(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="projets")
    nom = models.CharField(max_length=150)
    budget = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, default='En_cours')

class Transaction(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="transactions")
    projet = models.ForeignKey(Projet, on_delete=models.SET_NULL, null=True, blank=True)

    TYPE_CHOICES = (('Recette','Recette'),('Depense','Depense'))
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)
    categorie = models.CharField(max_length=80)
    mode_paiement = models.CharField(max_length=30, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    fichier_recu = models.FileField(upload_to='receipts/%Y/%m/', null=True, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    # ➤ Ajouter ce champ manquant !
    mois = models.CharField(max_length=7, editable=False)

    class Meta:
        ordering = ["-date"]

    def save(self, *args, **kwargs):
        self.mois = self.date.strftime("%Y-%m")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.type} {self.montant} ({self.tenant})"
    

class Cotisation(models.Model):
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name="cotisations")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date_paiement = models.DateField(default=timezone.now)
    periode = models.CharField(max_length=20)
    statut = models.CharField(max_length=20, default='Payé')

class FileUpload(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="uploads")
    transaction = models.ForeignKey('Transaction', on_delete=models.SET_NULL, null=True, blank=True, related_name="uploads")
    uploaded_by = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
        if self.file and not self.size:
            try:
                self.size = self.file.size
            except Exception:
                self.size = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.filename} ({self.tenant})"