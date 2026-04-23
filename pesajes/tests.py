# pesajes/tests.py
"""
Pruebas funcionales – CU-004: Gestión de Pesajes
=================================================
Bloque 1 – Modelo y Reglas de Negocio  (CP-MODEL-01 … CP-MODEL-12)
Bloque 2 – RBAC y Control de Acceso    (CP-RBAC-01  … CP-RBAC-09)
Bloque 3 – Vistas                      (CP-VISTA-01 … CP-VISTA-14)

Correspondencia con los CP del documento CU-004:
  CP-01 → CP-VISTA-07  (pesaje válido → creado, variación calculada)
  CP-02 → CP-MODEL-01 + CP-VISTA-09  (peso inválido ≤ 0)
  CP-03 → CP-MODEL-05 + CP-VISTA-10  (fecha futura bloqueada)
  CP-04 → CP-MODEL-10  (fecha anterior al último → permite, variación correcta)
  CP-07 → CP-MODEL-08 + CP-MODEL-09  (cálculo variación y promedio diario)
"""

from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from authz.models import Permission, Role, RolePermission, UserRole
from animals.models import Animal, Potrero
from .models import Pesaje


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades compartidas
# ─────────────────────────────────────────────────────────────────────────────

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


def make_animal(potrero: Potrero, rfid: str = "COL-PES-001",
                estado: str = Animal.Estado.ACTIVO) -> Animal:
    return Animal.objects.create(
        rfid=rfid,
        nombre=f"AR-{rfid}",
        sexo=Animal.Sexo.MACHO,
        etapa=Animal.Etapa.LEVANTE,
        potrero=potrero,
        estado=estado,
    )


