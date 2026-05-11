from django.db import migrations


PERMISOS = [
    ("alertas.view_alertas",      "Ver listado y detalle de alertas del sistema"),
    ("alertas.atender_alertas",   "Marcar alertas como atendidas y agregar observaciones"),
    ("alertas.configurar_alertas","Configurar reglas y umbrales de generación de alertas"),
]


def crear_permisos_alertas(apps, schema_editor):
    Permission     = apps.get_model("authz", "Permission")
    Role           = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")

    perm_objs = []
    for code, desc in PERMISOS:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"description": desc},
        )
        perm_objs.append(perm)

    for role in Role.objects.all():
        for perm in perm_objs:
            RolePermission.objects.get_or_create(role=role, permission=perm)


def eliminar_permisos_alertas(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Permission.objects.filter(
        code__in=[code for code, _ in PERMISOS]
    ).delete()


class Migration(migrations.Migration):
    """Crea los permisos RBAC del módulo de alertas y los asigna a todos los roles."""

    dependencies = [
        ("alertas", "0001_initial"),
        ("authz",   "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_permisos_alertas, eliminar_permisos_alertas),
    ]
