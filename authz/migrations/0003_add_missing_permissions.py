from django.db import migrations


# ---------------------------------------------------------------------------
# Descripciones correctas para todos los permisos del módulo authz
# ---------------------------------------------------------------------------
PERMISOS = [
    ("users.read",   "Ver el listado y detalle de usuarios del sistema"),
    ("users.write",  "Crear y editar usuarios (nombre, email, rol, estado)"),
    ("users.delete", "Dar de baja lógica a usuarios (nunca eliminación física)"),
    ("roles.read",   "Ver el listado de roles y sus permisos asignados"),
    ("roles.write",  "Crear y editar roles y su asignación de permisos"),
]

# Roles que reciben cada permiso
ASIGNACIONES = {
    "Administrador": [
        "users.read", "users.write", "users.delete",
        "roles.read", "roles.write",
    ],
}


def aplicar(apps, schema_editor):
    Permission     = apps.get_model("authz", "Permission")
    Role           = apps.get_model("authz", "Role")
    RolePermission = apps.get_model("authz", "RolePermission")

    # 1. Crear o actualizar cada permiso con descripción correcta
    perm_objs = {}
    for code, desc in PERMISOS:
        perm, created = Permission.objects.get_or_create(code=code)
        if perm.description != desc:
            perm.description = desc
            perm.save(update_fields=["description"])
        perm_objs[code] = perm

    # 2. Asignar permisos a roles (idempotente con get_or_create)
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
    Permission.objects.filter(code="users.delete").delete()


class Migration(migrations.Migration):
    """Añade users.delete y asigna users.*/roles.* al rol Administrador (CU-001)."""

    dependencies = [
        ("authz", "0002_userprofile"),
    ]

    operations = [
        migrations.RunPython(aplicar, revertir),
    ]
