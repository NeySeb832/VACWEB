from django.db import migrations


def crear_permisos_transacciones(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Role        = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")

    perm_read, _   = Permission.objects.get_or_create(
        code="transacciones.read",
        defaults={"description": "Ver listado, detalle e historial de transacciones comerciales"},
    )
    perm_write, _  = Permission.objects.get_or_create(
        code="transacciones.write",
        defaults={"description": "Registrar compras, ventas y sacrificios"},
    )
    perm_anular, _ = Permission.objects.get_or_create(
        code="transacciones.anular",
        defaults={"description": "Anular transacciones confirmadas (solo Administrador)"},
    )

    # Asignar a roles existentes por nombre (con tolerancia si no existen todavía)
    ASIGNACIONES_POR_NOMBRE = {
        "Administrador": [perm_read, perm_write, perm_anular],
        "Propietario":   [perm_read, perm_write],
        # Operario: sin permisos de transacciones
    }
    for role_name, perms in ASIGNACIONES_POR_NOMBRE.items():
        try:
            role = Role.objects.get(name=role_name)
        except Role.DoesNotExist:
            continue
        for perm in perms:
            RolePermission.objects.get_or_create(role=role, permission=perm)


def eliminar_permisos_transacciones(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Permission.objects.filter(
        code__in=["transacciones.read", "transacciones.write", "transacciones.anular"]
    ).delete()


class Migration(migrations.Migration):
    """Crea los permisos RBAC para el módulo de transacciones (CU-006)."""

    dependencies = [
        ("transacciones", "0001_initial"),
        ("authz",         "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_permisos_transacciones, eliminar_permisos_transacciones),
    ]
