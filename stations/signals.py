from django.db.models.signals import post_save
from django.dispatch import receiver

from stations.models import Station
from stations.models_depotage.cuve import Cuve


@receiver(post_save, sender=Station)
def create_default_cuves(sender, instance, created, **kwargs):
    if not created:
        return

    for produit in ["ESSENCE", "GASOIL"]:
        Cuve.objects.get_or_create(
            tenant=instance.tenant,
            station=instance,
            produit=produit,
            defaults={
                "capacite_max": 0,
                "stock_actuel": 0,
                "seuil_alerte": 0,
                "actif": True,
            },
        )
