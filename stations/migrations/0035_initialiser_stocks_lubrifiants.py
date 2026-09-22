from django.db import migrations


def creer_stocks_lubrifiants(apps, schema_editor):
    Lubrifiants = apps.get_model("stations", "Lubrifiants")
    Station = apps.get_model("stations", "Station")
    StockLubrifiant = apps.get_model("stations", "StockLubrifiant")

    stations = Station.objects.filter(active=True)
    lubrifiants = Lubrifiants.objects.all()

    for station in stations.iterator():

        stocks = [
            StockLubrifiant(
                tenant_id=station.tenant_id,
                station_id=station.id,
                lubrifiant_id=lubrifiant.id,
                stock_actuel=0,
            )
            for lubrifiant in lubrifiants
        ]

        StockLubrifiant.objects.bulk_create(
            stocks,
            ignore_conflicts=True,
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("stations", "0034_ventelubrifiant"),
    ]

    operations = [
        migrations.RunPython(
            creer_stocks_lubrifiants,
            migrations.RunPython.noop,
        ),
    ]