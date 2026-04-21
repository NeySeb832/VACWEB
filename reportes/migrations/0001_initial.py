from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LogReporte",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_reporte", models.CharField(choices=[("inventario", "Inventario de Animales"), ("historial", "Historial por Animal"), ("sanitario", "Calendario Sanitario"), ("ventas", "Reporte de Ventas")], max_length=20)),
                ("filtros_aplicados", models.JSONField(blank=True, default=dict)),
                ("formato_exportacion", models.CharField(blank=True, max_length=10)),
                ("fecha_ejecucion", models.DateTimeField(auto_now_add=True)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Log de reporte",
                "verbose_name_plural": "Logs de reportes",
                "ordering": ["-fecha_ejecucion"],
            },
        ),
    ]
