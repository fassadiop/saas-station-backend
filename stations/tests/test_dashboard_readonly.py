from django.test import TestCase
from rest_framework.test import APIClient

from stations.models import Station, MouvementStock
from core.models import Tenant, User


class DashboardReadOnlyTestCase(TestCase):

    def setUp(self):
        self.client = APIClient()

        self.tenant = Tenant.objects.create(nom="Tenant Test")
        self.station = Station.objects.create(
            tenant=self.tenant,
            nom="Station A"
        )

        self.user = User.objects.create_user(
            username="chef",
            password="test",
            tenant=self.tenant,
            station=self.station,
            role="CHEF_STATION"
        )

        self.client.force_authenticate(self.user)

    def test_dashboard_ne_cree_aucun_mouvement(self):
        initial_count = MouvementStock.objects.count()

        response = self.client.get(
            "/api/station/dashboard/operational/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            MouvementStock.objects.count(),
            initial_count
        )
