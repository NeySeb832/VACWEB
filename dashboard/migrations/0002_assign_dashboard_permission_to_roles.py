from django.db import migrations


def assign_permission(apps, schema_editor):
    """
    Asigna dashboard.read a todos los roles que contengan palabras clave
    de administración, sin importar el código exacto usado en cada instalación.
    """
    Permission = apps.get_model("authz", "Permission")
    Role = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")

    try:
        perm = Permission.objects.get(code="dashboard.read")
    except Permission.DoesNotExist:
        return

    # Intentar por códigos conocidos (instalación limpia)
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
    Permission = apps.get_model("authz", "Permission")
    RolePermission = apps.get_model("authz", "RolePermission")
    try:
        perm = Permission.objects.get(code="dashboard.read")
        RolePermission.objects.filter(permission=perm).delete()
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0001_add_permissions"),
    ]

    operations = [
        migrations.RunPython(assign_permission, remove_permission),
    ]
