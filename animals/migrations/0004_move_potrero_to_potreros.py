import django.db.models.deletion
from django.db import migrations, models


def limpiar_referencias_potrero(apps, schema_editor):
    """Nulifica las FK de Animal.potrero y borra Movimientos antes de eliminar el
    modelo animals.Potrero. Necesario para poder hacer AlterField y DeleteModel."""
    Animal = apps.get_model("animals", "Animal")
    Animal.objects.all().update(potrero=None)

    Movimiento = apps.get_model("animals", "Movimiento")
    Movimiento.objects.all().delete()


class Migration(migrations.Migration):
    """Migra las FK de animals.Potrero → potreros.Potrero y elimina el modelo antiguo.

    Pasos:
      1. Limpia FK references (data migration).
      2. Altera Animal.potrero para apuntar a potreros.Potrero.
      3. Altera Movimiento.desde / Movimiento.hacia para apuntar a potreros.Potrero.
      4. Elimina el modelo animals.Potrero (tabla animals_potrero).
    """

    dependencies = [
        ("animals",  "0003_remove_eventosanitario_pesaje"),
        ("potreros", "0001_initial"),
    ]

    operations = [
        # Paso 1: limpiar datos para evitar FK violations al cambiar targets
        migrations.RunPython(limpiar_referencias_potrero, migrations.RunPython.noop),

        # Paso 2: redirigir Animal.potrero → potreros.Potrero
        migrations.AlterField(
            model_name="animal",
            name="potrero",
            field=models.ForeignKey(
                "potreros.Potrero",
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="animales",
            ),
        ),

        # Paso 3: redirigir Movimiento.desde → potreros.Potrero
        migrations.AlterField(
            model_name="movimiento",
            name="desde",
            field=models.ForeignKey(
                "potreros.Potrero",
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
            ),
        ),

        # Paso 4: redirigir Movimiento.hacia → potreros.Potrero
        migrations.AlterField(
            model_name="movimiento",
            name="hacia",
            field=models.ForeignKey(
                "potreros.Potrero",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
            ),
        ),

        # Paso 5: eliminar el modelo antiguo (borra tabla animals_potrero)
        migrations.DeleteModel(name="Potrero"),
    ]
