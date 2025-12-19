import uuid
import os
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings

from tenants.models import Tenant

class Utilisateur(AbstractUser):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="utilisateurs", null=True)
    station = models.ForeignKey("stations.Station", on_delete=models.SET_NULL, null=True, blank=True)
    ROLE_CHOICES = (
        ('SuperAdmin','SuperAdmin'),
        ('AdminTenant','AdminTenant'),
        ('Tresorier','Tresorier'),
        ('Collecteur','Collecteur'),
        ('Lecteur','Lecteur'),
        ("ChefStation", "Chef de station"),
        ("Superviseur", "Superviseur"),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Lecteur')
