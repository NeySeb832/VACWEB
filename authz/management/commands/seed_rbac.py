"""
Management command: python manage.py seed_rbac

Crea los Permisos, Roles y la asignacion Rol -> Permisos del sistema VACWEB.
Idempotente: se puede ejecutar varias veces sin duplicar nada.

No toca usuarios, ni datos de negocio. Solo modifica las tres tablas del modulo
authz: Permission, Role y RolePermission.

Tipico uso:
  - Despues de un deploy nuevo en Render para inicializar el RBAC.
  - Cuando se agrega un permiso o rol nuevo y se quiere propagar a produccion.
  - En desarrollo local para tener el RBAC listo sin correr todo seed_demo.

Salida: imprime cuantos permisos, roles y asignaciones creo (o que ya existian).
"""

from django.core.management.base import BaseCommand
from django.db import transaction


# ─── Catálogo de permisos ─────────────────────────────────────────────────────
# Convencion: "<modulo>.<accion>". Cada tupla = (codigo, descripcion).
PERMISOS = [
    # CU-001 — Gestión de usuarios y roles
    ("users.read",                 "Ver el listado y detalle de usuarios"),
    ("users.write",                "Crear y editar usuarios"),
    ("users.delete",               "Dar de baja usuarios (baja lógica)"),
    ("roles.read",                 "Ver roles y sus permisos"),
    ("roles.write",                "Crear y editar roles y asignaciones"),

    # CU-002 — Animales
    ("animals.read",               "Ver el listado y detalle de animales"),
    ("animals.write",              "Crear, editar y dar de baja animales"),

    # CU-003 — Eventos sanitarios
    ("eventos.read",               "Ver el historial sanitario"),
    ("eventos.write",              "Registrar, editar y cancelar eventos sanitarios"),

    # CU-004 — Pesajes
    ("pesajes.read",               "Ver el historial de pesajes"),
    ("pesajes.write",              "Registrar pesajes (los registros son inmutables)"),

    # CU-005 — Potreros
    ("potreros.read",              "Ver los potreros y su ocupacion"),
    ("potreros.write",             "Crear, editar y dar de baja potreros"),

    # CU-006 — Transacciones comerciales
    ("transacciones.read",         "Ver el historial de transacciones"),
    ("transacciones.write",        "Registrar compras, ventas y sacrificios"),
    ("transacciones.anular",       "Anular transacciones con motivo"),

    # CU-007 — Reportes y analitica
    ("reportes.read",              "Generar reportes"),
    ("reportes.export",            "Exportar reportes a CSV / PDF"),

    # CU-008 — Alertas
    ("alertas.view_alertas",       "Ver alertas pendientes y atendidas"),
    ("alertas.atender_alertas",    "Atender alertas con observacion"),
    ("alertas.configurar_alertas", "Configurar reglas de alertas"),

    # CU-009 — Dashboard
    ("dashboard.read",             "Acceder al panel principal"),

    # CU-010 — Auditoria
    ("auditoria.read",             "Consultar la bitacora de auditoria"),
]


# ─── Catalogo de roles ────────────────────────────────────────────────────────
ROLES = [
    # (name, code, descripcion)
    ("Administrador", "administrador", "Acceso total al sistema"),
    ("Propietario",   "propietario",   "Dueno de la finca: inventario, comercial y reportes"),
    ("Veterinario",   "veterinario",   "Profesional sanitario: eventos y alertas"),
    ("Operario",      "operario",      "Personal de campo: solo lectura + pesajes"),
    ("Auditor",       "auditor",       "Solo lectura de bitacora y alertas"),
]


