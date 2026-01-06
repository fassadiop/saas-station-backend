from django.test import TestCase
from django.utils import timezone

from stations.models import Station, MouvementStock
from stations.services.stock import get_stock_actuel
from core.models import Tenant

CARBURANT_GASOIL = "GASOIL"


class StockServiceTestCase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(nom="Tenant Test")
        self.station = Station.objects.create(
            tenant=self.tenant,
            nom="Station A"
        )

    def test_stock_initial_est_zero(self):
        stock = get_stock_actuel(self.station, CARBURANT_GASOIL)
        self.assertEqual(stock, 0)

    def test_stock_apres_depotage(self):
        MouvementStock.objects.create(
            tenant=self.tenant,
            station=self.station,
            carburant=CARBURANT_GASOIL,
            quantite=10000,
            source_type="DEPOTAGE"
        )

        stock = get_stock_actuel(self.station, CARBURANT_GASOIL)
        self.assertEqual(stock, 10000)

    def test_stock_entrees_et_sorties(self):
        MouvementStock.objects.bulk_create([
            MouvementStock(
                tenant=self.tenant,
                station=self.station,
                carburant=CARBURANT_GASOIL,
                quantite=10000,
                source_type="DEPOTAGE"
            ),
            MouvementStock(
                tenant=self.tenant,
                station=self.station,
                carburant=CARBURANT_GASOIL,
                quantite=-2000,
                source_type="RELAIS_EQUIPE"
            ),
            MouvementStock(
                tenant=self.tenant,
                station=self.station,
                carburant=CARBURANT_GASOIL,
                quantite=-500,
                source_type="INCIDENT"
            ),
        ])

        stock = get_stock_actuel(self.station, CARBURANT_GASOIL)
        self.assertEqual(stock, 7500)
