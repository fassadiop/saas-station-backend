from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from stations.models import Station, MouvementStock
from stations.services.autonomie import (
    get_consommation_moyenne,
    calcul_autonomie_station
)
from core.models import Tenant

CARBURANT_GASOIL = "GASOIL"


class AutonomieServiceTestCase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(nom="Tenant Test")
        self.station = Station.objects.create(
            tenant=self.tenant,
            nom="Station A"
        )

    def _create_sortie(self, jours_avant, quantite):
        MouvementStock.objects.create(
            tenant=self.tenant,
            station=self.station,
            carburant=CARBURANT_GASOIL,
            quantite=-quantite,
            source_type="RELAIS_EQUIPE",
            created_at=timezone.now() - timedelta(days=jours_avant)
        )

    def test_consommation_moyenne_7_jours(self):
        for i in range(7):
            self._create_sortie(i, 1000)

        conso = get_consommation_moyenne(
            self.station, CARBURANT_GASOIL, days=7
        )

        self.assertEqual(conso, 1000)

    def test_autonomie_nominale(self):
        MouvementStock.objects.create(
            tenant=self.tenant,
            station=self.station,
            carburant=CARBURANT_GASOIL,
            quantite=10000,
            source_type="DEPOTAGE"
        )

        for i in range(5):
            self._create_sortie(i, 2000)

        autonomie = calcul_autonomie_station(
            self.station, CARBURANT_GASOIL, window_days=5
        )

        self.assertEqual(autonomie, 5)

    def test_autonomie_conso_nulle(self):
        autonomie = calcul_autonomie_station(
            self.station, CARBURANT_GASOIL
        )
        self.assertIsNone(autonomie)
