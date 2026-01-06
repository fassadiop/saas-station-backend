def test_transferer_applique_stock(api_client, depotage_confirme, cuve):
    stock_initial = cuve.stock_actuel

    resp = api_client.post(
        f"/api/v1/station/depotages/{depotage_confirme.id}/transferer/"
    )

    assert resp.status_code == 200

    cuve.refresh_from_db()
    depotage_confirme.refresh_from_db()

    assert cuve.stock_actuel == stock_initial + depotage_confirme.quantite_acceptee
    assert depotage_confirme.stock_applique is True
    assert depotage_confirme.statut == "TRANSFERE"


def test_transferer_idempotent(api_client, depotage_transfere):
    resp = api_client.post(
        f"/api/v1/station/depotages/{depotage_transfere.id}/transferer/"
    )
    assert resp.status_code == 400
