from django.db import migrations


class Migration(migrations.Migration):
    """Elimina los modelos EventoSanitario y Pesaje de la app animals.
    Estos modelos se reemplazan por eventos.EventoSanitario (CU-003).
    """

    dependencies = [
        ('animals', '0002_alter_animal_foto'),
    ]

    operations = [
        migrations.DeleteModel(name='EventoSanitario'),
        migrations.DeleteModel(name='Pesaje'),
    ]
