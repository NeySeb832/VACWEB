from django.db import migrations


PERMISOS = [
    ("reportes.read",   "Ver y generar reportes del sistema (CU-007)"),
    ("reportes.export", "Exportar reportes a CSV y PDF (CU-007)"),
]

ASIGNACIONES = {
    "Administrador": ["reportes.read", "reportes.export"],
    "Propietario":   ["reportes.read", "reportes.export"],
}


def aplicar(apps, schema_editor):
    Permission     = apps.get_model("authz", "Permission")
    Role           = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")

    perm_objs = {}
    for code, desc in PERMISOS:
        perm, _ = Permission.objects.get_or_create(code=code)
        if perm.description != desc:
            perm.description = desc
            perm.save(update_fields=["description"])
        perm_objs[code] = perm

    for role_name, codes in ASIGNACIONES.items():
        try:
            role = Role.objects.get(name=role_name)
        except Role.DoesNotExist:
            continue
        for code in codes:
            perm = perm_objs.get(code) or Permission.objects.get(code=code)
            RolePermission.objects.get_or_create(role=role, permission=perm)


def revertir(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Permission.objects.filter(code__in=["reportes.read", "reportes.export"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reportes", "0001_initial"),
        ("authz", "0003_add_missing_permissions"),
    ]

    operations = [
        migrations.RunPython(aplicar, revertir),
    ]
