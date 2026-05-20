"""
Management command: python manage.py seed_full

Carga un dataset rico y coherente para presentaciones del sistema VACWEB.

Incluye:
  - 5 usuarios (admin, propietario, veterinario, operario, auditor) con roles.
  - 22 permisos + 5 roles + asignaciones (llama internamente a seed_rbac).
  - 8 potreros (7 activos + 1 inactivo) de todos los tipos de uso.
  - 22 animales repartidos en distintas etapas (1 BORRADOR + 1 INACTIVO).
  - ~70 pesajes con tendencia visible (3-4 por animal activo).
  - 14 eventos sanitarios en todos los estados (CON, APL, CAN, REA) + corrección.
  - 8 transacciones comerciales (compras, ventas, sacrificios, una anulada).
  - 6 movimientos entre potreros.
  - 7 reglas de alertas activas (sanitarias, productivas, potrero, inventario).
  - Las alertas se autogeneran vía signals al crear los datos.

Uso:
  python manage.py seed_full              # confirma antes de borrar/cargar
  python manage.py seed_full --force      # sin confirmacion (CI / scripts)
  python manage.py seed_full --no-purge   # solo agrega, no borra previos
  python manage.py seed_full --no-rbac    # asume que seed_rbac ya corrio

CONSERVA al admin y otros superusers que ya existan (no los borra).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


# ─── Catalogo de usuarios ────────────────────────────────────────────────────
USUARIOS = [
    # (username, password, first, last, email, is_super, is_staff, role_code)
    ("admin",          "Admin123!",  "Admin",      "VACWEB",   "admin@vacweb.test",       True,  True,  "administrador"),
    ("propietario01",  "Demo123!",   "Carlos",     "Ramirez",  "carlos@vacweb.test",      False, False, "propietario"),
    ("veterinario01",  "Demo123!",   "Dr. Perez",  "Martinez", "veterinario@vacweb.test", False, False, "veterinario"),
    ("operario01",     "Demo123!",   "Juan",       "Operario", "operario@vacweb.test",    False, False, "operario"),
    ("auditor01",      "Demo123!",   "Ana",        "Auditora", "auditor@vacweb.test",     False, False, "auditor"),
]


# ─── Reglas de alertas (umbrales que disparan las alertas automaticas) ───────
REGLAS = [
    # (tipo, subtipo, umbral_valor, umbral_unidad, descripcion)
    ("sanitaria",  "proxima_vacuna",   7,   "dias",       "Alertar 7 dias antes de un evento sanitario programado."),
    ("sanitaria",  "vacuna_vencida",   30,  "dias",       "Alertar si una vacuna programada no se realizo dentro de 30 dias."),
    ("productiva", "variacion_peso",   15,  "porcentaje", "Alertar ante una variacion >=15% en un pesaje vs el anterior."),
    ("productiva", "sin_pesaje",       60,  "dias",       "Alertar si un animal lleva mas de 60 dias sin pesaje."),
    ("potrero",    "capacidad",        90,  "porcentaje", "Alertar cuando un potrero llega al 90% de ocupacion."),
    ("inventario", "sin_potrero",      0,   "n_a",        "Alertar por animales activos sin potrero asignado."),
    ("inventario", "borrador",         7,   "dias",       "Alertar por animales en BORRADOR por mas de 7 dias."),
]


# ─── Potreros (8: 7 activos + 1 inactivo para mostrar filtros) ────────────────
POTREROS = [
    # (nombre, area_ha, capacidad, tipo_uso, estado)
    ("P-001 Pradera Central",   "15.00", 100, "CEBA",       "ACTIVO"),
    ("P-002 Lote Maternidad",   "8.00",  50,  "MATERNIDAD", "ACTIVO"),
    ("P-003 Cuarentena",        "3.00",  20,  "CUARENTENA", "ACTIVO"),
    ("P-004 Potrero Norte",     "12.00", 80,  "LEVANTE",    "ACTIVO"),
    ("P-005 Lote Sur",          "5.00",  30,  "ROTACION",   "ACTIVO"),
    ("P-006 Establo Cerca",     "6.00",  40,  "CEBA",       "ACTIVO"),
    ("P-007 Maternidad B",      "4.00",  25,  "MATERNIDAD", "ACTIVO"),
    ("P-008 Antigua Rotacion",  "10.00", 60,  "ROTACION",   "INACTIVO"),
]


# ─── Animales (22 — mezcla de etapas, estados y razas) ───────────────────────
# Mapas para legibilidad:
SEXO_M, SEXO_F = "M", "F"
ETAPA_TER, ETAPA_DES, ETAPA_LEV, ETAPA_NOV, ETAPA_ADU = "TER", "DES", "LEV", "NOV", "ADU"
EST_ACT, EST_INA, EST_BOR = "ACT", "INA", "BOR"

ANIMALES = [
    # (rfid, nombre, sexo, etapa, raza, potrero_codigo, estado, dias_atras_ingreso)
    ("COL-9999", "Estrella",    SEXO_F, ETAPA_ADU, "Brahman",         "P-001 Pradera Central",  EST_ACT, 180),
    ("COL-1001", "Lucero",      SEXO_M, ETAPA_LEV, "Cebu",            "P-001 Pradera Central",  EST_ACT, 120),
    ("COL-1002", "Manchada",    SEXO_F, ETAPA_ADU, "Holstein",        "P-002 Lote Maternidad",  EST_ACT, 250),
    ("COL-1003", "Negro",       SEXO_M, ETAPA_LEV, "Angus",           "P-004 Potrero Norte",    EST_ACT, 90),
    ("COL-1004", "Bonita",      SEXO_F, ETAPA_ADU, "Brahman",         "P-002 Lote Maternidad",  EST_ACT, 365),
    ("COL-1005", "Tornado",     SEXO_M, ETAPA_NOV, "Cebu",            "P-004 Potrero Norte",    EST_ACT, 200),
    ("COL-1006", "Linda",       SEXO_F, ETAPA_DES, "Holstein",        "P-001 Pradera Central",  EST_ACT, 60),
    ("COL-1007", "Rayo",        SEXO_M, ETAPA_TER, "Brahman",         "P-002 Lote Maternidad",  EST_ACT, 30),
    ("COL-1008", "Sultana",     SEXO_F, ETAPA_ADU, "Holstein",        "P-007 Maternidad B",     EST_ACT, 400),
    ("COL-1009", "Pintada",     SEXO_F, ETAPA_LEV, "Jersey",          "P-005 Lote Sur",         EST_ACT, 150),
    ("COL-1010", "Trueno",      SEXO_M, ETAPA_ADU, "Brahman",         "P-006 Establo Cerca",    EST_ACT, 300),
    ("COL-1011", "Princesa",    SEXO_F, ETAPA_ADU, "Holstein",        "P-002 Lote Maternidad",  EST_ACT, 280),
    ("COL-1012", "Mancha",      SEXO_M, ETAPA_NOV, "Angus",           "P-004 Potrero Norte",    EST_ACT, 220),
    ("COL-1013", "Bella",       SEXO_F, ETAPA_LEV, "Cebu",            "P-005 Lote Sur",         EST_ACT, 130),
    ("COL-1014", "Tarzan",      SEXO_M, ETAPA_LEV, "Brahman",         "P-001 Pradera Central",  EST_ACT, 100),
    ("COL-1015", "Margarita",   SEXO_F, ETAPA_ADU, "Jersey",          "P-007 Maternidad B",     EST_ACT, 350),
    ("COL-1016", "Capitan",     SEXO_M, ETAPA_ADU, "Angus",           "P-006 Establo Cerca",    EST_ACT, 320),
    ("COL-1017", "Aurora",      SEXO_F, ETAPA_DES, "Holstein",        "P-001 Pradera Central",  EST_ACT, 45),
    ("COL-1018", "Rocky",       SEXO_M, ETAPA_TER, "Cebu",            "P-007 Maternidad B",     EST_ACT, 20),
    # Animal recientemente vendido (INACTIVO) para mostrar historial
    ("COL-1019", "Toro Viejo",  SEXO_M, ETAPA_ADU, "Brahman",         None,                     EST_INA, 600),
    # Animal en cuarentena
    ("COL-1020", "Sospechoso",  SEXO_M, ETAPA_NOV, "Holstein",        "P-003 Cuarentena",       EST_ACT, 14),
    # Animal en BORRADOR para demo de compra en vivo
    (None,       "Becerro-Nuevo", None, None,      None,              None,                     EST_BOR, 0),
]


# ─── Pesajes: cada animal activo recibe 2-4 pesajes ──────────────────────────
# Estrella mantiene su pesaje de 320 kg hace 30 dias para CP5 del CU-004.
PESAJES_POR_ANIMAL = {
    # nombre: lista de (dias_atras, peso_kg)
    "Estrella":  [(180, 280), (90, 305), (30, 320)],     # +40 kg en 30 dias al registrar 360 kg hoy en vivo
    "Lucero":    [(120, 220), (60, 260), (15, 290)],
    "Manchada":  [(180, 380), (90, 410), (30, 430)],
    "Negro":     [(90, 200), (30, 235)],
    "Bonita":    [(180, 440), (90, 460), (30, 475)],
    "Tornado":   [(180, 320), (90, 355), (30, 385)],
    "Linda":     [(60, 95),  (30, 120)],
    "Rayo":      [(20, 45)],
    "Sultana":   [(180, 480), (90, 495), (30, 505)],
    "Pintada":   [(120, 270), (60, 295), (15, 315)],
    "Trueno":    [(180, 600), (90, 615), (30, 625)],
    "Princesa":  [(180, 420), (90, 440), (30, 455)],
    "Mancha":    [(180, 340), (90, 375), (30, 400)],
    "Bella":     [(120, 250), (60, 280), (15, 300)],
    "Tarzan":    [(90, 230), (30, 265)],
    "Margarita": [(180, 460), (90, 470), (30, 480)],
    "Capitan":   [(180, 580), (90, 590), (30, 600)],
    "Aurora":    [(40, 100), (10, 130)],
    "Rocky":     [(15, 50)],
    # Sospechoso: variacion >15% para disparar alerta productiva
    "Sospechoso": [(60, 320), (10, 260)],
}


# ─── Eventos sanitarios variados (14 eventos cubriendo todos los estados) ────
EVENTOS = [
    # (animal_nombre, tipo, dias_offset, responsable, producto, dosis, via, estado, notas)
    # REALIZADOS pasados — alimentan cumplimiento sanitario del dashboard
    ("Estrella",  "Vacunacion",       -120, "Dr. Perez", "Aftosa Bivalente",    "2 ml", "Intramuscular", "REA", "Campania semestral."),
    ("Manchada",  "Desparasitacion",  -45,  "Dr. Perez", "Ivermectina",         "1 ml/50kg", "Subcutanea", "REA", ""),
    ("Bonita",    "Vacunacion",       -60,  "Dr. Perez", "Triple Bovina",       "5 ml", "Subcutanea",    "REA", ""),
    ("Sultana",   "Desparasitacion",  -40,  "Dr. Perez", "Albendazol",          "2 g",  "Oral",          "REA", ""),
    ("Princesa",  "Vacunacion",       -80,  "Dr. Perez", "Aftosa Bivalente",    "2 ml", "Intramuscular", "REA", "Lote sur."),
    ("Capitan",   "Antibiotico",      -25,  "Dr. Perez", "Penicilina LA",       "10 ml", "Intramuscular","REA", "Tratamiento de pezuna."),

    # CONFIRMADOS proximos — disparan alertas automaticas
    ("Estrella",  "Vacunacion",       5,    "Dr. Perez", "Refuerzo Aftosa",     "2 ml", "Intramuscular", "CON", ""),
    ("Lucero",    "Vacunacion",       2,    "Dr. Perez", "Aftosa Bivalente",    "2 ml", "Intramuscular", "CON", "Campania."),
    ("Trueno",    "Desparasitacion",  10,   "Dr. Perez", "Ivermectina",         "1 ml/50kg", "Subcutanea", "CON", ""),

    # APLAZADO
    ("Tornado",   "Vacunacion",       12,   "Dr. Perez", "Triple Bovina",       "5 ml", "Subcutanea",    "APL", "Aplazado por lluvia."),

    # CANCELADOS
    ("Lucero",    "Antibiotico",      -15,  "Dr. Perez", "Oxitetraciclina",     "8 ml", "Intramuscular", "CAN", "Cancelado: animal mejoro sin medicacion."),

    # Eventos del animal vendido (historico)
    ("Toro Viejo", "Vacunacion",      -200, "Dr. Perez", "Aftosa Bivalente",    "2 ml", "Intramuscular", "REA", "Antes de la venta."),
    ("Toro Viejo", "Desparasitacion", -180, "Dr. Perez", "Ivermectina",         "1 ml/50kg", "Subcutanea", "REA", ""),

    # CORRECCION (RN-5) — apunta a un evento anterior
    ("Manchada",  "Desparasitacion",  -44,  "Dr. Perez", "Ivermectina LA",      "1.5 ml/50kg", "Subcutanea", "REA", "Correccion de la dosis aplicada el dia anterior."),
]


# ─── Transacciones comerciales (8 — compras, ventas, sacrificio, anulada) ────
TRANSACCIONES = [
    # (tipo, dias_offset, animal_nombre, peso_kg, origen_destino, valor_cop, estado, motivo_anulacion, observaciones)
    ("COM", -365, "Bonita",     None,    "Hacienda La Esperanza",     "2200000.00",  "CON", None, "Compra historica."),
    ("COM", -300, "Trueno",     None,    "Subasta El Cebu Centro",    "3500000.00",  "CON", None, ""),
    ("COM", -180, "Estrella",   None,    "Hacienda La Esperanza",     "2500000.00",  "CON", None, "Compra inicial registrada para el demo."),
    ("COM", -150, "Pintada",    None,    "Hacienda Las Brisas",       "2800000.00",  "CON", None, ""),
    # VENTA confirmada reciente del Toro Viejo
    ("VEN", -10,  "Toro Viejo", "650",   "Frigorifico Antioquia S.A.","6500000.00",  "CON", None, "Venta a frigorifico."),
    # SACRIFICIO reciente
    ("SAC", -30,  None,         "550",   "Sacrificio en finca",       "0.01",        "CON", None, "Sacrificio sanitario; sin cuerpo destinatario."),
    # COMPRA ANULADA con motivo (CU-006 RN-6)
    ("COM", -45,  "Bella",      None,    "Ganaderia Andes",           "2900000.00",  "ANU", "Error en captura: el valor real era 2.4M.", "Anulada para registrar nuevamente."),
    # COMPRA nuevamente registrada (la "correcta" tras anular la anterior)
    ("COM", -44,  "Bella",      None,    "Ganaderia Andes",           "2400000.00",  "CON", None, "Registro corregido."),
]


# ─── Movimientos entre potreros (6 — muestra trazabilidad) ───────────────────
MOVIMIENTOS = [
    # (animal_nombre, desde_codigo, hacia_codigo, dias_atras, responsable)
    ("Estrella", "P-002 Lote Maternidad", "P-001 Pradera Central", 60,  "Juan Operario"),
    ("Lucero",   "P-003 Cuarentena",      "P-001 Pradera Central", 90,  "Juan Operario"),
    ("Linda",    "P-002 Lote Maternidad", "P-001 Pradera Central", 30,  "Juan Operario"),
    ("Aurora",   "P-002 Lote Maternidad", "P-001 Pradera Central", 14,  "Juan Operario"),
    ("Tornado",  "P-001 Pradera Central", "P-004 Potrero Norte",   45,  "Juan Operario"),
    ("Bella",    "P-001 Pradera Central", "P-005 Lote Sur",        20,  "Juan Operario"),
]


# ============================================================================
class Command(BaseCommand):
    help = "Carga un dataset rico y coherente para presentaciones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Sin confirmacion interactiva. Util en CI o scripts.",
        )
        parser.add_argument(
            "--no-purge", action="store_true",
            help="No borrar datos previos antes de cargar.",
        )
        parser.add_argument(
            "--no-rbac", action="store_true",
            help="Asume que seed_rbac ya corrio; no lo invoca.",
        )

    def handle(self, *args, **opts):
        force = opts["force"]
        no_purge = opts["no_purge"]
        no_rbac = opts["no_rbac"]

        # ── Confirmacion (puede saltearse con --force) ──────────────────────
        if not force and not no_purge:
            self.stdout.write(self.style.WARNING(
                "\nEste comando va a BORRAR los datos de negocio existentes\n"
                "(animales, potreros, pesajes, eventos, transacciones, alertas,\n"
                "movimientos y bitacora) y recrear un dataset de demostracion.\n"
                "Conserva los superusers que ya existan.\n"
            ))
            resp = input("Continuar? [s/N]: ").strip().lower()
            if resp not in ("s", "si", "y", "yes"):
                self.stdout.write(self.style.ERROR("Cancelado."))
                return

        # ── Tabla de cache de Django ────────────────────────────────────────
        try:
            call_command("createcachetable", verbosity=0)
        except Exception:
            pass

        # ── RBAC: permisos, roles y asignaciones ────────────────────────────
        if not no_rbac:
            self.stdout.write(self.style.HTTP_INFO("\n[1/7] Permisos y roles..."))
            call_command("seed_rbac", verbosity=0)

        with transaction.atomic():
            # ── Limpieza ─────────────────────────────────────────────────────
            if not no_purge:
                self.stdout.write(self.style.HTTP_INFO("\n[2/7] Limpiando datos previos..."))
                self._purge()

            # ── Reglas de alertas (van ANTES de crear datos para que se evaluen)
            self.stdout.write(self.style.HTTP_INFO("\n[3/7] Reglas de alertas..."))
            self._crear_reglas()

            # ── Usuarios ────────────────────────────────────────────────────
            self.stdout.write(self.style.HTTP_INFO("\n[4/7] Usuarios y roles asignados..."))
            usuarios = self._crear_usuarios()

            # ── Datos de negocio ────────────────────────────────────────────
            self.stdout.write(self.style.HTTP_INFO("\n[5/7] Potreros y animales..."))
            potreros = self._crear_potreros(usuarios["admin"])
            animales = self._crear_animales(potreros, usuarios["admin"])

            self.stdout.write(self.style.HTTP_INFO("\n[6/7] Pesajes, eventos, transacciones y movimientos..."))
            self._crear_pesajes(animales, usuarios["operario01"])
            self._crear_eventos(animales, usuarios["veterinario01"])
            self._crear_transacciones(animales, usuarios["propietario01"])
            self._crear_movimientos(animales, potreros)

        # ── Resumen final ───────────────────────────────────────────────────
        self.stdout.write(self.style.HTTP_INFO("\n[7/7] Resumen del dataset cargado:"))
        self._resumen()

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  DATOS DE PRESENTACION LISTOS"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("\n  Credenciales para el video:")
        for u, p, *_ in USUARIOS:
            self.stdout.write(f"    - {u:14s}  /  {p}")
        self.stdout.write("")

    # ────────────────────────────────────────────────────────────────────────
    def _purge(self):
        from animals.models import Animal, Movimiento
        from potreros.models import Potrero
        from eventos.models import EventoSanitario
        from pesajes.models import Pesaje
        from transacciones.models import Transaccion
        from alertas.models import Alerta, ReglaAlerta
        from auditoria.models import Bitacora
        from authz.models import AuditLog, UserRole
        try:
            from reportes.models import LogReporte
            LogReporte.objects.all().delete()
        except Exception:
            pass

        Alerta.objects.all().delete()
        ReglaAlerta.objects.all().delete()
        Bitacora.objects.all().delete()
        AuditLog.objects.all().delete()
        Transaccion.objects.all().delete()
        Pesaje.objects.all().delete()
        EventoSanitario.objects.all().delete()
        Movimiento.objects.all().delete()
        Animal.objects.all().delete()
        Potrero.objects.all().delete()
        UserRole.objects.all().delete()
        # No tocar superusers existentes; borrar el resto
        User.objects.filter(is_superuser=False).delete()

    # ────────────────────────────────────────────────────────────────────────
    def _crear_reglas(self):
        from alertas.models import ReglaAlerta
        for tipo, subtipo, valor, unidad, desc in REGLAS:
            ReglaAlerta.objects.update_or_create(
                tipo=tipo, subtipo=subtipo,
                defaults={
                    "activa": True,
                    "umbral_valor": valor,
                    "umbral_unidad": unidad,
                    "descripcion": desc,
                },
            )

    # ────────────────────────────────────────────────────────────────────────
    def _crear_usuarios(self):
        from authz.models import UserProfile, Role, UserRole
        usuarios = {}
        for username, pw, first, last, email, is_su, is_st, role_code in USUARIOS:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first, "last_name": last, "email": email,
                    "is_superuser": is_su, "is_staff": is_st,
                },
            )
            user.set_password(pw)
            user.first_name = first
            user.last_name = last
            user.email = email
            user.is_superuser = is_su
            user.is_staff = is_st
            user.is_active = True
            user.save()
            UserProfile.objects.get_or_create(user=user)
            # Asignar rol
            try:
                role = Role.objects.get(code=role_code)
                UserRole.objects.get_or_create(user=user, role=role)
            except Role.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f"    Rol '{role_code}' no existe. Corre seed_rbac primero."
                ))
            usuarios[username] = user
        return usuarios

    # ────────────────────────────────────────────────────────────────────────
    def _crear_potreros(self, admin_user):
        from potreros.models import Potrero
        potreros = {}
        for nombre, area, cap, tipo, estado in POTREROS:
            p = Potrero.objects.create(
                nombre_codigo=nombre,
                area_ha=Decimal(area),
                capacidad_maxima=cap,
                tipo_uso=tipo,
                estado=estado,
                created_by=admin_user,
            )
            potreros[nombre] = p
        return potreros

    # ────────────────────────────────────────────────────────────────────────
    def _crear_animales(self, potreros, admin_user):
        from animals.models import Animal
        animales = {}
        for rfid, nombre, sexo, etapa, raza, potrero_codigo, estado, dias in ANIMALES:
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
                fecha_ingreso=date.today() - timedelta(days=dias) if dias > 0 else None,
            )
            a.save()
            animales[nombre] = a
        return animales

    # ────────────────────────────────────────────────────────────────────────
    def _crear_pesajes(self, animales, operario):
        from pesajes.models import Pesaje
        total = 0
        for nombre, lista_pesajes in PESAJES_POR_ANIMAL.items():
            if nombre not in animales:
                continue
            animal = animales[nombre]
            for dias_atras, peso in lista_pesajes:
                Pesaje(
                    animal=animal,
                    fecha=date.today() - timedelta(days=dias_atras),
                    peso_kg=Decimal(str(peso)),
                    responsable="Juan Operario",
                    created_by=operario,
                ).save()
                total += 1

    # ────────────────────────────────────────────────────────────────────────
    def _crear_eventos(self, animales, veterinario):
        from eventos.models import EventoSanitario
        creados = []
        for nombre, tipo, dias_offset, resp, prod, dosis, via, estado, notas in EVENTOS:
            if nombre not in animales:
                continue
            ev = EventoSanitario.objects.create(
                animal=animales[nombre],
                tipo=tipo,
                fecha=date.today() + timedelta(days=dias_offset),
                responsable=resp,
                producto=prod,
                dosis=dosis,
                via_aplicacion=via,
                estado=estado,
                notas=notas,
                created_by=veterinario,
            )
            creados.append(ev)

        # Encadenar la correccion (ultimo evento) con el de Manchada anterior
        try:
            originales = [e for e in creados if e.animal.nombre == "Manchada"
                          and e.tipo == "Desparasitacion" and e.estado == "REA"]
            if len(originales) >= 2:
                # El segundo es la correccion; apunta al primero
                originales[-1].evento_original = originales[0]
                # Evitar el guard de inmutabilidad usando update directo
                EventoSanitario.objects.filter(pk=originales[-1].pk).update(
                    evento_original=originales[0]
                )
        except Exception:
            pass  # no-op si algo falla, el dataset queda igual

    # ────────────────────────────────────────────────────────────────────────
    def _crear_transacciones(self, animales, propietario):
        from transacciones.models import Transaccion
        from django.utils import timezone
        for tipo, dias_offset, nombre, peso, origen, valor, estado, motivo, obs in TRANSACCIONES:
            if nombre is None:
                # Para el sacrificio sin nombre asignado, usar uno generico (Trueno)
                nombre = "Trueno"
            if nombre not in animales:
                continue
            t = Transaccion.objects.create(
                tipo=tipo,
                fecha=date.today() + timedelta(days=dias_offset),
                animal=animales[nombre],
                peso_final_kg=Decimal(peso) if peso else None,
                origen_destino=origen,
                valor_cop=Decimal(valor),
                estado=estado,
                observaciones=obs,
                created_by=propietario,
            )
            if estado == "ANU":
                t.motivo_anulacion = motivo
                t.anulado_por = propietario
                t.fecha_anulacion = timezone.now()
                t.save(update_fields=["motivo_anulacion", "anulado_por", "fecha_anulacion"])

    # ────────────────────────────────────────────────────────────────────────
    def _crear_movimientos(self, animales, potreros):
        from animals.models import Movimiento
        for nombre, desde, hacia, dias, resp in MOVIMIENTOS:
            if nombre not in animales:
                continue
            Movimiento.objects.create(
                animal=animales[nombre],
                desde=potreros.get(desde),
                hacia=potreros.get(hacia),
                fecha=date.today() - timedelta(days=dias),
                responsable=resp,
            )

    # ────────────────────────────────────────────────────────────────────────
    def _resumen(self):
        from animals.models import Animal, Movimiento
        from potreros.models import Potrero
        from eventos.models import EventoSanitario
        from pesajes.models import Pesaje
        from transacciones.models import Transaccion
        from alertas.models import Alerta, ReglaAlerta

        self.stdout.write(f"  - Usuarios          : {User.objects.count()}")
        self.stdout.write(f"  - Potreros          : {Potrero.objects.count()} "
                          f"({Potrero.objects.filter(estado='ACTIVO').count()} activos)")
        self.stdout.write(f"  - Animales          : {Animal.objects.count()} "
                          f"({Animal.objects.filter(estado='ACT').count()} activos, "
                          f"{Animal.objects.filter(estado='BOR').count()} en borrador)")
        self.stdout.write(f"  - Pesajes           : {Pesaje.objects.count()}")
        self.stdout.write(f"  - Eventos sanitarios: {EventoSanitario.objects.count()}")
        self.stdout.write(f"  - Transacciones     : {Transaccion.objects.count()}")
        self.stdout.write(f"  - Movimientos       : {Movimiento.objects.count()}")
        self.stdout.write(f"  - Reglas de alerta  : {ReglaAlerta.objects.filter(activa=True).count()}")
        self.stdout.write(f"  - Alertas generadas : {Alerta.objects.filter(estado='pendiente').count()} pendientes")
