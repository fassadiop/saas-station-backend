from django.db import migrations


def delete_orphan_station_staff(apps, schema_editor):
    Utilisateur = apps.get_model("accounts", "Utilisateur")

    STATION_ROLES = [
        "GERANT",
        "SUPERVISEUR",
        "POMPISTE",
        "CAISSIER",
        "PERSONNEL_ENTRETIEN",
        "SECURITE",
    ]

    Utilisateur.objects.filter(
        role__in=STATION_ROLES,
        station__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_normalize_user_roles"),
    ]

    operations = [
        migrations.RunPython(delete_orphan_station_staff),
    ]
