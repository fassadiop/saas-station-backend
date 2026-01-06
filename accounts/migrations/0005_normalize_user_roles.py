from django.db import migrations


def normalize_user_roles(apps, schema_editor):
    Utilisateur = apps.get_model("accounts", "Utilisateur")

    ROLE_MAP = {
        # Admin / système
        "SuperAdmin": "SUPERADMIN",
        "AdminTenantStation": "ADMIN_TENANT_STATION",
        "AdminTenantFinance": "ADMIN_TENANT_FINANCE",

        # Station
        "Gerant": "GERANT",          # chef_yoff
        "GERANT": "GERANT",
        "SUPERVISEUR": "SUPERVISEUR",
        "POMPISTE": "POMPISTE",
        "CAISSIER": "CAISSIER",
        "PERSONNEL_ENTRETIEN": "PERSONNEL_ENTRETIEN",
        "SECURITE": "SECURITE",

        # Finance / terrain
        "Tresorier": "TRESORIER",
        "COLLECTEUR": "COLLECTEUR",
    }

    for old_role, new_role in ROLE_MAP.items():
        Utilisateur.objects.filter(role=old_role).update(role=new_role)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_alter_utilisateur_role"),  # ⚠️ remplace par la VRAIE dernière migration
    ]

    operations = [
        migrations.RunPython(normalize_user_roles),
    ]
