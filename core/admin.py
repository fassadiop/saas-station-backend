# core/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Tenant, Membre, Projet, Transaction, Cotisation

User = get_user_model()

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_structure', 'devise', 'actif')

@admin.register(Membre)
class MembreAdmin(admin.ModelAdmin):
    list_display = ('nom_membre', 'contact', 'tenant', 'statut')
    list_filter = ('tenant', 'statut')

@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    list_display = ('nom', 'tenant', 'budget', 'statut')
    list_filter = ('tenant', 'statut')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'montant', 'date', 'categorie', 'tenant', 'projet')
    list_filter = ('type', 'categorie', 'tenant')

@admin.register(Cotisation)
class CotisationAdmin(admin.ModelAdmin):
    list_display = ('membre', 'montant', 'date_paiement', 'periode', 'tenant', 'statut')
    list_filter = ('periode', 'tenant')



User = get_user_model()
admin.site.register(User)