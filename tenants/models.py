import uuid
from django.db import models
from django.conf import settings

class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=150, unique=True)
    type_structure = models.CharField(max_length=50)
    date_creation = models.DateField(auto_now_add=True)
    devise = models.CharField(max_length=10, default='XOF')
    actif = models.BooleanField(default=True)

    created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="tenants_created"
    )

    class Meta:
        db_table = "core_tenant"

    def __str__(self):
        return self.nom


