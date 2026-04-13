import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Crea la tabla eventos_eventosanitario (CU-003)."""

    initial = True

    dependencies = [
        ('animals', '0003_remove_eventosanitario_pesaje'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EventoSanitario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(max_length=64)),
                ('fecha', models.DateField(default=django.utils.timezone.now)),
                ('responsable', models.CharField(max_length=64)),
                ('producto', models.CharField(max_length=128)),
                ('dosis', models.CharField(blank=True, max_length=32, null=True)),
                ('lote', models.CharField(blank=True, max_length=64, null=True)),
                ('via_aplicacion', models.CharField(blank=True, max_length=32, null=True)),
                ('notas', models.TextField(blank=True, null=True)),
                ('estado', models.CharField(
                    choices=[('CON', 'Confirmado'), ('ANU', 'Anulado')],
                    default='CON',
                    max_length=3,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('animal', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='eventos',
                    to='animals.animal',
                )),
                ('evento_original', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='correcciones',
                    to='eventos.eventosanitario',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-fecha', '-created_at'],
            },
        ),
    ]
