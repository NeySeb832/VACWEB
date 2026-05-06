from django.db import migrations


def add_permissions(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    Role = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")

    perm, _ = Permission.objects.get_or_create(
        code="dashboard.read",
        defaults={"description": "Ver panel principal (Dashboard)"},
    )

    for role_code in ("administrador", "propietario"):
        try:
            role = Role.objects.get(code=role_code)
            RolePermission.objects.get_or_create(role=role, permission=perm)
        except Exception:
            pass


def remove_permissions(apps, schema_editor):
    Permission = apps.get_model("authz", "Permission")
    try:
        Permission.objects.filter(code="dashboard.read").delete()
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("authz", "0003_add_missing_permissions"),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
