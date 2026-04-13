from django.db import migrations


def crear_permisos_pesajes(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Permission.objects.get_or_create(
        code="pesajes.read",
        defaults={"description": "Ver listado y detalle de pesajes"},
    )
    Permission.objects.get_or_create(
        code="pesajes.write",
        defaults={"description": "Registrar nuevos pesajes"},
    )


def eliminar_permisos_pesajes(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Permission.objects.filter(code__in=["pesajes.read", "pesajes.write"]).delete()


class Migration(migrations.Migration):
    """Crea los permisos RBAC para el módulo de pesajes (CU-004)."""

    dependencies = [
        ("pesajes", "0001_initial"),
        ("authz", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_permisos_pesajes, eliminar_permisos_pesajes),
    ]
