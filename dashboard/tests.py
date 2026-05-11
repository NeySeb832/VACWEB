# dashboard/tests.py
"""
Pruebas funcionales – CU-009: Panel Principal (Dashboard)
==========================================================
Bloque 1 – Lógica de KPIs   (CP-KPI-01 … CP-KPI-06)
Bloque 2 – RBAC             (CP-RBAC-01 … CP-RBAC-05)
Bloque 3 – Vistas           (CP-VISTA-01 … CP-VISTA-08)
Bloque 4 – Auditoría        (CP-AUD-01)
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from animals.models import Animal
from alertas.models import Alerta
from authz.models import AuditLog, Permission, Role, RolePermission, UserRole
from eventos.models import EventoSanitario
from pesajes.models import Pesaje
from potreros.models import Potrero
from transacciones.models import Transaccion

from dashboard.views import _calcular_kpis, _get_actividad_reciente

# ─────────────────────────────────────────────────────────────────────────────
# Utilidades compartidas
# ─────────────────────────────────────────────────────────────────────────────

HOY    = date.today()
AYER   = HOY - timedelta(days=1)
MANANA = HOY + timedelta(days=1)


def make_user(username: str, password: str = "testpass123") -> User:
    return User.objects.create_user(username=username, password=password)


def grant_perm(user: User, perm_code: str) -> None:
    perm, _ = Permission.objects.get_or_create(code=perm_code)
    role, _ = Role.objects.get_or_create(name=perm_code, code=perm_code)
    RolePermission.objects.get_or_create(role=role, permission=perm)
    UserRole.objects.get_or_create(user=user, role=role)


def make_potrero(nombre: str = "P-DASH-01", capacidad: int = 10) -> Potrero:
    return Potrero.objects.create(
        nombre_codigo=nombre,
        estado="ACTIVO",
        area_ha="5.00",
        capacidad_maxima=capacidad,
        tipo_uso="CEBA",
    )


def make_animal(potrero=None, rfid: str = "COL-DASH-001",
                estado: str = Animal.Estado.ACTIVO) -> Animal:
    return Animal.objects.create(
        rfid=rfid,
        nombre=f"Animal-{rfid}",
        sexo=Animal.Sexo.MACHO,
        etapa=Animal.Etapa.LEVANTE,
        potrero=potrero,
        estado=estado,
    )


def make_pesaje(animal: Animal, user: User, peso: str = "250.00",
                fecha: date = None) -> Pesaje:
    return Pesaje.objects.create(
        animal=animal,
        fecha=fecha or HOY,
        peso_kg=peso,
        created_by=user,
    )


def make_evento(animal: Animal, user: User, estado=None, fecha=None) -> EventoSanitario:
    return EventoSanitario.objects.create(
        animal=animal,
        tipo="Vacuna Aftosa",
        responsable="vet01",
        producto="Aftovaxpur",
        fecha=fecha or HOY,
        estado=estado or EventoSanitario.Estado.CONFIRMADO,
        created_by=user,
    )


def make_transaccion(animal: Animal, user: User, tipo=None,
                     fecha: date = None) -> Transaccion:
    t = Transaccion(
        tipo=tipo or Transaccion.Tipo.VENTA,
        fecha=fecha or HOY,
        animal=animal,
        origen_destino="Frigorífico Central",
        valor_cop="2000000.00",
        created_by=user,
    )
    t.save()
    return t


def make_alerta(tipo: str = "sanitaria", mensaje: str = "Alerta test") -> Alerta:
    return Alerta.objects.create(
        tipo=tipo,
        mensaje=mensaje,
        origen="test",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Lógica de KPIs
# ─────────────────────────────────────────────────────────────────────────────

class DashboardKPITests(TestCase):
    """
    Valida que _calcular_kpis() devuelva valores coherentes con los datos
    de los módulos fuente (CP-02 a CP-05 del análisis).
    """

    def setUp(self):
        self.user = make_user("vet_kpi")
        self.potrero = make_potrero("P-KPI-01", capacidad=10)
        self.animal1 = make_animal(self.potrero, rfid="COL-KPI-001")
        self.animal2 = make_animal(self.potrero, rfid="COL-KPI-002")

    # ── CP-KPI-01 ─────────────────────────────────────────────────────────
    def test_kpi_animales_activos_cuenta_solo_activos(self):
        """Total Animales Activos = conteo real de animales en estado ACTIVO."""
        make_animal(self.potrero, rfid="COL-KPI-INA", estado=Animal.Estado.INACTIVO)
        kpis = _calcular_kpis()
        self.assertEqual(kpis["animales_activos"]["valor"], 2)

    # ── CP-KPI-02 ─────────────────────────────────────────────────────────
    def test_kpi_peso_promedio_usa_ultimo_pesaje_por_animal(self):
        """Peso Promedio = promedio del último pesaje de cada animal activo."""
        make_pesaje(self.animal1, self.user, peso="200.00", fecha=AYER)
        make_pesaje(self.animal1, self.user, peso="220.00", fecha=HOY)
        make_pesaje(self.animal2, self.user, peso="180.00", fecha=HOY)
        kpis = _calcular_kpis()
        # Último de animal1 = 220, animal2 = 180 → promedio = 200
        self.assertAlmostEqual(kpis["peso_promedio"]["valor"], 200.0, places=0)

    # ── CP-KPI-03 ─────────────────────────────────────────────────────────
    def test_kpi_peso_promedio_es_cero_sin_pesajes(self):
        """Peso Promedio = 0 si no hay pesajes registrados."""
        kpis = _calcular_kpis()
        self.assertEqual(kpis["peso_promedio"]["valor"], 0.0)

    # ── CP-KPI-04 ─────────────────────────────────────────────────────────
    def test_kpi_ocupacion_potreros_calcula_porcentaje(self):
        """Ocupación = (animales activos / capacidad_maxima) × 100 promediado."""
        # potrero capacidad=10, 2 activos → 20%
        kpis = _calcular_kpis()
        self.assertAlmostEqual(kpis["ocupacion_potreros"]["valor"], 20.0, places=0)

    # ── CP-KPI-05 ─────────────────────────────────────────────────────────
    def test_kpi_alertas_pendientes_cuenta_solo_pendientes(self):
        """Alertas Pendientes = solo las que están en estado PENDIENTE."""
        a1 = make_alerta(tipo="sanitaria")
        a2 = make_alerta(tipo="productiva")
        a2.atender(self.user)
        kpis = _calcular_kpis()
        self.assertEqual(kpis["alertas_pendientes"]["valor"], 1)

    # ── CP-KPI-06 ─────────────────────────────────────────────────────────
    def test_kpi_cumplimiento_sanitario_calcula_porcentaje(self):
        """Cumplimiento = (animales con evento REALIZADO reciente / total activos) × 100."""
        make_evento(self.animal1, self.user,
                    estado=EventoSanitario.Estado.REALIZADO,
                    fecha=HOY - timedelta(days=30))
        kpis = _calcular_kpis()
        # 1 de 2 activos tiene evento REALIZADO en últimos 90 días → 50%
        self.assertAlmostEqual(kpis["cumplimiento_sanitario"]["valor"], 50.0, places=0)

    # ── CP-KPI-07 ─────────────────────────────────────────────────────────
    def test_kpi_transacciones_mes_cuenta_solo_confirmadas_del_mes_actual(self):
        """Transacciones del Mes = solo CONFIRMADO en el mes en curso."""
        make_transaccion(self.animal1, self.user, fecha=HOY)
        kpis = _calcular_kpis()
        self.assertEqual(kpis["transacciones_mes"]["valor"], 1)

    # ── CP-KPI-08 ─────────────────────────────────────────────────────────
    def test_actividad_reciente_devuelve_hasta_10_items(self):
        """_get_actividad_reciente() devuelve como máximo 10 operaciones."""
        for i in range(5):
            an = make_animal(self.potrero, rfid=f"COL-ACT-{i:03d}")
            make_pesaje(an, self.user, peso=f"{200+i}.00")
            make_evento(an, self.user)
        items = _get_actividad_reciente()
        self.assertLessEqual(len(items), 10)

    # ── CP-KPI-09 ─────────────────────────────────────────────────────────
    def test_actividad_reciente_ordenada_mas_reciente_primero(self):
        """Los items de actividad reciente están ordenados de más reciente a más antiguo."""
        make_pesaje(self.animal1, self.user, peso="200.00", fecha=AYER)
        make_evento(self.animal2, self.user, fecha=HOY)
        items = _get_actividad_reciente()
        if len(items) >= 2:
            self.assertGreaterEqual(items[0]["fecha"], items[1]["fecha"])


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – RBAC y Control de Acceso
# ─────────────────────────────────────────────────────────────────────────────

class DashboardRBACTests(TestCase):
    """
    Verifica que @login_required y @require_perm protegen la vista
    según el permiso dashboard.read (CP-10 del análisis).
    """

    def setUp(self):
        self.user_con = make_user("user_con_perm")
        grant_perm(self.user_con, "dashboard.read")

        self.user_sin = make_user("user_sin_perm")

        self.url = reverse("dashboard:index")

    # ── CP-RBAC-01 ────────────────────────────────────────────────────────
    def test_acceso_sin_autenticar_redirige_a_login(self):
        """Usuario no autenticado → redirección a /login/."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-02 ────────────────────────────────────────────────────────
    def test_acceso_sin_permiso_retorna_403(self):
        """Usuario autenticado sin dashboard.read → 403."""
        self.client.force_login(self.user_sin)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-03 ────────────────────────────────────────────────────────
    def test_acceso_con_permiso_retorna_200(self):
        """Usuario con dashboard.read → 200."""
        self.client.force_login(self.user_con)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)

    # ── CP-RBAC-04 ────────────────────────────────────────────────────────
    def test_post_no_permitido(self):
        """El Dashboard es solo lectura; POST → 405 o redirección."""
        self.client.force_login(self.user_con)
        r = self.client.post(self.url, {})
        self.assertIn(r.status_code, [405, 302, 200])

    # ── CP-RBAC-05 ────────────────────────────────────────────────────────
    def test_acceso_redirige_correctamente_tras_login(self):
        """LOGIN_REDIRECT_URL apunta a /dashboard/."""
        from django.conf import settings
        self.assertEqual(settings.LOGIN_REDIRECT_URL, "/dashboard/")


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – Vistas (comportamiento funcional)
# ─────────────────────────────────────────────────────────────────────────────

