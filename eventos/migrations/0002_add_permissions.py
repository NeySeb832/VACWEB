from django.db import migrations


def crear_permisos_eventos(apps, schema_editor):
    Permission = apps.get_model('authz', 'Permission')
    Permission.objects.get_or_create(
        code='eventos.read',
        defaults={'description': 'Ver listado y detalle de eventos sanitarios'},
    )
    Permission.objects.get_or_create(
        code='eventos.write',
        defaults={'description': 'Crear, corregir y anular eventos sanitarios'},
    )


def eliminar_permisos_eventos(apps, schema_editor):
    Permission = apps.get_model('authz', 'Permission')
    Permission.objects.filter(code__in=['eventos.read', 'eventos.write']).delete()


class Migration(migrations.Migration):
    """Crea los permisos RBAC para el módulo de eventos (CU-003)."""

    dependencies = [
        ('eventos', '0001_initial'),
        ('authz', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_permisos_eventos, eliminar_permisos_eventos),
    ]
