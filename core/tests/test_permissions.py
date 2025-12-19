import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from core.models import Tenant, Utilisateur

@pytest.fixture
def client():
    return APIClient()

@pytest.fixture
def superuser(db):
    return Utilisateur.objects.create_superuser(
        username="super",
        email="super@test.com",
        password="pass1234",
        role="SuperAdmin"
    )

@pytest.fixture
def tenant_admin(db):
    t = Tenant.objects.create(nom="FENAGIE", type_structure="GIE")
    u = Utilisateur.objects.create_user(
        username="admin1",
        email="admin1@test.com",
        password="pass1234",
        role="AdminTenant",
        tenant=t
    )
    return u

@pytest.fixture
def another_tenant_admin(db):
    t = Tenant.objects.create(nom="CNPS", type_structure="Collectif")
    u = Utilisateur.objects.create_user(
        username="admin2",
        email="admin2@test.com",
        password="pass1234",
        role="AdminTenant",
        tenant=t
    )
    return u

def test_superuser_can_only_see_his_own_tenants(client, superuser):
    # créer deux tenants mais assigner created_by au superuser seulement pour un
    t1 = Tenant.objects.create(nom="TENANT_A", type_structure="GIE", created_by=superuser)
    t2 = Tenant.objects.create(nom="TENANT_B", type_structure="GIE")  # pas créé par superuser

    client.force_authenticate(user=superuser)
    url = "/api/v1/tenants/"
    resp = client.get(url)

    assert resp.status_code == 200
    returned_ids = {t["id"] for t in resp.data}
    assert str(t1.id) in returned_ids
    assert str(t2.id) in returned_ids

def test_admintenant_cannot_see_other_tenants(client, tenant_admin, another_tenant_admin):
    client.force_authenticate(user=tenant_admin)
    url = "/api/v1/tenants/"
    resp = client.get(url)

    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["nom"] == tenant_admin.tenant.nom

def test_admintenant_cannot_see_users_of_other_tenants(client, tenant_admin, another_tenant_admin):
    client.force_authenticate(user=tenant_admin)
    url = "/api/v1/utilisateurs/"
    resp = client.get(url)

    assert resp.status_code == 200
    for user in resp.data:
        assert user["tenant"] == str(tenant_admin.tenant.id)

def test_superuser_sees_only_users_of_his_tenants(client, superuser, tenant_admin, another_tenant_admin):
    # only admin1 tenant is created_by superuser
    tenant_admin.tenant.created_by = superuser
    tenant_admin.tenant.save()

    client.force_authenticate(user=superuser)
    resp = client.get("/api/v1/utilisateurs/")

    assert resp.status_code == 200
    returned_roles = {u["role"] for u in resp.data}
    assert "AdminTenant" in returned_roles
    # admin2 must NOT appear
    assert all(u["email"] != another_tenant_admin.email for u in resp.data)
