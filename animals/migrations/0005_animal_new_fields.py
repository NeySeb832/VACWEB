from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('animals', '0004_move_potrero_to_potreros'),
    ]

    operations = [
        migrations.AddField(
            model_name='animal',
            name='fecha_ingreso',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha de ingreso'),
        ),
        migrations.AddField(
            model_name='animal',
            name='peso_entrada',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=7, null=True,
                verbose_name='Peso de entrada (kg)'
            ),
        ),
        migrations.AddField(
            model_name='animal',
            name='procedencia',
            field=models.CharField(
                blank=True, max_length=120, null=True,
                verbose_name='Procedencia / Finca de origen'
            ),
        ),
    ]
