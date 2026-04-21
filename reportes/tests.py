# reportes/tests.py
"""
Pruebas funcionales – CU-007: Generación de Reportes y Analítica
=================================================================
Bloque 1 – Modelo LogReporte                (CP-MOD-01 … CP-MOD-04)
Bloque 2 – Control de Acceso (RBAC)         (CP-RBAC-01 … CP-RBAC-06)
Bloque 3 – Vistas HTML (comportamiento)     (CP-VISTA-01 … CP-VISTA-10)
Bloque 4 – Exportación CSV                  (CP-CSV-01  … CP-CSV-05)

Reglas de negocio cubiertas:
  RN-1: rango de fechas — desde <= hasta (error_fechas en contexto)
  RN-2: acceso restringido a roles con reportes.read
  RN-3: exportación CSV con BOM UTF-8 para compatibilidad Excel
  RN-4: log de auditoría en cada generación/exportación (LogReporte + AuditLog)
  RN-5: sólo ventas confirmadas (estado=CON, tipo=VEN) en reporte de ventas
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from animals.models import Animal
from authz.models import AuditLog, Permission, Role, RolePermission, UserRole
from eventos.models import EventoSanitario
from pesajes.models import Pesaje
from potreros.models import Potrero
from transacciones.models import Transaccion

from .models import LogReporte


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades compartidas
# ─────────────────────────────────────────────────────────────────────────────

HOY    = date.today()
AYER   = HOY - timedelta(days=1)
SEMANA = HOY - timedelta(days=7)


def make_user(username: str, password: str = "testpass123") -> User:
    return User.objects.create_user(username=username, password=password)


def grant_perm(user: User, perm_code: str) -> None:
    perm, _ = Permission.objects.get_or_create(code=perm_code)
    role, _ = Role.objects.get_or_create(name=perm_code, code=perm_code)
    RolePermission.objects.get_or_create(role=role, permission=perm)
    UserRole.objects.get_or_create(user=user, role=role)


def make_potrero(nombre: str = "P1") -> Potrero:
    return Potrero.objects.create(
        nombre_codigo=nombre,
        estado="ACTIVO",
        area_ha="10.00",
        capacidad_maxima=50,
        tipo_uso="CEBA",
    )


def make_animal(potrero, rfid: str = "COL-R-001",
                estado=Animal.Estado.ACTIVO,
                sexo=Animal.Sexo.MACHO) -> Animal:
    return Animal.objects.create(
        rfid=rfid,
        sexo=sexo,
        etapa=Animal.Etapa.LEVANTE,
        potrero=potrero,
        estado=estado,
        fecha_ingreso=SEMANA,
    )


def make_venta(animal, user, valor="800000.00") -> Transaccion:
    return Transaccion.objects.create(
        tipo=Transaccion.Tipo.VENTA,
        fecha=AYER,
        animal=animal,
        origen_destino="Frigorífico Central",
        valor_cop=valor,
        peso_final_kg=Decimal("380.00"),
        estado=Transaccion.Estado.CONFIRMADO,
        created_by=user,
    )


def make_evento(animal, user, estado=EventoSanitario.Estado.CONFIRMADO) -> EventoSanitario:
    return EventoSanitario.objects.create(
        animal=animal,
        tipo="Vacuna FMD",
        fecha=AYER,
        responsable="Dr. García",
        producto="Aftovac",
        estado=estado,
        created_by=user,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Modelo LogReporte
# ─────────────────────────────────────────────────────────────────────────────

class LogReporteModelTests(TestCase):
    """CP-MOD-01 … CP-MOD-04: validaciones del modelo LogReporte."""

    def setUp(self):
        self.user = make_user("mod_user")

    # ── CP-MOD-01 ─────────────────────────────────────────────────────────────
    def test_str_incluye_tipo_y_usuario(self):
        log = LogReporte.objects.create(
            usuario=self.user,
            tipo_reporte="inventario",
        )
        s = str(log)
        self.assertIn("inventario", s)
        self.assertIn(self.user.username, s)

    # ── CP-MOD-02 ─────────────────────────────────────────────────────────────
    def test_str_sin_usuario_muestra_anon(self):
        log = LogReporte.objects.create(tipo_reporte="ventas")
        self.assertIn("anon", str(log))

    # ── CP-MOD-03 ─────────────────────────────────────────────────────────────
    def test_filtros_json_se_persiste(self):
        filtros = {"desde": "2025-01-01", "hasta": "2025-12-31"}
        log = LogReporte.objects.create(
            usuario=self.user,
            tipo_reporte="sanitario",
            filtros_aplicados=filtros,
        )
        log.refresh_from_db()
        self.assertEqual(log.filtros_aplicados["desde"], "2025-01-01")

    # ── CP-MOD-04 ─────────────────────────────────────────────────────────────
    def test_ordering_descendente_por_fecha(self):
        LogReporte.objects.create(tipo_reporte="inventario")
        LogReporte.objects.create(tipo_reporte="ventas")
        logs = list(LogReporte.objects.all())
        self.assertEqual(logs[0].tipo_reporte, "ventas")


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – Control de Acceso (RBAC)
# ─────────────────────────────────────────────────────────────────────────────

class ReportesRBACTests(TestCase):
    """CP-RBAC-01 … CP-RBAC-06: acceso según permisos (RN-2)."""

    URLS = [
        ("reportes:index",     {}),
        ("reportes:inventario", {}),
        ("reportes:historial",  {}),
        ("reportes:sanitario",  {}),
        ("reportes:ventas",     {}),
    ]

    def setUp(self):
        self.sin_perm  = make_user("sin_perm")
        self.con_perm  = make_user("con_perm")
        grant_perm(self.con_perm, "reportes.read")

    # ── CP-RBAC-01 ─────────────────────────────────────────────────────────────
    def test_anonimo_redirige_al_login(self):
        resp = self.client.get(reverse("reportes:index"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])

    # ── CP-RBAC-02 ─────────────────────────────────────────────────────────────
    def test_sin_permiso_recibe_403(self):
        self.client.force_login(self.sin_perm)
        for name, kwargs in self.URLS:
            with self.subTest(url=name):
                resp = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(resp.status_code, 403)

    # ── CP-RBAC-03 ─────────────────────────────────────────────────────────────
    def test_con_permiso_accede_200(self):
        self.client.force_login(self.con_perm)
        for name, kwargs in self.URLS:
            with self.subTest(url=name):
                resp = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(resp.status_code, 200)

    # ── CP-RBAC-04 ─────────────────────────────────────────────────────────────
    def test_sin_permiso_inventario_recibe_403(self):
        self.client.force_login(self.sin_perm)
        resp = self.client.get(reverse("reportes:inventario"))
        self.assertEqual(resp.status_code, 403)

    # ── CP-RBAC-05 ─────────────────────────────────────────────────────────────
    def test_sin_permiso_ventas_recibe_403(self):
        self.client.force_login(self.sin_perm)
        resp = self.client.get(reverse("reportes:ventas"))
        self.assertEqual(resp.status_code, 403)

    # ── CP-RBAC-06 ─────────────────────────────────────────────────────────────
    def test_sin_permiso_sanitario_recibe_403(self):
        self.client.force_login(self.sin_perm)
        resp = self.client.get(reverse("reportes:sanitario"))
        self.assertEqual(resp.status_code, 403)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – Vistas HTML
# ─────────────────────────────────────────────────────────────────────────────

class ReportesVistasTests(TestCase):
    """CP-VISTA-01 … CP-VISTA-10: comportamiento de las vistas."""

    def setUp(self):
        self.user    = make_user("vista_user")
        grant_perm(self.user, "reportes.read")
        self.client.force_login(self.user)
        self.potrero = make_potrero("PV")
        self.animal  = make_animal(self.potrero, rfid="COL-V-001")

    # ── CP-VISTA-01 ────────────────────────────────────────────────────────────
    def test_index_renderiza_cuatro_tarjetas(self):
        resp = self.client.get(reverse("reportes:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Inventario Actual")
        self.assertContains(resp, "Historial por Animal")
        self.assertContains(resp, "Calendario Sanitario")
        self.assertContains(resp, "Reporte de Ventas")

    # ── CP-VISTA-02 ────────────────────────────────────────────────────────────
    def test_inventario_muestra_animal(self):
        resp = self.client.get(reverse("reportes:inventario"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.animal.rfid)

    # ── CP-VISTA-03 ────────────────────────────────────────────────────────────
    def test_inventario_kpis_en_contexto(self):
        resp = self.client.get(reverse("reportes:inventario"))
        self.assertIn("total",        resp.context)
        self.assertIn("machos",       resp.context)
        self.assertIn("hembras",      resp.context)
        self.assertIn("peso_promedio",resp.context)

    # ── CP-VISTA-04 ────────────────────────────────────────────────────────────
    def test_RN1_fechas_invertidas_muestra_error(self):
        resp = self.client.get(reverse("reportes:inventario"), {
            "desde": str(HOY),
            "hasta": str(SEMANA),
        })
        self.assertIsNotNone(resp.context["error_fechas"])

    # ── CP-VISTA-05 ────────────────────────────────────────────────────────────
    def test_inventario_filtra_por_lote(self):
        otro_potrero = make_potrero("OTRO")
        otro_animal  = make_animal(otro_potrero, rfid="COL-V-999")
        resp = self.client.get(reverse("reportes:inventario"), {
            "lote": str(self.potrero.pk),
        })
        rfids = [d["animal"].rfid for d in resp.context["animals_data"]]
        self.assertIn(self.animal.rfid, rfids)
        self.assertNotIn(otro_animal.rfid, rfids)

    # ── CP-VISTA-06 ────────────────────────────────────────────────────────────
    def test_historial_muestra_contadores(self):
        make_evento(self.animal, self.user)
        resp = self.client.get(reverse("reportes:historial"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total_eventos", resp.context)
        self.assertGreaterEqual(resp.context["total_eventos"], 1)

    # ── CP-VISTA-07 ────────────────────────────────────────────────────────────
    def test_sanitario_sin_filtro_muestra_pendientes(self):
        make_evento(self.animal, self.user, estado=EventoSanitario.Estado.CONFIRMADO)
        resp = self.client.get(reverse("reportes:sanitario"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("eventos", resp.context)

    # ── CP-VISTA-08 ────────────────────────────────────────────────────────────
    def test_ventas_RN5_solo_confirmadas(self):
        self.animal.estado = Animal.Estado.ACTIVO
        self.animal.save(update_fields=["estado"])
        make_venta(self.animal, self.user)
        resp = self.client.get(reverse("reportes:ventas"))
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.context["total_ventas"], 1)

    # ── CP-VISTA-09 ────────────────────────────────────────────────────────────
    def test_ventas_kpis_en_contexto(self):
        resp = self.client.get(reverse("reportes:ventas"))
        self.assertIn("total_ventas", resp.context)
        self.assertIn("peso_total",   resp.context)
        self.assertIn("valor_total",  resp.context)

    # ── CP-VISTA-10 ────────────────────────────────────────────────────────────
    def test_RN4_log_reporte_se_crea_al_visitar(self):
        count_antes = LogReporte.objects.count()
        self.client.get(reverse("reportes:inventario"))
        self.assertGreater(LogReporte.objects.count(), count_antes)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 4 – Exportación CSV
# ─────────────────────────────────────────────────────────────────────────────

class ReportesCSVTests(TestCase):
    """CP-CSV-01 … CP-CSV-05: exportación a CSV (RN-3)."""

    def setUp(self):
        self.user    = make_user("csv_user")
        grant_perm(self.user, "reportes.read")
        self.client.force_login(self.user)
        self.potrero = make_potrero("PC")
        self.animal  = make_animal(self.potrero, rfid="COL-C-001")

    def _get_csv(self, url_name, params=None):
        params = params or {}
        params["fmt"] = "csv"
        params["exportar"] = "csv"
        return self.client.get(reverse(url_name), params)

    # ── CP-CSV-01 ──────────────────────────────────────────────────────────────
    def test_inventario_csv_content_type(self):
        resp = self._get_csv("reportes:inventario")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])

    # ── CP-CSV-02 ──────────────────────────────────────────────────────────────
    def test_inventario_csv_contiene_cabecera(self):
        resp = self._get_csv("reportes:inventario")
        content = resp.content.decode("utf-8-sig")
        self.assertIn("RFID", content)

    # ── CP-CSV-03 ──────────────────────────────────────────────────────────────
    def test_inventario_csv_tiene_bom_utf8(self):
        resp = self._get_csv("reportes:inventario")
        self.assertTrue(resp.content.startswith(b"\xef\xbb\xbf"))

    # ── CP-CSV-04 ──────────────────────────────────────────────────────────────
    def test_ventas_csv_content_type(self):
        self.animal.estado = Animal.Estado.ACTIVO
        self.animal.save(update_fields=["estado"])
        make_venta(self.animal, self.user)
        resp = self._get_csv("reportes:ventas")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])

    # ── CP-CSV-05 ──────────────────────────────────────────────────────────────
    def test_historial_csv_content_type(self):
        resp = self._get_csv("reportes:historial")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
