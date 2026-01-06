from stations.models import Station
from stations.models_depotage.cuve import Cuve


def test_station_creation_creates_cuves(db, tenant):
    station = Station.objects.create(
        tenant=tenant,
        nom="Station Test",
        adresse="Test",
    )

    assert station.cuves.filter(produit="ESSENCE").exists()
    assert station.cuves.filter(produit="GASOIL").exists()


def test_confirmer_fails_without_cuve(api_client, depotage):
    Cuve.objects.filter(
        station=depotage.station,
        produit=depotage.produit
    ).delete()

    response = api_client.post(
        f"/api/v1/station/depotages/{depotage.id}/confirmer/"
    )

    assert response.status_code == 400
