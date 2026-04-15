import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Crea la tabla potreros_potrero con todos sus campos (CU-005)."""

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Potrero",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre_codigo", models.CharField(max_length=100, unique=True, verbose_name="Nombre o código")),
                ("area_ha", models.DecimalField(decimal_places=2, max_digits=8, verbose_name="Área (ha)")),
                ("capacidad_maxima", models.IntegerField(verbose_name="Capacidad máxima (animales)")),
                (
                    "tipo_uso",
                    models.CharField(
                        choices=[
                            ("CEBA",       "Ceba"),
                            ("LEVANTE",    "Levante"),
                            ("MATERNIDAD", "Maternidad"),
                            ("CUARENTENA", "Cuarentena"),
                            ("ROTACION",   "Rotación"),
                        ],
                        max_length=20,
                        verbose_name="Tipo de uso",
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[("ACTIVO", "Activo"), ("INACTIVO", "Inactivo")],
                        default="ACTIVO",
                        max_length=10,
                        verbose_name="Estado",
                    ),
                ),
                ("observaciones", models.TextField(blank=True, null=True, verbose_name="Observaciones")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Última modificación")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Potrero",
                "verbose_name_plural": "Potreros",
                "ordering": ["nombre_codigo"],
            },
        ),
        migrations.AddConstraint(
            model_name="potrero",
            constraint=models.UniqueConstraint(
                fields=["nombre_codigo"],
                name="unique_nombre_codigo_potrero",
            ),
        ),
    ]
