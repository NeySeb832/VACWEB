"""
CU-010: Crea el permiso auditoria.read y lo asigna a los roles administrador/propietario.
"""
from django.db import migrations


def add_permission(apps, schema_editor):
    Permission    = apps.get_model("authz", "Permission")
    Role          = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")

    perm, _ = Permission.objects.get_or_create(
        code="auditoria.read",
        defaults={"description": "Consultar la bitácora de auditoría (CU-010)"},
    )

    codigos_admin = ("administrador", "propietario", "administrador de la finca", "admin")
    nombres_admin = ("administrador", "propietario", "admin")
    roles_asignados = set()

    for code in codigos_admin:
        for role in Role.objects.filter(code__icontains=code):
            if role.pk not in roles_asignados:
                RolePermission.objects.get_or_create(role=role, permission=perm)
                roles_asignados.add(role.pk)

    for nombre in nombres_admin:
        for role in Role.objects.filter(name__icontains=nombre):
            if role.pk not in roles_asignados:
                RolePermission.objects.get_or_create(role=role, permission=perm)
                roles_asignados.add(role.pk)


def remove_permission(apps, schema_editor):
    Permission     = apps.get_model("authz", "Permission")
    RolePermission = apps.get_model("authz", "RolePermission")
    try:
        perm = Permission.objects.get(code="auditoria.read")
        RolePermission.objects.filter(permission=perm).delete()
        perm.delete()
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("auditoria", "0001_initial"),
        ("authz", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_permission, remove_permission),
    ]
