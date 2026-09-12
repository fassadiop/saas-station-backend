from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stations", "0017_create_relais_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="relaisaudit",
            name="date_action",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]