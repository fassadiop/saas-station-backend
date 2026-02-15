# stations/management/commands/init_cuves_stations.py

from django.core.management.base import BaseCommand
from stations.models import Station
from stations.models_depotage.cuve import Cuve


class Command(BaseCommand):
    help = "Initialise les cuves ESSENCE et GASOIL pour toutes les stations"

    def handle(self, *args, **options):
        total_created = 0

        for station in Station.objects.all():
            for produit in ["ESSENCE", "GASOIL"]:
                _, created = Cuve.objects.get_or_create(
                    tenant=station.tenant,
                    station=station,
                    produit=produit,
                    defaults={
                        "capacite_max": 0,
                        "stock_actuel": 0,
                        "seuil_alerte": 0,
                        "actif": True,
                    },
                )
                if created:
                    total_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Cuve {produit} créée pour {station.nom}"
                        )
                    )

        self.stdout.write(
            self.style.WARNING(
                f"Total cuves créées : {total_created}"
            )
        )