def make_pesaje(animal: Animal, user: User, peso_kg="250.00",
                fecha=None, **kwargs) -> Pesaje:
    """Crea un Pesaje válido con datos mínimos."""
    return Pesaje.objects.create(
        animal=animal,
        peso_kg=Decimal(peso_kg),
        fecha=fecha or date.today(),
        created_by=user,
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Modelo y Reglas de Negocio
# ─────────────────────────────────────────────────────────────────────────────

class PesajeModelRNTests(TestCase):
    """
    Valida las reglas de negocio en Pesaje.clean() y Pesaje.save():
    RN-1 (peso > 0), RN-2 (solo ACTIVO), RN-3 (inmutabilidad),
    RN-6 (cálculo automático de variación) y validación de fecha futura.
    """

    def setUp(self):
        self.potrero = make_potrero("P1")
        self.user = make_user("operario")
        self.animal = make_animal(self.potrero, rfid="COL-ACT-001",
                                  estado=Animal.Estado.ACTIVO)
        self.animal_borrador = make_animal(self.potrero, rfid="COL-BOR-001",
                                           estado=Animal.Estado.BORRADOR)
        self.animal_inactivo = make_animal(self.potrero, rfid="COL-INA-001",
                                           estado=Animal.Estado.INACTIVO)

    # ── CP-MODEL-01 ──────────────────────────────────────────────────────────
    def test_rn1_peso_cero_lanza_error(self):
        """RN-1: peso_kg == 0 → ValidationError campo 'peso_kg'. (CP-02)"""
        p = Pesaje(animal=self.animal, peso_kg=Decimal("0.00"),
                   fecha=date.today(), created_by=self.user)
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("peso_kg", ctx.exception.message_dict)

    # ── CP-MODEL-02 ──────────────────────────────────────────────────────────
    def test_rn1_peso_negativo_lanza_error(self):
        """RN-1: peso_kg < 0 → ValidationError campo 'peso_kg'."""
        p = Pesaje(animal=self.animal, peso_kg=Decimal("-10.00"),
                   fecha=date.today(), created_by=self.user)
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("peso_kg", ctx.exception.message_dict)

    # ── CP-MODEL-03 ──────────────────────────────────────────────────────────
    def test_rn1_peso_valido_permitido(self):
        """RN-1: peso_kg > 0 → se guarda sin error."""
        p = Pesaje(animal=self.animal, peso_kg=Decimal("254.50"),
                   fecha=date.today(), created_by=self.user)
        p.full_clean()  # no debe lanzar error
        p.save()
        self.assertEqual(Pesaje.objects.filter(pk=p.pk).count(), 1)

    # ── CP-MODEL-04 ──────────────────────────────────────────────────────────
    def test_rn2_animal_inactivo_lanza_error(self):
        """RN-2: animal INACTIVO → ValidationError campo 'animal'."""
        p = Pesaje(animal=self.animal_inactivo, peso_kg=Decimal("200.00"),
                   fecha=date.today(), created_by=self.user)
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("animal", ctx.exception.message_dict)

    # ── CP-MODEL-05 ──────────────────────────────────────────────────────────
    def test_rn2_animal_borrador_lanza_error(self):
        """RN-2: animal BORRADOR → ValidationError campo 'animal'."""
        p = Pesaje(animal=self.animal_borrador, peso_kg=Decimal("200.00"),
                   fecha=date.today(), created_by=self.user)
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("animal", ctx.exception.message_dict)

    # ── CP-MODEL-06 ──────────────────────────────────────────────────────────
    def test_rn2_animal_activo_permitido(self):
        """RN-2: animal ACTIVO → se guarda sin error."""
        p = Pesaje(animal=self.animal, peso_kg=Decimal("200.00"),
                   fecha=date.today(), created_by=self.user)
        p.full_clean()
        p.save()
        self.assertTrue(Pesaje.objects.filter(pk=p.pk).exists())

    # ── CP-MODEL-07 ──────────────────────────────────────────────────────────
    def test_rn3_inmutabilidad_impide_update(self):
        """RN-3: llamar save() sobre un pesaje ya guardado → ValueError."""
        p = make_pesaje(self.animal, self.user)
        with self.assertRaises(ValueError) as ctx:
            p.save()
        self.assertIn("RN-3", str(ctx.exception))

    # ── CP-MODEL-08 ──────────────────────────────────────────────────────────
    def test_rn6_primer_pesaje_variacion_es_none(self):
        """RN-6: primer pesaje del animal → variacion_kg y promedio_diario_g son None."""
        p = make_pesaje(self.animal, self.user, peso_kg="250.00",
                        fecha=date.today() - timedelta(days=10))
        self.assertIsNone(p.variacion_kg)
        self.assertIsNone(p.promedio_diario_g)

    # ── CP-MODEL-09 ──────────────────────────────────────────────────────────
    def test_rn6_segundo_pesaje_calcula_variacion(self):
        """RN-6: segundo pesaje → variacion_kg y promedio_diario_g calculados. (CP-07)"""
        fecha_1 = date.today() - timedelta(days=30)
        fecha_2 = date.today()
        make_pesaje(self.animal, self.user, peso_kg="237.00", fecha=fecha_1)
        p2 = make_pesaje(self.animal, self.user, peso_kg="254.50", fecha=fecha_2)

        # variacion = 254.50 - 237.00 = 17.50 kg
        self.assertEqual(p2.variacion_kg, Decimal("17.50"))
        # promedio = 17500 g / 30 días = 583.3 g/día
        self.assertIsNotNone(p2.promedio_diario_g)
        self.assertAlmostEqual(float(p2.promedio_diario_g), 583.3, delta=1.0)

    # ── CP-MODEL-10 ──────────────────────────────────────────────────────────
    def test_fecha_anterior_al_ultimo_pesaje_permite_con_variacion(self):
        """Fecha anterior al último pesaje → permitido; variación calculada vs su anterior. (CP-04)"""
        fecha_antigua = date.today() - timedelta(days=60)
        fecha_media = date.today() - timedelta(days=30)
        fecha_reciente = date.today()

        make_pesaje(self.animal, self.user, peso_kg="200.00", fecha=fecha_antigua)
        make_pesaje(self.animal, self.user, peso_kg="250.00", fecha=fecha_reciente)
        # Pesaje con fecha intermedia: no debe lanzar error
        p_medio = make_pesaje(self.animal, self.user, peso_kg="225.00", fecha=fecha_media)
        # variacion respecto a fecha_antigua (200.00) = +25.00
        self.assertEqual(p_medio.variacion_kg, Decimal("25.00"))

    # ── CP-MODEL-11 ──────────────────────────────────────────────────────────
    def test_fecha_futura_lanza_error(self):
        """Fecha futura → ValidationError campo 'fecha'. (CP-03)"""
        p = Pesaje(animal=self.animal, peso_kg=Decimal("250.00"),
                   fecha=date.today() + timedelta(days=1), created_by=self.user)
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("fecha", ctx.exception.message_dict)

    # ── CP-MODEL-12 ──────────────────────────────────────────────────────────
    def test_str_muestra_peso_y_fecha(self):
        """__str__ retorna '{peso_kg} kg · {fecha:%Y-%m-%d}'."""
        p = make_pesaje(self.animal, self.user, peso_kg="254.50")
        self.assertIn("254.50", str(p))
        self.assertIn(str(date.today().year), str(p))


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – RBAC y Control de Acceso
# ─────────────────────────────────────────────────────────────────────────────

class PesajeRBACTests(TestCase):
    """
    Valida que @login_required + @require_perm restringen el acceso
    según los permisos pesajes.read y pesajes.write.
    """

    def setUp(self):
        self.potrero = make_potrero("P-RBAC")
        self.admin = make_user("admin_rbac")
        self.animal = make_animal(self.potrero, rfid="COL-RBAC-001")
        self.pesaje = make_pesaje(self.animal, self.admin)

        self.user_read = make_user("user_read")
        grant_perm(self.user_read, "pesajes.read")

        self.user_write = make_user("user_write")
        grant_perm(self.user_write, "pesajes.read")
        grant_perm(self.user_write, "pesajes.write")

        self.user_sin = make_user("user_sin")

    # ── CP-RBAC-01 ───────────────────────────────────────────────────────────
    def test_list_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("pesajes:list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-02 ───────────────────────────────────────────────────────────
    def test_detail_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("pesajes:detail", args=[self.pesaje.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-03 ───────────────────────────────────────────────────────────
    def test_create_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("pesajes:create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-04 ───────────────────────────────────────────────────────────
    def test_list_sin_permiso_read_retorna_403(self):
        self.client.login(username="user_sin", password="testpass123")
        self.assertEqual(self.client.get(reverse("pesajes:list")).status_code, 403)

    # ── CP-RBAC-05 ───────────────────────────────────────────────────────────
    def test_detail_sin_permiso_read_retorna_403(self):
        self.client.login(username="user_sin", password="testpass123")
        self.assertEqual(
            self.client.get(reverse("pesajes:detail", args=[self.pesaje.pk])).status_code, 403
        )

    # ── CP-RBAC-06 ───────────────────────────────────────────────────────────
    def test_create_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        self.assertEqual(self.client.get(reverse("pesajes:create")).status_code, 403)

    # ── CP-RBAC-07 ───────────────────────────────────────────────────────────
    def test_solo_read_puede_listar_y_ver_pero_no_crear(self):
        self.client.login(username="user_read", password="testpass123")
        self.assertEqual(self.client.get(reverse("pesajes:list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("pesajes:detail", args=[self.pesaje.pk])).status_code, 200
        )
        self.assertEqual(self.client.get(reverse("pesajes:create")).status_code, 403)

    # ── CP-RBAC-08 ───────────────────────────────────────────────────────────
    def test_write_puede_acceder_a_create(self):
        self.client.login(username="user_write", password="testpass123")
        self.assertEqual(self.client.get(reverse("pesajes:create")).status_code, 200)

    # ── CP-RBAC-09 ───────────────────────────────────────────────────────────
    def test_write_puede_acceder_a_create_con_animal(self):
        self.client.login(username="user_write", password="testpass123")
        r = self.client.get(
            reverse("pesajes:create") + f"?animal={self.animal.pk}"
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.context.get("animal_obj"))


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – Vistas (comportamiento funcional)
# ─────────────────────────────────────────────────────────────────────────────

class PesajeVistaTests(TestCase):
    """
    Prueba el comportamiento funcional de todas las vistas del módulo
    de pesajes: listado, filtros, creación, detalle y cálculo de variación.
    """

    def setUp(self):
        self.potrero = make_potrero("P1")
        self.potrero2 = make_potrero("P2")

        self.user = make_user("operario")
        grant_perm(self.user, "pesajes.read")
        grant_perm(self.user, "pesajes.write")
        self.client.login(username="operario", password="testpass123")

        self.animal = make_animal(self.potrero, rfid="COL-VIS-001")
        self.animal2 = make_animal(self.potrero2, rfid="COL-VIS-002")
        self.animal_borrador = make_animal(
            self.potrero, rfid="COL-VIS-BOR", estado=Animal.Estado.BORRADOR
        )

        # Pesaje de referencia
        self.pesaje = make_pesaje(
            self.animal, self.user,
            peso_kg="237.00",
            fecha=date.today() - timedelta(days=30),
            responsable="operario01",
        )

    def _post_create(self, **overrides):
        """Helper: POST válido a pesaje_create."""
        data = {
            "animal": self.animal.pk,
            "fecha": str(date.today()),
            "peso_kg": "254.50",
            "responsable": "operario01",
            "observaciones": "",
        }
        data.update(overrides)
        return self.client.post(reverse("pesajes:create"), data)

    # ── CP-VISTA-01 ──────────────────────────────────────────────────────────
    def test_list_sin_filtros_retorna_200(self):
        """GET /pesajes/ → 200, pesaje de referencia aparece en page_obj."""
        r = self.client.get(reverse("pesajes:list"))
        self.assertEqual(r.status_code, 200)
        pks = [p.pk for p in r.context["page_obj"].object_list]
        self.assertIn(self.pesaje.pk, pks)

    # ── CP-VISTA-02 ──────────────────────────────────────────────────────────
    def test_list_filtro_q_por_responsable(self):
        """GET ?q=operario01 → solo retorna pesajes con ese responsable."""
        make_pesaje(self.animal2, self.user, peso_kg="180.00",
                    responsable="otro_operario")
        r = self.client.get(reverse("pesajes:list") + "?q=operario01")
        self.assertEqual(r.status_code, 200)
        for p in r.context["page_obj"].object_list:
            self.assertIn("operario01", (p.responsable or ""))

    # ── CP-VISTA-03 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_animal(self):
        """GET ?animal=<pk> → solo retorna pesajes de ese animal."""
        make_pesaje(self.animal2, self.user, peso_kg="180.00")
        r = self.client.get(reverse("pesajes:list") + f"?animal={self.animal.pk}")
        self.assertEqual(r.status_code, 200)
        for p in r.context["page_obj"].object_list:
            self.assertEqual(p.animal_id, self.animal.pk)

    # ── CP-VISTA-04 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_fecha_desde(self):
        """GET ?fecha_desde=<hoy> → solo retorna pesajes de hoy en adelante."""
        r = self.client.get(
            reverse("pesajes:list") + f"?fecha_desde={date.today()}"
        )
        self.assertEqual(r.status_code, 200)
        for p in r.context["page_obj"].object_list:
            self.assertGreaterEqual(p.fecha, date.today())

    # ── CP-VISTA-05 ──────────────────────────────────────────────────────────
    def test_create_get_sin_animal_retorna_formulario_vacio(self):
        """GET /pesajes/new/ sin ?animal= → 200, animal_obj=None. (CP-EV-03 análogo)"""
        r = self.client.get(reverse("pesajes:create"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)
        self.assertIsNone(r.context.get("animal_obj"))

    # ── CP-VISTA-06 ──────────────────────────────────────────────────────────
    def test_create_get_con_animal_activo_precarga_contexto(self):
        """GET /pesajes/new/?animal=<pk> (ACTIVO) → animal_obj en contexto + ultimo_pesaje."""
        r = self.client.get(
            reverse("pesajes:create") + f"?animal={self.animal.pk}"
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.context.get("animal_obj"))
        self.assertEqual(r.context["animal_obj"].pk, self.animal.pk)
        # ultimo_pesaje debe ser el pesaje de referencia
        self.assertIsNotNone(r.context.get("ultimo_pesaje"))

    # ── CP-VISTA-07 ──────────────────────────────────────────────────────────
    def test_create_get_con_animal_borrador_retorna_404(self):
        """GET /pesajes/new/?animal=<pk_BORRADOR> → 404 (get_object_or_404 filtra ACTIVO)."""
        r = self.client.get(
            reverse("pesajes:create") + f"?animal={self.animal_borrador.pk}"
        )
        self.assertEqual(r.status_code, 404)

    # ── CP-VISTA-08 ──────────────────────────────────────────────────────────
    def test_create_post_valido_crea_pesaje_con_variacion(self):
        """POST válido → pesaje creado, variación calculada, redirige a detail. (CP-01)"""
        count_antes = Pesaje.objects.count()
        r = self._post_create(peso_kg="254.50")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Pesaje.objects.count(), count_antes + 1)
        nuevo = Pesaje.objects.latest("created_at")
        self.assertEqual(nuevo.peso_kg, Decimal("254.50"))
        self.assertEqual(nuevo.created_by, self.user)
        # Variación respecto al pesaje anterior (237.00) = +17.50
        self.assertEqual(nuevo.variacion_kg, Decimal("17.50"))
        self.assertRedirects(r, reverse("pesajes:detail", args=[nuevo.pk]))

    # ── CP-VISTA-09 ──────────────────────────────────────────────────────────
    def test_create_post_peso_cero_re_renderiza(self):
        """POST con peso_kg=0 → re-renderiza 200, sin pesaje creado. (CP-02)"""
        count_antes = Pesaje.objects.count()
        r = self._post_create(peso_kg="0")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Pesaje.objects.count(), count_antes)

    # ── CP-VISTA-10 ──────────────────────────────────────────────────────────
    def test_create_post_fecha_futura_re_renderiza(self):
        """POST con fecha futura → re-renderiza 200, sin pesaje creado. (CP-03)"""
        count_antes = Pesaje.objects.count()
        fecha_futura = str(date.today() + timedelta(days=1))
        r = self._post_create(fecha=fecha_futura)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Pesaje.objects.count(), count_antes)

    # ── CP-VISTA-11 ──────────────────────────────────────────────────────────
    def test_create_post_animal_borrador_re_renderiza(self):
        """POST con animal BORRADOR → form rechaza (queryset solo ACTIVO), re-renderiza."""
        count_antes = Pesaje.objects.count()
        r = self._post_create(animal=self.animal_borrador.pk)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Pesaje.objects.count(), count_antes)

    # ── CP-VISTA-12 ──────────────────────────────────────────────────────────
    def test_create_post_peso_negativo_re_renderiza(self):
        """POST con peso_kg negativo → re-renderiza 200, sin pesaje creado."""
        count_antes = Pesaje.objects.count()
        r = self._post_create(peso_kg="-50")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Pesaje.objects.count(), count_antes)

    # ── CP-VISTA-13 ──────────────────────────────────────────────────────────
    def test_detail_retorna_datos_del_pesaje(self):
        """GET /pesajes/<pk>/ → 200, pesaje en contexto con anterior."""
        r = self.client.get(reverse("pesajes:detail", args=[self.pesaje.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["pesaje"].pk, self.pesaje.pk)
        self.assertIn("anterior", r.context)

    # ── CP-VISTA-14 ──────────────────────────────────────────────────────────
    def test_detail_primer_pesaje_anterior_es_none(self):
        """GET detail del primer (y único) pesaje → anterior es None."""
        r = self.client.get(reverse("pesajes:detail", args=[self.pesaje.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["anterior"])