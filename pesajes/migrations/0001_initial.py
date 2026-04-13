# Generated migration for pesajes app (CU-004)
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("animals", "0003_remove_eventosanitario_pesaje"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Pesaje",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("fecha", models.DateField(default=django.utils.timezone.now)),
                ("peso_kg", models.DecimalField(decimal_places=2, max_digits=7)),
                ("observaciones", models.TextField(blank=True, null=True)),
                (
                    "foto_bascula",
                    models.ImageField(
                        blank=True, null=True, upload_to="pesajes/fotos/"
                    ),
                ),
                ("responsable", models.CharField(blank=True, max_length=64, null=True)),
                (
                    "variacion_kg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Diferencia respecto al pesaje anterior en kg. Positivo=ganancia, negativo=pérdida.",
                        max_digits=7,
                        null=True,
                    ),
                ),
                (
                    "promedio_diario_g",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        help_text="Promedio de ganancia/pérdida diaria en g/día respecto al pesaje anterior.",
                        max_digits=8,
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "animal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pesajes",
                        to="animals.animal",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha", "-created_at"],
            },
        ),
    ]
