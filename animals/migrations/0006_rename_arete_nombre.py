from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("animals", "0005_animal_new_fields"),
    ]

    operations = [
        migrations.RenameField(
            model_name="animal",
            old_name="arete",
            new_name="nombre",
        ),
    ]
