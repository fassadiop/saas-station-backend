from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("stations", "0027_dettestation_relais"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dettestation",
            name="relais",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dettes",
                to="stations.relaisequipe",
            ),
        ),
    ]