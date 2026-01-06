from django.db import migrations


ROLE_MAPPING = {
    # Super
    "SuperAdmin": "SUPERADMIN",

    # Tenant
    "AdminTenantStation": "ADMIN_TENANT_STATION",
    "AdminTenantFinance": "ADMIN_TENANT_FINANCE",

    # Station
    "Gerant": "GERANT",
    "SUPERVISEUR": "SUPERVISEUR",
    "POMPISTE": "POMPISTE",
    "CAISSIER": "CAISSIER",
    "PERSONNEL_ENTRETIEN": "PERSONNEL_ENTRETIEN",
    "SECURITE": "SECURITE",

    # Finance / autres
    "Tresorier": "TRESORIER",
    "COLLECTEUR": "COLLECTEUR",
}


def normalize_roles(apps, schema_editor):
    Utilisateur = apps.get_model("accounts", "Utilisateur")

    for old, new in ROLE_MAPPING.items():
        Utilisateur.objects.filter(role=old).update(role=new)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_alter_utilisateur_role"),  # ⚠️ adapte si besoin
    ]

    operations = [
        migrations.RunPython(normalize_roles),
    ]
