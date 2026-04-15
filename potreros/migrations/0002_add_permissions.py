from django.db import migrations


def crear_permisos_potreros(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Permission.objects.get_or_create(
        code="potreros.read",
        defaults={"description": "Ver listado y detalle de potreros/lotes"},
    )
    Permission.objects.get_or_create(
        code="potreros.write",
        defaults={"description": "Crear, editar y desactivar potreros/lotes"},
    )


def eliminar_permisos_potreros(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Permission.objects.filter(code__in=["potreros.read", "potreros.write"]).delete()


class Migration(migrations.Migration):
    """Crea los permisos RBAC para el módulo de potreros (CU-005)."""

    dependencies = [
        ("potreros", "0001_initial"),
        ("authz",    "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_permisos_potreros, eliminar_permisos_potreros),
    ]
