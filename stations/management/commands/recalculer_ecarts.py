from decimal import Decimal

from django.core.management.base import BaseCommand

from stations.models import (
    RelaisIlot,
    RelaisEcart,
)


class Command(BaseCommand):

    help = "Recalcul des écarts historiques"

    def handle(self, *args, **kwargs):

        total = 0

        relais_ilots = (
            RelaisIlot.objects
            .select_related(
                "tenant",
                "relais",
                "responsable",
            )
        )

        for ri in relais_ilots:

            ecart = (
                ri.total_encaisse -
                ri.total_theorique
            )

            if ecart == Decimal("0"):
                continue

            type_ecart = (
                RelaisEcart.TypeEcart.EXCEDENT
                if ecart > 0
                else RelaisEcart.TypeEcart.MANQUE
            )

            RelaisEcart.objects.update_or_create(
                relais_ilot=ri,
                defaults={
                    "tenant": ri.tenant,
                    "relais": ri.relais,
                    "responsable": ri.responsable,
                    "type_ecart": type_ecart,
                    "montant_theorique": ri.total_theorique,
                    "montant_encaisse": ri.total_encaisse,
                    "montant": abs(ecart),
                    "date_relais": ri.relais.fin_relais.date(),
                    "created_by": (
                        ri.valide_par
                        or ri.responsable
                    ),
                }
            )

            total += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{total} écarts recalculés."
            )
        )