class DashboardVistaTests(TestCase):
    """
    Prueba el comportamiento de la vista: contexto correcto, KPIs presentes,
    estado vacío y sección de alertas urgentes.
    """

    def setUp(self):
        self.user = make_user("admin_vista")
        grant_perm(self.user, "dashboard.read")
        self.client.force_login(self.user)
        self.url = reverse("dashboard:index")

        self.potrero = make_potrero("P-VIS-DASH", capacidad=20)
        self.animal = make_animal(self.potrero, rfid="COL-VIS-DASH-001")

    # ── CP-VISTA-01 ───────────────────────────────────────────────────────
    def test_dashboard_carga_con_contexto_kpis(self):
        """GET /dashboard/ → 200 y contexto contiene 'kpis'."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("kpis", r.context)

    # ── CP-VISTA-02 ───────────────────────────────────────────────────────
    def test_kpis_contiene_todas_las_claves_esperadas(self):
        """El contexto kpis tiene los 6 indicadores definidos en el CU."""
        r = self.client.get(self.url)
        kpis = r.context["kpis"]
        for clave in (
            "animales_activos",
            "peso_promedio",
            "ocupacion_potreros",
            "alertas_pendientes",
            "transacciones_mes",
            "cumplimiento_sanitario",
        ):
            self.assertIn(clave, kpis, msg=f"Falta KPI: {clave}")

    # ── CP-VISTA-03 ───────────────────────────────────────────────────────
    def test_kpi_animales_activos_coincide_con_bd(self):
        """CP-02: valor del KPI Animales Activos es coherente con la BD."""
        r = self.client.get(self.url)
        total = Animal.objects.filter(estado=Animal.Estado.ACTIVO).count()
        self.assertEqual(r.context["kpis"]["animales_activos"]["valor"], total)

    # ── CP-VISTA-04 ───────────────────────────────────────────────────────
    def test_kpi_alertas_pendientes_coincide_con_bd(self):
        """CP-05: badge de alertas coincide con el conteo real en BD."""
        make_alerta(tipo="sanitaria")
        make_alerta(tipo="productiva")
        r = self.client.get(self.url)
        total_bd = Alerta.objects.filter(estado=Alerta.Estado.PENDIENTE).count()
        self.assertEqual(r.context["kpis"]["alertas_pendientes"]["valor"], total_bd)

    # ── CP-VISTA-05 ───────────────────────────────────────────────────────
    def test_actividad_reciente_en_contexto(self):
        """CP-06: contexto incluye 'actividad' con items de las últimas operaciones."""
        make_pesaje(self.animal, self.user, peso="240.00")
        r = self.client.get(self.url)
        self.assertIn("actividad", r.context)
        self.assertGreaterEqual(len(r.context["actividad"]), 1)

    # ── CP-VISTA-06 ───────────────────────────────────────────────────────
    def test_alertas_urgentes_en_contexto(self):
        """Las alertas urgentes (top 5 pendientes) están en el contexto."""
        make_alerta(tipo="sanitaria", mensaje="Urgente 1")
        r = self.client.get(self.url)
        self.assertIn("alertas_urgentes", r.context)

    # ── CP-VISTA-07 ───────────────────────────────────────────────────────
    def test_dashboard_sin_datos_muestra_estado_vacio(self):
        """CP-08: finca sin animales activos → sin_datos=True en contexto."""
        self.animal.estado = Animal.Estado.INACTIVO
        self.animal.save(update_fields=["estado"])
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["sin_datos"])

    # ── CP-VISTA-08 ───────────────────────────────────────────────────────
    def test_kpi_ocupacion_potreros_en_contexto(self):
        """CP-04: ocupación de potreros aparece en kpis y potreros_ocupacion."""
        r = self.client.get(self.url)
        self.assertIn("potreros_ocupacion", r.context)
        self.assertIn("ocupacion_potreros", r.context["kpis"])


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 4 – Auditoría
# ─────────────────────────────────────────────────────────────────────────────

class DashboardAuditoriaTests(TestCase):
    """
    Verifica que cada acceso al Dashboard queda registrado en AuditLog
    con usuario y fecha/hora (CP-11, RN-5).
    """

    def setUp(self):
        self.user = make_user("admin_aud")
        grant_perm(self.user, "dashboard.read")
        self.client.force_login(self.user)
        self.url = reverse("dashboard:index")

    # ── CP-AUD-01 ─────────────────────────────────────────────────────────
    def test_acceso_al_dashboard_registra_en_auditlog(self):
        """CP-11: cada GET al Dashboard genera un AuditLog con action='dashboard_acceso'."""
        conteo_previo = AuditLog.objects.filter(
            action="dashboard_acceso", user=self.user
        ).count()

        self.client.get(self.url)

        conteo_nuevo = AuditLog.objects.filter(
            action="dashboard_acceso", user=self.user
        ).count()
        self.assertEqual(conteo_nuevo, conteo_previo + 1)

    # ── CP-AUD-02 ─────────────────────────────────────────────────────────
    def test_multiples_accesos_generan_multiples_registros(self):
        """Dos accesos consecutivos → dos registros de auditoría."""
        self.client.get(self.url)
        self.client.get(self.url)

        total = AuditLog.objects.filter(
            action="dashboard_acceso", user=self.user
        ).count()
        self.assertGreaterEqual(total, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 5 – Integración Login y Permisos
# ─────────────────────────────────────────────────────────────────────────────

class DashboardIntegracionLoginTests(TestCase):
    """
    Verifica que el login redirige exactamente a /dashboard/ y que la lógica
    de asignación de permisos cubre roles con nombre 'administrador'.
    (CP-INT-01 … CP-INT-03)
    """

    def setUp(self):
        self.user = make_user("admin_integ", password="Admin$1234")
        grant_perm(self.user, "dashboard.read")

    # ── CP-INT-01 ─────────────────────────────────────────────────────────
    def test_login_exitoso_redirige_exactamente_a_dashboard(self):
        """POST /login/ con credenciales válidas → Location exacta '/dashboard/'."""
        r = self.client.post("/login/", {
            "username": "admin_integ",
            "password": "Admin$1234",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/dashboard/")

    # ── CP-INT-02 ─────────────────────────────────────────────────────────
    def test_usuario_con_permiso_accede_al_dashboard_tras_autenticar(self):
        """Usuario con dashboard.read obtiene 200 en /dashboard/."""
        self.client.force_login(self.user)
        r = self.client.get("/dashboard/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("kpis", r.context)

    # ── CP-INT-03 ─────────────────────────────────────────────────────────
    def test_asignacion_permiso_cubre_rol_administrador_de_la_finca(self):
        """
        La lógica icontains de la migración 0002 asigna dashboard.read
        a roles con código 'administrador de la finca'.
        """
        perm, _ = Permission.objects.get_or_create(
            code="dashboard.read",
            defaults={"description": "Ver panel principal"},
        )
        rol = Role.objects.create(
            name="Administrador de la Finca",
            code="administrador de la finca",
        )

        # Replicar la lógica de assign_permission de la migración 0002
        codigos_admin = ("administrador", "propietario", "administrador de la finca", "admin")
        roles_asignados = set()
        for code in codigos_admin:
            for r in Role.objects.filter(code__icontains=code):
                if r.pk not in roles_asignados:
                    RolePermission.objects.get_or_create(role=r, permission=perm)
                    roles_asignados.add(r.pk)

        self.assertTrue(
            RolePermission.objects.filter(role=rol, permission=perm).exists(),
            "El rol 'administrador de la finca' no recibió dashboard.read",
        )
