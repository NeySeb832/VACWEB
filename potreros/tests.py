# potreros/tests.py
"""
Pruebas funcionales – CU-005: Gestión de Potreros/Lotes
=========================================================
Bloque 1 – Modelo y Reglas de Negocio  (CP-MODEL-01 … CP-MODEL-09)
Bloque 2 – RBAC y Control de Acceso    (CP-RBAC-01  … CP-RBAC-10)
Bloque 3 – Vistas                      (CP-VISTA-01 … CP-VISTA-20)
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from authz.models import Permission, Role, RolePermission, UserRole
from animals.models import Animal
from .forms import PotreroForm
from .models import Potrero


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


def make_potrero(nombre: str = "P-TEST", **kwargs) -> Potrero:
    defaults = {
        "nombre_codigo":   nombre,
        "area_ha":         "10.00",
        "capacidad_maxima": 20,
        "tipo_uso":        Potrero.TipoUso.CEBA,
        "estado":          Potrero.Estado.ACTIVO,
    }
    defaults.update(kwargs)
    return Potrero.objects.create(**defaults)


def make_animal(potrero: Potrero, rfid: str = "COL-POT-001",
                estado: str = Animal.Estado.ACTIVO) -> Animal:
    return Animal.objects.create(
        rfid=rfid,
        nombre=f"AR-{rfid}",
        sexo=Animal.Sexo.MACHO,
        etapa=Animal.Etapa.LEVANTE,
        potrero=potrero,
        estado=estado,
    )


def _post_json(client, url: str, data: dict):
    """Helper: POST de formulario y parsea respuesta JSON."""
    r = client.post(url, data)
    return r, json.loads(r.content)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Modelo y Reglas de Negocio
# ─────────────────────────────────────────────────────────────────────────────

class PotreroModelTests(TestCase):
    """
    Valida el modelo Potrero: campos, constraint de unicidad,
    helpers de ocupación y valores por defecto.
    """

    def setUp(self):
        self.potrero = make_potrero("Potrero Norte", capacidad_maxima=10)

    # ── CP-MODEL-01 ──────────────────────────────────────────────────────────
    def test_str_retorna_nombre_codigo(self):
        """__str__ debe retornar nombre_codigo."""
        self.assertEqual(str(self.potrero), "Potrero Norte")

    # ── CP-MODEL-02 ──────────────────────────────────────────────────────────
    def test_estado_por_defecto_es_activo(self):
        """El estado por defecto de un potrero nuevo es ACTIVO."""
        p = Potrero(
            nombre_codigo="NuevoP",
            area_ha="5.00",
            capacidad_maxima=10,
            tipo_uso=Potrero.TipoUso.LEVANTE,
        )
        self.assertEqual(p.estado, Potrero.Estado.ACTIVO)

    # ── CP-MODEL-03 ──────────────────────────────────────────────────────────
    def test_unique_constraint_en_meta(self):
        """Potrero._meta.constraints debe incluir unique_nombre_codigo_potrero."""
        nombres = [c.name for c in Potrero._meta.constraints]
        self.assertIn("unique_nombre_codigo_potrero", nombres)

    # ── CP-MODEL-04 ──────────────────────────────────────────────────────────
    def test_nombre_codigo_duplicado_lanza_error(self):
        """Crear dos potreros con el mismo nombre_codigo debe lanzar IntegrityError."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_potrero("Potrero Norte")

    # ── CP-MODEL-05 ──────────────────────────────────────────────────────────
    def test_get_animales_activos_count_sin_animales(self):
        """Con cero animales asignados, get_animales_activos_count() retorna 0."""
        self.assertEqual(self.potrero.get_animales_activos_count(), 0)

    # ── CP-MODEL-06 ──────────────────────────────────────────────────────────
    def test_get_animales_activos_count_con_activos_e_inactivos(self):
        """Solo cuenta animales en estado ACTIVO; ignora INACTIVO y BORRADOR."""
        make_animal(self.potrero, rfid="A-ACT-1", estado=Animal.Estado.ACTIVO)
        make_animal(self.potrero, rfid="A-ACT-2", estado=Animal.Estado.ACTIVO)
        make_animal(self.potrero, rfid="A-INA-1", estado=Animal.Estado.INACTIVO)
        make_animal(self.potrero, rfid="A-BOR-1", estado=Animal.Estado.BORRADOR)
        self.assertEqual(self.potrero.get_animales_activos_count(), 2)

    # ── CP-MODEL-07 ──────────────────────────────────────────────────────────
    def test_get_porcentaje_ocupacion_correcto(self):
        """Con 5 animales activos sobre capacidad 10 → 50.0%."""
        for i in range(5):
            make_animal(self.potrero, rfid=f"A-OC-{i}")
        self.assertEqual(self.potrero.get_porcentaje_ocupacion(), 50.0)

    # ── CP-MODEL-08 ──────────────────────────────────────────────────────────
    def test_get_porcentaje_ocupacion_supera_100(self):
        """Con más animales que capacidad, puede superar 100%."""
        for i in range(12):
            make_animal(self.potrero, rfid=f"A-OVER-{i}")
        self.assertGreater(self.potrero.get_porcentaje_ocupacion(), 100)

    # ── CP-MODEL-09 ──────────────────────────────────────────────────────────
    def test_get_porcentaje_ocupacion_capacidad_cero(self):
        """Con capacidad_maxima == 0, get_porcentaje_ocupacion() retorna 0.0 sin error."""
        p = make_potrero("P-CAP0", capacidad_maxima=0)
        self.assertEqual(p.get_porcentaje_ocupacion(), 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – Formulario
# ─────────────────────────────────────────────────────────────────────────────

class PotreroFormTests(TestCase):
    """Valida las validaciones del PotreroForm."""

    def _form(self, **overrides):
        data = {
            "nombre_codigo":   "Potrero Sur",
            "area_ha":         "8.50",
            "capacidad_maxima": "15",
            "tipo_uso":        Potrero.TipoUso.CEBA,
        }
        data.update(overrides)
        return PotreroForm(data)

    # ── CP-FORM-01 ───────────────────────────────────────────────────────────
    def test_form_valido_con_datos_correctos(self):
        """Todos los campos válidos → form.is_valid() True."""
        self.assertTrue(self._form().is_valid())

    # ── CP-FORM-02 ───────────────────────────────────────────────────────────
    def test_area_cero_invalida(self):
        """area_ha == 0 → error en campo area_ha."""
        form = self._form(area_ha="0")
        self.assertFalse(form.is_valid())
        self.assertIn("area_ha", form.errors)

    # ── CP-FORM-03 ───────────────────────────────────────────────────────────
    def test_area_negativa_invalida(self):
        """area_ha < 0 → error en campo area_ha."""
        form = self._form(area_ha="-5")
        self.assertFalse(form.is_valid())
        self.assertIn("area_ha", form.errors)

    # ── CP-FORM-04 ───────────────────────────────────────────────────────────
    def test_capacidad_cero_invalida(self):
        """capacidad_maxima == 0 → error en campo capacidad_maxima."""
        form = self._form(capacidad_maxima="0")
        self.assertFalse(form.is_valid())
        self.assertIn("capacidad_maxima", form.errors)

    # ── CP-FORM-05 ───────────────────────────────────────────────────────────
    def test_nombre_codigo_duplicado_invalida(self):
        """nombre_codigo ya existe → error en campo nombre_codigo."""
        make_potrero("Potrero Sur")
        form = self._form(nombre_codigo="Potrero Sur")
        self.assertFalse(form.is_valid())
        self.assertIn("nombre_codigo", form.errors)

    # ── CP-FORM-06 ───────────────────────────────────────────────────────────
    def test_nombre_codigo_duplicado_excluye_instancia_propia(self):
        """Al editar un potrero, su propio nombre_codigo no se considera duplicado."""
        p = make_potrero("Potrero Sur")
        form = PotreroForm(
            {"nombre_codigo": "Potrero Sur", "area_ha": "8.50",
             "capacidad_maxima": "15", "tipo_uso": Potrero.TipoUso.CEBA},
            instance=p,
        )
        self.assertTrue(form.is_valid())

    # ── CP-FORM-07 ───────────────────────────────────────────────────────────
    def test_observaciones_es_opcional(self):
        """El campo observaciones puede omitirse → form válido."""
        form = self._form()
        self.assertNotIn("observaciones", form.errors)
        self.assertTrue(form.is_valid())


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – RBAC y Control de Acceso
# ─────────────────────────────────────────────────────────────────────────────

class PotreroRBACTests(TestCase):
    """
    Valida que @login_required + @require_perm restringen el acceso
    según los permisos potreros.read y potreros.write.
    """

    def setUp(self):
        self.potrero = make_potrero("P-RBAC")

        self.user_read = make_user("user_read")
        grant_perm(self.user_read, "potreros.read")

        self.user_write = make_user("user_write")
        grant_perm(self.user_write, "potreros.read")
        grant_perm(self.user_write, "potreros.write")

        self.user_sin = make_user("user_sin")

    # ── CP-RBAC-01 ───────────────────────────────────────────────────────────
    def test_list_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("potreros:list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-02 ───────────────────────────────────────────────────────────
    def test_detail_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("potreros:detail", args=[self.potrero.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-03 ───────────────────────────────────────────────────────────
    def test_create_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("potreros:create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-04 ───────────────────────────────────────────────────────────
    def test_list_sin_permiso_retorna_403(self):
        self.client.login(username="user_sin", password="testpass123")
        self.assertEqual(self.client.get(reverse("potreros:list")).status_code, 403)

    # ── CP-RBAC-05 ───────────────────────────────────────────────────────────
    def test_detail_sin_permiso_retorna_403(self):
        self.client.login(username="user_sin", password="testpass123")
        r = self.client.get(reverse("potreros:detail", args=[self.potrero.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-06 ───────────────────────────────────────────────────────────
    def test_create_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        self.assertEqual(self.client.get(reverse("potreros:create")).status_code, 403)

    # ── CP-RBAC-07 ───────────────────────────────────────────────────────────
    def test_edit_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.get(reverse("potreros:edit", args=[self.potrero.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-08 ───────────────────────────────────────────────────────────
    def test_deactivate_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.post(reverse("potreros:deactivate", args=[self.potrero.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-09 ───────────────────────────────────────────────────────────
    def test_solo_read_puede_listar_y_ver_pero_no_escribir(self):
        self.client.login(username="user_read", password="testpass123")
        self.assertEqual(self.client.get(reverse("potreros:list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("potreros:detail", args=[self.potrero.pk])).status_code, 200
        )
        self.assertEqual(self.client.get(reverse("potreros:create")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("potreros:edit", args=[self.potrero.pk])).status_code, 403
        )

    # ── CP-RBAC-10 ───────────────────────────────────────────────────────────
    def test_write_puede_acceder_a_create_y_edit(self):
        self.client.login(username="user_write", password="testpass123")
        self.assertEqual(self.client.get(reverse("potreros:create")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("potreros:edit", args=[self.potrero.pk])).status_code, 200
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 4 – Vistas (comportamiento funcional)
# ─────────────────────────────────────────────────────────────────────────────

class PotreroVistaTests(TestCase):
    """
    Prueba el comportamiento funcional de todas las vistas del módulo
    de potreros: listado, filtros, creación, edición, detalle y desactivación.
    """

    def setUp(self):
        self.user = make_user("operario")
        grant_perm(self.user, "potreros.read")
        grant_perm(self.user, "potreros.write")
        self.client.login(username="operario", password="testpass123")

        self.potrero = make_potrero("Potrero A", capacidad_maxima=10)
        self.potrero_b = make_potrero("Potrero B", tipo_uso=Potrero.TipoUso.LEVANTE)

    def _post_create(self, **overrides):
        data = {
            "nombre_codigo":   "Potrero Nuevo",
            "area_ha":         "12.50",
            "capacidad_maxima": "25",
            "tipo_uso":        Potrero.TipoUso.CEBA,
            "observaciones":   "",
        }
        data.update(overrides)
        return self.client.post(reverse("potreros:create"), data)

    def _post_edit(self, potrero, **overrides):
        data = {
            "nombre_codigo":   potrero.nombre_codigo,
            "area_ha":         str(potrero.area_ha),
            "capacidad_maxima": str(potrero.capacidad_maxima),
            "tipo_uso":        potrero.tipo_uso,
            "observaciones":   "",
        }
        data.update(overrides)
        return self.client.post(reverse("potreros:edit", args=[potrero.pk]), data)

    # ── CP-VISTA-01 ──────────────────────────────────────────────────────────
    def test_list_retorna_200_y_potreros_en_contexto(self):
        """GET /potreros/ → 200, potreros en page_obj."""
        r = self.client.get(reverse("potreros:list"))
        self.assertEqual(r.status_code, 200)
        pks = [item["potrero"].pk for item in r.context["page_obj"].object_list]
        self.assertIn(self.potrero.pk, pks)
        self.assertIn(self.potrero_b.pk, pks)

    # ── CP-VISTA-02 ──────────────────────────────────────────────────────────
    def test_list_filtro_q_por_nombre(self):
        """GET ?q=Potrero+A → solo retorna potreros cuyo nombre contiene 'Potrero A'."""
        r = self.client.get(reverse("potreros:list") + "?q=Potrero+A")
        self.assertEqual(r.status_code, 200)
        pks = [item["potrero"].pk for item in r.context["page_obj"].object_list]
        self.assertIn(self.potrero.pk, pks)
        self.assertNotIn(self.potrero_b.pk, pks)

    # ── CP-VISTA-03 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_estado_activo(self):
        """GET ?estado=ACTIVO → solo retorna potreros ACTIVOS."""
        p_inac = make_potrero("P-INAC", estado=Potrero.Estado.INACTIVO)
        r = self.client.get(reverse("potreros:list") + "?estado=ACTIVO")
        pks = [item["potrero"].pk for item in r.context["page_obj"].object_list]
        self.assertNotIn(p_inac.pk, pks)

    # ── CP-VISTA-04 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_tipo(self):
        """GET ?tipo=LEVANTE → solo retorna potreros con tipo_uso LEVANTE."""
        r = self.client.get(reverse("potreros:list") + "?tipo=LEVANTE")
        pks = [item["potrero"].pk for item in r.context["page_obj"].object_list]
        self.assertIn(self.potrero_b.pk, pks)
        self.assertNotIn(self.potrero.pk, pks)

    # ── CP-VISTA-05 ──────────────────────────────────────────────────────────
    def test_list_incluye_resumen_en_contexto(self):
        """El contexto del listado incluye el dict 'resumen' con métricas globales."""
        r = self.client.get(reverse("potreros:list"))
        self.assertIn("resumen", r.context)
        resumen = r.context["resumen"]
        self.assertIn("total_potreros", resumen)
        self.assertIn("animales_activos", resumen)
        self.assertIn("capacidad_total", resumen)
        self.assertIn("ocupacion_global", resumen)

    # ── CP-VISTA-06 ──────────────────────────────────────────────────────────
    def test_list_puede_escribir_true_con_permiso_write(self):
        """Context 'puede_escribir' es True para usuario con potreros.write."""
        r = self.client.get(reverse("potreros:list"))
        self.assertTrue(r.context["puede_escribir"])

    # ── CP-VISTA-07 ──────────────────────────────────────────────────────────
    def test_list_puede_escribir_false_sin_permiso_write(self):
        """Context 'puede_escribir' es False para usuario solo con potreros.read."""
        user_r = make_user("solo_read")
        grant_perm(user_r, "potreros.read")
        self.client.login(username="solo_read", password="testpass123")
        r = self.client.get(reverse("potreros:list"))
        self.assertFalse(r.context["puede_escribir"])

    # ── CP-VISTA-08 ──────────────────────────────────────────────────────────
    def test_create_get_retorna_json_con_html(self):
        """GET /potreros/nuevo/ → 200, JSON con clave 'html'."""
        r = self.client.get(reverse("potreros:create"))
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("html", data)

    # ── CP-VISTA-09 ──────────────────────────────────────────────────────────
    def test_create_post_valido_crea_potrero_y_retorna_json_success(self):
        """POST válido → potrero creado, JSON success=True, potrero_id presente."""
        count_antes = Potrero.objects.count()
        r, data = _post_json(self.client, reverse("potreros:create"), {
            "nombre_codigo": "Potrero Nuevo",
            "area_ha": "12.50",
            "capacidad_maxima": "25",
            "tipo_uso": Potrero.TipoUso.CEBA,
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(data["success"])
        self.assertIn("potrero_id", data)
        self.assertEqual(Potrero.objects.count(), count_antes + 1)

    # ── CP-VISTA-10 ──────────────────────────────────────────────────────────
    def test_create_post_nombre_duplicado_retorna_json_error(self):
        """POST con nombre_codigo ya existente → JSON success=False, error en errors."""
        r, data = _post_json(self.client, reverse("potreros:create"), {
            "nombre_codigo": "Potrero A",  # ya existe en setUp
            "area_ha": "5.00",
            "capacidad_maxima": "10",
            "tipo_uso": Potrero.TipoUso.CEBA,
        })
        self.assertFalse(data["success"])
        self.assertIn("nombre_codigo", data["errors"])

    # ── CP-VISTA-11 ──────────────────────────────────────────────────────────
    def test_create_post_area_cero_retorna_json_error(self):
        """POST con area_ha == 0 → JSON success=False, error en area_ha."""
        r, data = _post_json(self.client, reverse("potreros:create"), {
            "nombre_codigo": "Potrero X",
            "area_ha": "0",
            "capacidad_maxima": "10",
            "tipo_uso": Potrero.TipoUso.CEBA,
        })
        self.assertFalse(data["success"])
        self.assertIn("area_ha", data["errors"])

    # ── CP-VISTA-12 ──────────────────────────────────────────────────────────
    def test_create_post_capacidad_cero_retorna_json_error(self):
        """POST con capacidad_maxima == 0 → JSON success=False, error en capacidad_maxima."""
        r, data = _post_json(self.client, reverse("potreros:create"), {
            "nombre_codigo": "Potrero Y",
            "area_ha": "5.00",
            "capacidad_maxima": "0",
            "tipo_uso": Potrero.TipoUso.CEBA,
        })
        self.assertFalse(data["success"])
        self.assertIn("capacidad_maxima", data["errors"])

    # ── CP-VISTA-13 ──────────────────────────────────────────────────────────
    def test_create_asigna_estado_activo_y_created_by(self):
        """POST válido → potrero creado con estado ACTIVO y created_by=usuario."""
        self._post_create(nombre_codigo="Potrero Auditable")
        p = Potrero.objects.get(nombre_codigo="Potrero Auditable")
        self.assertEqual(p.estado, Potrero.Estado.ACTIVO)
        self.assertEqual(p.created_by, self.user)

    # ── CP-VISTA-14 ──────────────────────────────────────────────────────────
    def test_detail_retorna_200_con_contexto_correcto(self):
        """GET /potreros/<pk>/ → 200, potrero, activos_count y porcentaje en contexto."""
        r = self.client.get(reverse("potreros:detail", args=[self.potrero.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["potrero"].pk, self.potrero.pk)
        self.assertIn("activos_count", r.context)
        self.assertIn("porcentaje", r.context)
        self.assertIn("disponibles", r.context)

    # ── CP-VISTA-15 ──────────────────────────────────────────────────────────
    def test_detail_potrero_inexistente_retorna_404(self):
        """GET /potreros/99999/ → 404."""
        r = self.client.get(reverse("potreros:detail", args=[99999]))
        self.assertEqual(r.status_code, 404)

    # ── CP-VISTA-16 ──────────────────────────────────────────────────────────
    def test_edit_get_retorna_json_con_html(self):
        """GET /potreros/<pk>/editar/ → 200, JSON con clave 'html'."""
        r = self.client.get(reverse("potreros:edit", args=[self.potrero.pk]))
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("html", data)

    # ── CP-VISTA-17 ──────────────────────────────────────────────────────────
    def test_edit_post_valido_actualiza_potrero(self):
        """POST edición válida → JSON success=True, datos actualizados en BD."""
        r, data = _post_json(self.client, reverse("potreros:edit", args=[self.potrero.pk]), {
            "nombre_codigo": "Potrero A Modificado",
            "area_ha": "15.00",
            "capacidad_maxima": "30",
            "tipo_uso": Potrero.TipoUso.MATERNIDAD,
        })
        self.assertTrue(data["success"])
        self.potrero.refresh_from_db()
        self.assertEqual(self.potrero.nombre_codigo, "Potrero A Modificado")
        self.assertEqual(self.potrero.capacidad_maxima, 30)

    # ── CP-VISTA-18 ──────────────────────────────────────────────────────────
    def test_edit_post_capacidad_menor_a_activos_retorna_warning(self):
        """POST edición con nueva capacidad < animales activos → success=True + campo 'warning'."""
        for i in range(5):
            make_animal(self.potrero, rfid=f"A-WARN-{i}")

        r, data = _post_json(self.client, reverse("potreros:edit", args=[self.potrero.pk]), {
            "nombre_codigo": self.potrero.nombre_codigo,
            "area_ha": str(self.potrero.area_ha),
            "capacidad_maxima": "3",   # menor que los 5 animales activos
            "tipo_uso": self.potrero.tipo_uso,
        })
        self.assertTrue(data["success"])
        self.assertIn("warning", data)

    # ── CP-VISTA-19 ──────────────────────────────────────────────────────────
    def test_deactivate_post_sin_animales_cambia_estado_a_inactivo(self):
        """POST desactivar potrero sin animales activos → JSON success=True, estado INACTIVO."""
        r, data = _post_json(
            self.client, reverse("potreros:deactivate", args=[self.potrero.pk]), {}
        )
        self.assertTrue(data["success"])
        self.potrero.refresh_from_db()
        self.assertEqual(self.potrero.estado, Potrero.Estado.INACTIVO)

    # ── CP-VISTA-20 ──────────────────────────────────────────────────────────
    def test_deactivate_post_con_animales_activos_retorna_blocked(self):
        """POST desactivar potrero con animales activos → JSON blocked=True, success=False."""
        make_animal(self.potrero, rfid="A-BLOCK-1")
        make_animal(self.potrero, rfid="A-BLOCK-2")

        r, data = _post_json(
            self.client, reverse("potreros:deactivate", args=[self.potrero.pk]), {}
        )
        self.assertFalse(data["success"])
        self.assertTrue(data["blocked"])
        self.assertIn("animales", data)
        self.assertEqual(len(data["animales"]), 2)
        # Estado no debe haber cambiado
        self.potrero.refresh_from_db()
        self.assertEqual(self.potrero.estado, Potrero.Estado.ACTIVO)

    # ── CP-VISTA-21 ──────────────────────────────────────────────────────────
    def test_deactivate_get_retorna_405(self):
        """GET /potreros/<pk>/desactivar/ → 405 Method Not Allowed (solo acepta POST)."""
        r = self.client.get(reverse("potreros:deactivate", args=[self.potrero.pk]))
        self.assertEqual(r.status_code, 405)