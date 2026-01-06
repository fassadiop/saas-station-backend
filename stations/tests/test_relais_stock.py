from django.test import TestCase

from stations.models import Station, MouvementStock, RelaisEquipe
from stations.services.stock import appliquer_sortie_relais
from core.models import Tenant

CARBURANT_GASOIL = "GASOIL"


class RelaisEquipeStockTestCase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(nom="Tenant Test")
        self.station = Station.objects.create(
            tenant=self.tenant,
            nom="Station A"
        )

        self.relais = RelaisEquipe.objects.create(
            tenant=self.tenant,
            station=self.station,
            carburant=CARBURANT_GASOIL,
            volume_vendu=1500,
            status="VALIDE",
            stock_applique=False
        )

    def test_aucun_mouvement_avant_transfere(self):
        appliquer_sortie_relais(self.relais)
        self.assertEqual(MouvementStock.objects.count(), 0)

    def test_mouvement_cree_au_transfere(self):
        self.relais.status = "TRANSFERE"
        self.relais.save(update_fields=["status"])

        appliquer_sortie_relais(self.relais)

        self.assertEqual(MouvementStock.objects.count(), 1)

        mouvement = MouvementStock.objects.first()
        self.assertEqual(mouvement.quantite, -1500)
        self.assertEqual(mouvement.source_type, "RELAIS_EQUIPE")
        self.assertEqual(mouvement.source_id, self.relais.id)

    def test_idempotence_critique(self):
        self.relais.status = "TRANSFERE"
        self.relais.save(update_fields=["status"])

        appliquer_sortie_relais(self.relais)
        appliquer_sortie_relais(self.relais)

        self.assertEqual(MouvementStock.objects.count(), 1)

        self.relais.refresh_from_db()
        self.assertTrue(self.relais.stock_applique)
