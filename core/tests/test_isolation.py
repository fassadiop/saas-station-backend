import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from core.models import Tenant, Utilisateur, Membre, Projet, Transaction, Cotisation

@pytest.fixture
def api():
    return APIClient()

@pytest.fixture
def tenantA(db):
    return Tenant.objects.create(nom="TA", type_structure="GIE")

@pytest.fixture
def tenantB(db):
    return Tenant.objects.create(nom="TB", type_structure="GIE")

@pytest.fixture
def adminA(db, tenantA):
    return Utilisateur.objects.create_user(
        username="adminA",
        password="pass1234",
        role="AdminTenant",
        tenant=tenantA
    )

@pytest.fixture
def adminB(db, tenantB):
    return Utilisateur.objects.create_user(
        username="adminB",
        password="pass1234",
        role="AdminTenant",
        tenant=tenantB
    )


###############################
# A1 — Isolation des Membres
###############################
def test_member_isolation(api, adminA, adminB, tenantA, tenantB):
    mA = Membre.objects.create(nom_membre="M1", tenant=tenantA)
    mB = Membre.objects.create(nom_membre="M2", tenant=tenantB)

    api.force_authenticate(user=adminA)
    respA = api.get("/api/v1/membres/")
    idsA = {m["id"] for m in respA.data}
    assert mA.id in idsA
    assert mB.id not in idsA

    api.force_authenticate(user=adminB)
    respB = api.get("/api/v1/membres/")
    idsB = {m["id"] for m in respB.data}
    assert mB.id in idsB
    assert mA.id not in idsB


###############################
# A2 — Isolation des Projets
###############################
def test_project_isolation(api, adminA, adminB, tenantA, tenantB):
    pA = Projet.objects.create(nom="PA", tenant=tenantA)
    pB = Projet.objects.create(nom="PB", tenant=tenantB)

    api.force_authenticate(user=adminA)
    respA = api.get("/api/v1/projets/")
    idsA = {p["id"] for p in respA.data}
    assert pA.id in idsA
    assert pB.id not in idsA

    api.force_authenticate(user=adminB)
    respB = api.get("/api/v1/projets/")
    idsB = {p["id"] for p in respB.data}
    assert pB.id in idsB
    assert pA.id not in idsB


#################################
# A3 — Isolation des Transactions
#################################
def test_transaction_isolation(api, adminA, adminB, tenantA, tenantB):
    tA = Transaction.objects.create(montant=1000, type="Recette", categorie="Test", tenant=tenantA)
    tB = Transaction.objects.create(montant=2000, type="DEPENSE", categorie="Test", tenant=tenantB)

    api.force_authenticate(user=adminA)
    respA = api.get("/api/v1/transactions/")
    idsA = {t["id"] for t in respA.data}
    assert tA.id in idsA
    assert tB.id not in idsA

    api.force_authenticate(user=adminB)
    respB = api.get("/api/v1/transactions/")
    idsB = {t["id"] for t in respB.data}
    assert tB.id in idsB
    assert tA.id not in idsB


###############################
# A4 — Isolation des Cotisations
###############################
def test_cotisation_isolation(api, adminA, adminB, tenantA, tenantB):
    mA = Membre.objects.create(nom_membre="M1", tenant=tenantA)
    cA = Cotisation.objects.create(montant=500, tenant=tenantA, membre=mA, periode="2025")
    mB = Membre.objects.create(nom_membre="M2", tenant=tenantB)
    cB = Cotisation.objects.create(montant=600, tenant=tenantB, membre=mB, periode="2025")

    api.force_authenticate(user=adminA)
    respA = api.get("/api/v1/cotisations/")
    idsA = {c["id"] for c in respA.data}
    assert cA.id in idsA
    assert cB.id not in idsA

    api.force_authenticate(user=adminB)
    respB = api.get("/api/v1/cotisations/")
    idsB = {c["id"] for c in respB.data}
    assert cB.id in idsB
    assert cA.id not in idsB


###########################################
# A5 — Interdiction de cross-tenant
###########################################
def test_admin_cannot_create_cross_tenant_member(api, adminA, tenantB):
    payload = {"nom": "Cross", "tenant": tenantB.id}

    api.force_authenticate(user=adminA)
    resp = api.post("/api/v1/membres/", payload)

    assert resp.status_code in (400, 403)


###########################################
# A6 — Permissions des rôles
###########################################
@pytest.fixture
def collector(db, tenantA):
    return Utilisateur.objects.create_user(
        username="col",
        password="pass1234",
        role="Collecteur",
        tenant=tenantA
    )

@pytest.fixture
def treasurer(db, tenantA):
    return Utilisateur.objects.create_user(
        username="tre",
        password="pass1234",
        role="Tresorier",
        tenant=tenantA
    )

def test_collector_cannot_delete_transaction(api, collector, tenantA):
    tr = Transaction.objects.create(montant=1000, type="RECETTE", tenant=tenantA)

    api.force_authenticate(user=collector)
    resp = api.delete(f"/api/v1/transactions/{tr.id}/")
    assert resp.status_code == 403

def test_treasurer_can_create_transaction(api, treasurer):
    payload = {
        "montant": 500,
        "type": "Recette",
        "categorie": "Test",
        "date": "2025-01-01",
        "mode_paiement": "ESPECES",
        "reference": ""
    }

    api.force_authenticate(user=treasurer)
    resp = api.post("/api/v1/transactions/", payload)
    print("DEBUG:", resp.status_code, resp.data)

    assert resp.status_code in (200, 201)
