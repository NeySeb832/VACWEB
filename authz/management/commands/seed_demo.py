"""
Management command: python manage.py seed_demo

Llena la BD activa con datos coherentes para grabar los videos
de calidad externa y en uso de los CU del 002 al 010.

IMPORTANTE — Seguridad:
  Este comando SOLO se ejecuta si la BD activa NO es 'soft_animales'.
  Es decir, solo funciona cuando VACWEB_DB_NAME=soft_animales_demo
  (o cualquier otra distinta de la real).
  Esto protege tus datos reales de un borrado accidental.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


# ---------- Configuración de datos demo ----------

USUARIOS_DEMO = [
    # username, password, first_name, last_name, email, is_superuser, is_staff
    ("admin",          "Admin123!",  "Admin",       "VACWEB",   "admin@vacweb.test",        True,  True),
    ("propietario01",  "Demo123!",   "Carlos",      "Ramírez",  "carlos@vacweb.test",       False, False),
    ("veterinario01",  "Demo123!",   "Dr. Pérez",   "Martínez", "veterinario@vacweb.test",  False, False),
    ("operario01",     "Demo123!",   "Juan",        "Operario", "operario@vacweb.test",     False, False),
    ("auditor01",      "Demo123!",   "Ana",         "Auditora", "auditor@vacweb.test",      False, False),
]

# Permisos extra (los de animals no los crea ninguna migración)
PERMISOS_EXTRA = [
    ("animals.read",  "Ver el listado y detalle de animales"),
    ("animals.write", "Crear, editar y dar de baja animales"),
]

ROLES_DEMO = [
    # name, code, descripcion
    ("Administrador", "administrador", "Acceso total al sistema"),
    ("Propietario",   "propietario",   "Dueño de la finca"),
    ("Veterinario",   "veterinario",   "Profesional sanitario"),
    ("Operario",      "operario",      "Personal de campo"),
    ("Auditor",       "auditor",       "Solo lectura de bitácora"),
]

# Asignación de permisos a roles
PERMISOS_POR_ROL = {
    "administrador": [
        "animals.read", "animals.write",
        "potreros.read", "potreros.write",
        "eventos.read", "eventos.write",
        "pesajes.read", "pesajes.write",
        "transacciones.read", "transacciones.write", "transacciones.anular",
        "reportes.read", "reportes.export",
        "alertas.view_alertas", "alertas.atender_alertas", "alertas.configurar_alertas",
        "dashboard.read",
        "auditoria.read",
        "users.read", "users.write", "users.delete",
        "roles.read", "roles.write",
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
    ],
}

ROLES_DE_USUARIOS = {
    "admin":          ["administrador"],
    "propietario01":  ["propietario"],
    "veterinario01":  ["veterinario"],
    "operario01":     ["operario"],
    "auditor01":      ["auditor"],
}

POTREROS_DEMO = [
    # nombre_codigo, area_ha, capacidad, tipo_uso, estado
    ("P-001 Pradera Central", "15.00", 100, "CEBA",       "ACTIVO"),
    ("P-002 Lote Maternidad", "8.00",  50,  "MATERNIDAD", "ACTIVO"),
    ("P-003 Cuarentena",      "3.00",  20,  "CUARENTENA", "ACTIVO"),
    ("P-004 Potrero Norte",   "12.00", 80,  "LEVANTE",    "ACTIVO"),
    ("P-005 Lote Sur",        "5.00",  30,  "ROTACION",   "INACTIVO"),
]

# Animales clave referenciados en los guiones
ANIMALES_DEMO = [
    # rfid, nombre, sexo, etapa, raza, potrero_codigo, estado
    ("COL-9999", "Estrella",       "F", "ADU", "Brahman",        "P-001 Pradera Central", "ACT"),
    ("COL-1001", "Lucero",         "M", "LEV", "Cebú",           "P-001 Pradera Central", "ACT"),
    ("COL-1002", "Manchada",       "F", "ADU", "Holstein",       "P-002 Lote Maternidad", "ACT"),
    ("COL-1003", "Negro",          "M", "LEV", "Angus",          "P-004 Potrero Norte",   "ACT"),
    ("COL-1004", "Bonita",         "F", "ADU", "Brahman",        "P-002 Lote Maternidad", "ACT"),
    ("COL-1005", "Tornado",        "M", "NOV", "Cebú",           "P-004 Potrero Norte",   "ACT"),
    ("COL-1006", "Linda",          "F", "DES", "Holstein",       "P-001 Pradera Central", "ACT"),
    ("COL-1007", "Rayo",           "M", "TER", "Brahman",        "P-002 Lote Maternidad", "ACT"),
    # Animal en BORRADOR para que demos puedan registrar COMPRA durante el video
    (None,       "Becerro-Nuevo",  None, None, None,             None,                    "BOR"),
]


class Command(BaseCommand):
    help = "Pobla la BD demo con usuarios, potreros, animales y eventos para grabar videos."

    def handle(self, *args, **options):
        # SEGURIDAD: bloquear ejecución sobre la BD real
        db_name = settings.DATABASES["default"]["NAME"]
        if db_name == "soft_animales":
            raise CommandError(
                "BLOQUEADO: No se puede ejecutar seed_demo sobre la BD real 'soft_animales'.\n"
                "Define la variable de entorno VACWEB_DB_NAME=soft_animales_demo antes de ejecutar."
            )

        self.stdout.write(self.style.WARNING(f"BD activa: {db_name}"))
        self.stdout.write(self.style.WARNING("Se van a borrar y recrear los datos demo...\n"))

        # Asegurar tabla de caché de Django (authz_cache) — necesaria para login
        from django.core.management import call_command
        try:
            call_command("createcachetable", verbosity=0)
        except Exception:
            pass  # ya existe

        with transaction.atomic():
            self._limpiar()
            self._crear_permisos_extra()
            self._crear_roles_y_asignar_permisos()
            usuarios = self._crear_usuarios()
            self._asignar_roles_a_usuarios(usuarios)
            potreros = self._crear_potreros(usuarios["admin"])
            animales = self._crear_animales(potreros, usuarios["admin"])
            self._crear_pesajes(animales, usuarios["operario01"])
            self._crear_eventos(animales, usuarios["veterinario01"])
            self._crear_transacciones(animales, usuarios["propietario01"])

        self.stdout.write(self.style.SUCCESS("\n========== DATOS DEMO LISTOS =========="))
        self.stdout.write(self.style.SUCCESS("Usuarios creados:"))
        for u, p, *_ in USUARIOS_DEMO:
            self.stdout.write(f"  - {u} / {p}")
        self.stdout.write(self.style.SUCCESS("\nYa puedes correr:  demo_iniciar.bat"))

    # ------------------------------------------------------------------
    def _limpiar(self):
        from animals.models import Animal, Movimiento
        from potreros.models import Potrero
        from eventos.models import EventoSanitario
        from pesajes.models import Pesaje
        from transacciones.models import Transaccion
        from alertas.models import Alerta, ReglaAlerta
        from auditoria.models import Bitacora
        from authz.models import AuditLog, UserRole, RolePermission, Role

        # Borrar en orden inverso a las FK
        Alerta.objects.all().delete()
        Bitacora.objects.all().delete()
        AuditLog.objects.all().delete()
        Transaccion.objects.all().delete()
        Pesaje.objects.all().delete()
        EventoSanitario.objects.all().delete()
        Movimiento.objects.all().delete()
        Animal.objects.all().delete()
        Potrero.objects.all().delete()
        UserRole.objects.all().delete()
        # Borrar usuarios no-superuser para no perder admin si ya existe
        User.objects.filter(is_superuser=False).delete()
        # Roles
        Role.objects.all().delete()
        self.stdout.write("  Datos previos limpiados.")

    # ------------------------------------------------------------------
    def _crear_permisos_extra(self):
        from authz.models import Permission
        for code, desc in PERMISOS_EXTRA:
            Permission.objects.get_or_create(code=code, defaults={"description": desc})
        self.stdout.write(f"  Permisos animals.* asegurados.")

    # ------------------------------------------------------------------
    def _crear_roles_y_asignar_permisos(self):
        from authz.models import Role, Permission, RolePermission

        for name, code, _desc in ROLES_DEMO:
            role, _ = Role.objects.get_or_create(code=code, defaults={"name": name})

        for role_code, perm_codes in PERMISOS_POR_ROL.items():
            role = Role.objects.get(code=role_code)
            for pcode in perm_codes:
                try:
                    perm = Permission.objects.get(code=pcode)
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"    ! Permiso no existe: {pcode}"))
                    continue
                RolePermission.objects.get_or_create(role=role, permission=perm)
        self.stdout.write(f"  {len(ROLES_DEMO)} roles creados con sus permisos.")

    # ------------------------------------------------------------------
    def _crear_usuarios(self):
        from authz.models import UserProfile

        usuarios = {}
        for username, password, first, last, email, is_super, is_staff in USUARIOS_DEMO:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "is_superuser": is_super,
                    "is_staff": is_staff,
                },
            )
            user.set_password(password)
            user.first_name = first
            user.last_name = last
            user.email = email
            user.is_superuser = is_super
            user.is_staff = is_staff
            user.is_active = True
            user.save()
            UserProfile.objects.get_or_create(user=user)
            usuarios[username] = user
        self.stdout.write(f"  {len(usuarios)} usuarios creados.")
        return usuarios

    # ------------------------------------------------------------------
    def _asignar_roles_a_usuarios(self, usuarios):
        from authz.models import Role, UserRole

        for username, role_codes in ROLES_DE_USUARIOS.items():
            user = usuarios[username]
            for code in role_codes:
                role = Role.objects.get(code=code)
                UserRole.objects.get_or_create(user=user, role=role)

    # ------------------------------------------------------------------
    def _crear_potreros(self, admin_user):
        from potreros.models import Potrero

        potreros = {}
        for nombre, area, cap, tipo, estado in POTREROS_DEMO:
            p = Potrero.objects.create(
                nombre_codigo=nombre,
                area_ha=Decimal(area),
                capacidad_maxima=cap,
                tipo_uso=tipo,
                estado=estado,
                created_by=admin_user,
            )
            potreros[nombre] = p
        self.stdout.write(f"  {len(potreros)} potreros creados.")
        return potreros

    # ------------------------------------------------------------------
    def _crear_animales(self, potreros, admin_user):
        from animals.models import Animal

        animales = {}
        for rfid, nombre, sexo, etapa, raza, potrero_codigo, estado in ANIMALES_DEMO:
            potrero = potreros.get(potrero_codigo) if potrero_codigo else None
            a = Animal(
                rfid=rfid,
                nombre=nombre,
                sexo=sexo,
                etapa=etapa,
                raza=raza,
                potrero=potrero,
                estado=estado,
                last_modified_by=admin_user,
                fecha_ingreso=date.today() - timedelta(days=180),
            )
            # Evitar validación clean() para BORRADOR sin datos
            a.save()
            animales[nombre] = a
        self.stdout.write(f"  {len(animales)} animales creados.")
        return animales

    # ------------------------------------------------------------------
    def _crear_pesajes(self, animales, operario):
        """Crea pesajes históricos.

        Para CP5 de CU-004 (cálculo conocido):
          - Estrella tiene UN pesaje previo: 320 kg hace 30 días.
          - Cuando el grabador registre 360 kg hoy, la variación = 40 kg
            y la ganancia diaria = 40/30 = 1.33 kg/día (1333 g/día).
        """
        from pesajes.models import Pesaje

        estrella = animales["Estrella"]
        hace_30 = date.today() - timedelta(days=30)

        Pesaje(
            animal=estrella, fecha=hace_30, peso_kg=Decimal("320.00"),
            responsable="Operario inicial", created_by=operario,
        ).save()

        # Pesaje único en otros animales (para que el dashboard tenga datos)
        for nombre in ["Lucero", "Negro", "Bonita"]:
            Pesaje(
                animal=animales[nombre],
                fecha=hace_30,
                peso_kg=Decimal("280.00"),
                responsable="Operario inicial",
                created_by=operario,
            ).save()

        self.stdout.write(f"  Pesajes históricos creados (4) — Estrella 320kg lista para CP5.")

    # ------------------------------------------------------------------
    def _crear_eventos(self, animales, veterinario):
        from eventos.models import EventoSanitario

        # 1) Evento CONFIRMADO con fecha en 5 días → dispara alerta automática
        EventoSanitario.objects.create(
            animal=animales["Estrella"],
            tipo="Vacunación",
            fecha=date.today() + timedelta(days=5),
            responsable="Dr. Pérez",
            producto="Aftosa Bivalente",
            dosis="2 ml",
            via_aplicacion="Intramuscular",
            estado="CON",
            created_by=veterinario,
        )

        # 2) Evento REALIZADO en el pasado (para mostrar inmutabilidad)
        EventoSanitario.objects.create(
            animal=animales["Manchada"],
            tipo="Desparasitación",
            fecha=date.today() - timedelta(days=45),
            responsable="Dr. Pérez",
            producto="Ivermectina",
            dosis="1 ml/50kg",
            estado="REA",
            created_by=veterinario,
        )

        # 3) Evento CANCELADO (para mostrar estado terminal)
        EventoSanitario.objects.create(
            animal=animales["Lucero"],
            tipo="Vacunación",
            fecha=date.today() - timedelta(days=15),
            responsable="Dr. Pérez",
            producto="Triple Bovina",
            estado="CAN",
            notas="Cancelado: animal en cuarentena.",
            created_by=veterinario,
        )

        self.stdout.write(f"  3 eventos sanitarios creados (1 dispara alerta).")

    # ------------------------------------------------------------------
    def _crear_transacciones(self, animales, propietario):
        from transacciones.models import Transaccion

        # COMPRA inicial de Estrella (confirmada, hace meses)
        Transaccion.objects.create(
            tipo="COM",
            fecha=date.today() - timedelta(days=180),
            animal=animales["Estrella"],
            origen_destino="Hacienda La Esperanza",
            valor_cop=Decimal("2500000.00"),
            estado="CON",
            observaciones="Compra inicial registrada para el demo.",
            created_by=propietario,
        )
        self.stdout.write(f"  1 transacción de compra inicial creada.")
