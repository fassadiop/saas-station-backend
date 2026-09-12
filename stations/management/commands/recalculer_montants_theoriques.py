from decimal import Decimal

from django.core.management.base import BaseCommand

from stations.models import (
    RelaisIndex,
    PrixCarburant,
)


class Command(BaseCommand):

    help = (
        "Recalcule prix_unitaire et montant_theorique "
        "de tous les RelaisIndex"
    )

    def handle(self, *args, **kwargs):

        total = 0
        erreurs = 0

        indexes = (
            RelaisIndex.objects
            .select_related(
                "relais_ilot__relais",
                "index_pompe__produit",
            )
        )

        for idx in indexes:

            try:

                if idx.index_fin is None:
                    continue

                relais = idx.relais_ilot.relais

                prix = (
                    PrixCarburant.objects
                    .filter(
                        tenant=relais.tenant,
                        station=relais.station,
                        produit=idx.index_pompe.produit,
                        actif=True,
                    )
                    .values_list(
                        "prix_unitaire",
                        flat=True,
                    )
                    .first()
                )

                if prix is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Aucun prix trouvé "
                            f"pour RelaisIndex #{idx.id}"
                        )
                    )
                    erreurs += 1
                    continue

                volume = (
                    idx.index_fin -
                    idx.index_debut
                )

                idx.prix_unitaire = prix

                idx.montant_theorique = (
                    volume * prix
                )

                idx.save(
                    update_fields=[
                        "prix_unitaire",
                        "montant_theorique",
                    ]
                )

                total += 1

            except Exception as e:

                erreurs += 1

                self.stdout.write(
                    self.style.ERROR(
                        f"Erreur index {idx.id}: {e}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{total} index recalculés "
                f"({erreurs} erreurs)"
            )
        )