# ─── Asignacion rol -> lista de permisos ──────────────────────────────────────
PERMISOS_POR_ROL = {
    "administrador": [
        # Acceso total: todos los permisos definidos arriba.
        c for c, _ in PERMISOS
    ],
    "propietario": [
        "animals.read", "animals.write",
        "potreros.read", "potreros.write",
        "eventos.read",
        "pesajes.read",
        "transacciones.read", "transacciones.write", "transacciones.anular",
        "reportes.read", "reportes.export",
        "alertas.view_alertas", "alertas.atender_alertas",
        "dashboard.read",
    ],
    "veterinario": [
        "animals.read",
        "eventos.read", "eventos.write",
        "pesajes.read",
        "alertas.view_alertas", "alertas.atender_alertas",
        "dashboard.read",
    ],
    "operario": [
        "animals.read",
        "potreros.read",
        "pesajes.read", "pesajes.write",
        "dashboard.read",
    ],
    "auditor": [
        "auditoria.read",
        "alertas.view_alertas",
        "dashboard.read",
    ],
}


class Command(BaseCommand):
    help = "Crea o actualiza permisos, roles y sus asignaciones. Idempotente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--purge-extra",
            action="store_true",
            help=(
                "Borra de la BD los permisos y asignaciones que NO esten en el "
                "catalogo de este script. UTIL para reset limpio; PELIGROSO si "
                "ya tienes permisos custom fuera del catalogo."
            ),
        )

    def handle(self, *args, **options):
        purge = options.get("purge_extra", False)
        # Import diferido para que el comando se pueda registrar aunque las
        # migraciones de authz no esten aplicadas al cargar.
        from authz.models import Role, Permission, RolePermission

        creados_perm = actualizados_perm = 0
        creados_rol = 0
        creadas_asign = 0

        with transaction.atomic():
            # ── 1. Permisos ──────────────────────────────────────────────────
            for code, desc in PERMISOS:
                perm, created = Permission.objects.get_or_create(
                    code=code,
                    defaults={"description": desc},
                )
                if created:
                    creados_perm += 1
                elif perm.description != desc:
                    perm.description = desc
                    perm.save(update_fields=["description"])
                    actualizados_perm += 1

            # ── 2. Roles ─────────────────────────────────────────────────────
            for name, code, _desc in ROLES:
                _, created = Role.objects.get_or_create(
                    code=code,
                    defaults={"name": name},
                )
                if created:
                    creados_rol += 1

            # ── 3. Asignaciones rol -> permiso ───────────────────────────────
            for role_code, perm_codes in PERMISOS_POR_ROL.items():
                role = Role.objects.get(code=role_code)
                for pcode in perm_codes:
                    perm = Permission.objects.get(code=pcode)
                    _, created = RolePermission.objects.get_or_create(
                        role=role, permission=perm,
                    )
                    if created:
                        creadas_asign += 1

            # ── 4. (Opcional) Purga de elementos fuera del catalogo ─────────
            if purge:
                codigos_catalogo = {c for c, _ in PERMISOS}
                eliminados_perm = Permission.objects.exclude(
                    code__in=codigos_catalogo
                ).delete()[0]

                roles_catalogo = {c for _, c, _ in ROLES}
                eliminados_rol = Role.objects.exclude(
                    code__in=roles_catalogo
                ).delete()[0]

                # Asignaciones huerfanas: rol o permiso fuera del catalogo
                eliminadas_asign = RolePermission.objects.exclude(
                    role__code__in=roles_catalogo,
                    permission__code__in=codigos_catalogo,
                ).delete()[0]

                self.stdout.write(self.style.WARNING(
                    f"  Purga: {eliminados_perm} permisos, {eliminados_rol} "
                    f"roles y {eliminadas_asign} asignaciones eliminados."
                ))

        # ── 5. Resumen ───────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  RBAC sembrado correctamente"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Permisos creados      : {creados_perm}")
        self.stdout.write(f"  Permisos actualizados : {actualizados_perm}")
        self.stdout.write(f"  Roles creados         : {creados_rol}")
        self.stdout.write(f"  Asignaciones creadas  : {creadas_asign}")
        self.stdout.write(
            f"  Total catalogo        : {len(PERMISOS)} permisos, "
            f"{len(ROLES)} roles"
        )
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # ── 6. Tabla resumen por rol (para verificar visualmente) ────────────
        self.stdout.write("\n  Permisos por rol:")
        for name, code, _ in ROLES:
            count = RolePermission.objects.filter(role__code=code).count()
            self.stdout.write(f"    - {name:14s} ({code:14s}): {count} permisos")
