import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Vincula Alerta con EventoSanitario para propagar el estado REALIZADO al atender."""

    dependencies = [
        ("alertas", "0002_add_permissions"),
        ("eventos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="alerta",
            name="evento_sanitario",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="alertas",
                to="eventos.eventosanitario",
            ),
        ),
    ]
