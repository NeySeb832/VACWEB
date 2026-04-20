# transacciones/tests.py
"""
Pruebas funcionales – CU-006: Registro de Transacciones Comerciales
====================================================================
Bloque 1 – Modelo y Reglas de Negocio   (CP-MODEL-01 … CP-MODEL-10)
Bloque 2 – Formularios                  (CP-FORM-01  … CP-FORM-08)
Bloque 3 – RBAC y Control de Acceso     (CP-RBAC-01  … CP-RBAC-08)
Bloque 4 – Vistas (comportamiento)      (CP-VISTA-01 … CP-VISTA-14)

Reglas de negocio cubiertas:
  RN-1: tipo obligatorio ∈ {COM, VEN, SAC}
  RN-2: valor_cop > 0
  RN-3: fecha <= today
  RN-4: compatibilidad estado animal / tipo
  RN-5: atomicidad — transaction.atomic()
  RN-6: anulación lógica con motivo obligatorio (≥ 10 caracteres)
"""

import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from animals.models import Animal
from authz.models import Permission, Role, RolePermission, UserRole
from potreros.models import Potrero

from decimal import Decimal

from .forms import AnimalInlineForm, AnulacionTransaccionForm, TransaccionForm
from .models import Transaccion


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades compartidas
# ─────────────────────────────────────────────────────────────────────────────

HOY     = date.today()
AYER    = HOY - timedelta(days=1)
MANANA  = HOY + timedelta(days=1)


def make_user(username: str, password: str = "testpass123") -> User:
    return User.objects.create_user(username=username, password=password)


def grant_perm(user: User, perm_code: str) -> None:
    """Asigna un permiso al usuario mediante un rol dedicado."""
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


def make_animal(potrero, rfid: str = "COL-TX-001",
                estado=Animal.Estado.ACTIVO) -> Animal:
    return Animal.objects.create(
        rfid=rfid,
        sexo=Animal.Sexo.MACHO,
        etapa=Animal.Etapa.LEVANTE,
        potrero=potrero,
        estado=estado,
    )


def make_transaccion(animal, user, tipo=Transaccion.Tipo.COMPRA,
                     valor="500000.00") -> Transaccion:
    tx = Transaccion.objects.create(
        tipo=tipo,
        fecha=AYER,
        animal=animal,
        origen_destino="Finca El Roble",
        valor_cop=valor,
        estado=Transaccion.Estado.CONFIRMADO,
        created_by=user,
    )
    return tx


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Modelo y Reglas de Negocio
# ─────────────────────────────────────────────────────────────────────────────

class TransaccionModelTests(TestCase):
    """Valida el modelo Transaccion: RN-2, RN-3, RN-4 y métodos de impacto."""

    def setUp(self):
        self.potrero = make_potrero("PM")
        self.user    = make_user("admin_model")
        self.animal_activo   = make_animal(self.potrero, rfid="COL-M-001",
                                           estado=Animal.Estado.ACTIVO)
        self.animal_borrador = make_animal(self.potrero, rfid="COL-M-002",
                                           estado=Animal.Estado.BORRADOR)
        self.animal_inactivo = make_animal(self.potrero, rfid="COL-M-003",
                                           estado=Animal.Estado.INACTIVO)

    def _build_tx(self, tipo, animal, valor=Decimal("100000"), fecha=None):
        return Transaccion(
            tipo=tipo,
            fecha=fecha or AYER,
            animal=animal,
            origen_destino="Test",
            valor_cop=valor,
            created_by=self.user,
        )

    # ── CP-MODEL-01 ──────────────────────────────────────────────────────────
    def test_str_incluye_tipo_e_identificador(self):
        tx = make_transaccion(self.animal_activo, self.user)
        s = str(tx)
        self.assertIn("Compra", s)
        self.assertIn(self.animal_activo.rfid, s)

    # ── CP-MODEL-02 ──────────────────────────────────────────────────────────
    def test_RN2_valor_cero_falla_validacion(self):
        tx = self._build_tx(Transaccion.Tipo.COMPRA, self.animal_borrador,
                            valor=Decimal("0"))
        with self.assertRaises(ValidationError) as ctx:
            tx.clean()
        self.assertIn("valor_cop", ctx.exception.message_dict)

    # ── CP-MODEL-03 ──────────────────────────────────────────────────────────
    def test_RN2_valor_negativo_falla_validacion(self):
        tx = self._build_tx(Transaccion.Tipo.COMPRA, self.animal_borrador,
                            valor=Decimal("-1"))
        with self.assertRaises(ValidationError) as ctx:
            tx.clean()
        self.assertIn("valor_cop", ctx.exception.message_dict)

    # ── CP-MODEL-04 ──────────────────────────────────────────────────────────
    def test_RN3_fecha_futura_falla_validacion(self):
        tx = self._build_tx(Transaccion.Tipo.COMPRA, self.animal_borrador,
                            fecha=MANANA)
        with self.assertRaises(ValidationError) as ctx:
            tx.clean()
        self.assertIn("fecha", ctx.exception.message_dict)

    # ── CP-MODEL-05 ──────────────────────────────────────────────────────────
    def test_RN4_venta_sobre_borrador_falla(self):
        tx = self._build_tx(Transaccion.Tipo.VENTA, self.animal_borrador)
        with self.assertRaises(ValidationError) as ctx:
            tx.clean()
        self.assertIn("animal", ctx.exception.message_dict)

    # ── CP-MODEL-06 ──────────────────────────────────────────────────────────
    def test_RN4_sacrificio_sobre_borrador_falla(self):
        tx = self._build_tx(Transaccion.Tipo.SACRIFICIO, self.animal_borrador)
        with self.assertRaises(ValidationError) as ctx:
            tx.clean()
        self.assertIn("animal", ctx.exception.message_dict)

    # ── CP-MODEL-07 ──────────────────────────────────────────────────────────
    def test_RN4_compra_sobre_inactivo_falla(self):
        tx = self._build_tx(Transaccion.Tipo.COMPRA, self.animal_inactivo)
        with self.assertRaises(ValidationError) as ctx:
            tx.clean()
        self.assertIn("animal", ctx.exception.message_dict)

    # ── CP-MODEL-08 ──────────────────────────────────────────────────────────
    def test_RN4_venta_sobre_activo_es_valida(self):
        tx = self._build_tx(Transaccion.Tipo.VENTA, self.animal_activo)
        tx.clean()  # No debe lanzar excepción

    # ── CP-MODEL-09 ──────────────────────────────────────────────────────────
    def test_aplicar_impacto_compra_activa_animal(self):
        tx = make_transaccion(self.animal_borrador, self.user,
                              tipo=Transaccion.Tipo.COMPRA)
        tx.aplicar_impacto_inventario()
        self.animal_borrador.refresh_from_db()
        self.assertEqual(self.animal_borrador.estado, Animal.Estado.ACTIVO)

    # ── CP-MODEL-10 ──────────────────────────────────────────────────────────
    def test_aplicar_impacto_venta_desactiva_animal(self):
        tx = make_transaccion(self.animal_activo, self.user,
                              tipo=Transaccion.Tipo.VENTA)
        tx.aplicar_impacto_inventario()
        self.animal_activo.refresh_from_db()
        self.assertEqual(self.animal_activo.estado, Animal.Estado.INACTIVO)

    # ── CP-MODEL-11 ──────────────────────────────────────────────────────────
    def test_revertir_impacto_restaura_estado(self):
        tx = make_transaccion(self.animal_activo, self.user,
                              tipo=Transaccion.Tipo.VENTA)
        tx.aplicar_impacto_inventario()
        tx.revertir_impacto_inventario(Animal.Estado.ACTIVO)
        self.animal_activo.refresh_from_db()
        self.assertEqual(self.animal_activo.estado, Animal.Estado.ACTIVO)

    # ── CP-MODEL-12 ──────────────────────────────────────────────────────────
    def test_es_anulable_true_si_confirmado(self):
        tx = make_transaccion(self.animal_activo, self.user)
        self.assertTrue(tx.es_anulable)

    # ── CP-MODEL-13 ──────────────────────────────────────────────────────────
    def test_es_anulable_false_si_anulado(self):
        tx = make_transaccion(self.animal_activo, self.user)
        tx.estado = Transaccion.Estado.ANULADO
        tx.save()
        self.assertFalse(tx.es_anulable)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – Formularios
# ─────────────────────────────────────────────────────────────────────────────

class TransaccionFormTests(TestCase):
    """Valida TransaccionForm, AnimalInlineForm y AnulacionTransaccionForm."""

    def setUp(self):
        self.potrero = make_potrero("PF")
        self.animal_activo   = make_animal(self.potrero, rfid="COL-F-001",
                                           estado=Animal.Estado.ACTIVO)
        self.animal_borrador = make_animal(self.potrero, rfid="COL-F-002",
                                           estado=Animal.Estado.BORRADOR)

    def _form_data(self, **overrides):
        data = {
            "tipo":            Transaccion.Tipo.COMPRA,
            "fecha":           str(AYER),
            "animal":          self.animal_borrador.pk,
            "origen_destino":  "Finca Origen",
            "valor_cop":       "800000.00",
            "observaciones":   "",
        }
        data.update(overrides)
        return data

    # ── CP-FORM-01 ───────────────────────────────────────────────────────────
    def test_form_valido_compra(self):
        form = TransaccionForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)

    # ── CP-FORM-02 ───────────────────────────────────────────────────────────
    def test_form_valor_cero_invalido(self):
        form = TransaccionForm(data=self._form_data(valor_cop="0"))
        self.assertFalse(form.is_valid())
        self.assertIn("valor_cop", form.errors)

    # ── CP-FORM-03 ───────────────────────────────────────────────────────────
    def test_form_fecha_futura_invalida(self):
        form = TransaccionForm(data=self._form_data(fecha=str(MANANA)))
        self.assertFalse(form.is_valid())
        self.assertIn("fecha", form.errors)

    # ── CP-FORM-04 ───────────────────────────────────────────────────────────
    def test_form_venta_sobre_borrador_invalida(self):
        form = TransaccionForm(data=self._form_data(
            tipo=Transaccion.Tipo.VENTA,
            animal=self.animal_borrador.pk,
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("animal", form.errors)

    # ── CP-FORM-05 ───────────────────────────────────────────────────────────
    def test_form_venta_sobre_activo_valida(self):
        form = TransaccionForm(data=self._form_data(
            tipo=Transaccion.Tipo.VENTA,
            animal=self.animal_activo.pk,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    # ── CP-FORM-06 ───────────────────────────────────────────────────────────
    def test_animal_inline_sin_rfid_ni_arete_invalido(self):
        form = AnimalInlineForm(data={"crear_animal": True,
                                      "ani_rfid": "", "ani_arete": ""})
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    # ── CP-FORM-07 ───────────────────────────────────────────────────────────
    def test_animal_inline_con_rfid_valido(self):
        form = AnimalInlineForm(data={"crear_animal": True,
                                      "ani_rfid": "COL-INLINE-99",
                                      "ani_arete": ""})
        self.assertTrue(form.is_valid(), form.errors)

    # ── CP-FORM-08 ───────────────────────────────────────────────────────────
    def test_animal_inline_sin_crear_animal_no_valida_campos(self):
        """crear_animal=False → no se exige rfid/arete."""
        form = AnimalInlineForm(data={"crear_animal": False,
                                      "ani_rfid": "", "ani_arete": ""})
        self.assertTrue(form.is_valid(), form.errors)

    # ── CP-FORM-09 ───────────────────────────────────────────────────────────
    def test_anulacion_motivo_corto_invalido(self):
        form = AnulacionTransaccionForm(data={"motivo": "Corto"})
        self.assertFalse(form.is_valid())
        self.assertIn("motivo", form.errors)

    # ── CP-FORM-10 ───────────────────────────────────────────────────────────
    def test_anulacion_motivo_suficiente_valido(self):
        form = AnulacionTransaccionForm(
            data={"motivo": "Error en el registro del animal adquirido."}
        )
        self.assertTrue(form.is_valid(), form.errors)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – RBAC y Control de Acceso
# ─────────────────────────────────────────────────────────────────────────────

class TransaccionRBACTests(TestCase):
    """Valida @login_required + @require_perm en las vistas de transacciones."""

    def setUp(self):
        self.potrero = make_potrero("PR")
        self.animal  = make_animal(self.potrero, rfid="COL-RBAC-001")

        self.admin      = make_user("admin_rbac")
        self.tx         = make_transaccion(self.animal, self.admin)

        self.user_read  = make_user("user_read")
        grant_perm(self.user_read, "transacciones.read")

        self.user_write = make_user("user_write")
        grant_perm(self.user_write, "transacciones.read")
        grant_perm(self.user_write, "transacciones.write")

        self.user_anular = make_user("user_anular")
        grant_perm(self.user_anular, "transacciones.read")
        grant_perm(self.user_anular, "transacciones.anular")

        self.user_sin = make_user("user_sin")

    # ── CP-RBAC-01 ───────────────────────────────────────────────────────────
    def test_list_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("transacciones:list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-02 ───────────────────────────────────────────────────────────
    def test_detail_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("transacciones:detail", args=[self.tx.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-03 ───────────────────────────────────────────────────────────
    def test_create_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("transacciones:create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-04 ───────────────────────────────────────────────────────────
    def test_list_sin_permiso_read_retorna_403(self):
        self.client.force_login(self.user_sin)
        self.assertEqual(self.client.get(reverse("transacciones:list")).status_code, 403)

    # ── CP-RBAC-05 ───────────────────────────────────────────────────────────
    def test_detail_sin_permiso_read_retorna_403(self):
        self.client.force_login(self.user_sin)
        self.assertEqual(
            self.client.get(reverse("transacciones:detail", args=[self.tx.pk])).status_code,
            403
        )

    # ── CP-RBAC-06 ───────────────────────────────────────────────────────────
    def test_create_sin_permiso_write_retorna_403(self):
        self.client.force_login(self.user_read)
        self.assertEqual(
            self.client.get(reverse("transacciones:create")).status_code, 403
        )

    # ── CP-RBAC-07 ───────────────────────────────────────────────────────────
    def test_anular_sin_permiso_anular_retorna_403(self):
        self.client.force_login(self.user_read)
        self.assertEqual(
            self.client.post(
                reverse("transacciones:anular", args=[self.tx.pk]),
                {"motivo": "Motivo suficientemente largo para pasar validación"}
            ).status_code,
            403
        )

    # ── CP-RBAC-08 ───────────────────────────────────────────────────────────
    def test_solo_read_puede_listar_y_ver_pero_no_crear(self):
        self.client.force_login(self.user_read)
        self.assertEqual(self.client.get(reverse("transacciones:list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("transacciones:detail", args=[self.tx.pk])).status_code,
            200
        )
        self.assertEqual(self.client.get(reverse("transacciones:create")).status_code, 403)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 4 – Vistas (comportamiento funcional)
# ─────────────────────────────────────────────────────────────────────────────

class TransaccionVistaTests(TestCase):
    """
    Prueba el comportamiento de las vistas de transacciones:
    listado, filtros, creación AJAX, detalle, anulación, historial.
    """

    def setUp(self):
        self.potrero = make_potrero("PV")
        self.user    = make_user("operario_tx")
        grant_perm(self.user, "transacciones.read")
        grant_perm(self.user, "transacciones.write")
        grant_perm(self.user, "transacciones.anular")
        self.client.force_login(self.user)

        self.animal_activo   = make_animal(self.potrero, rfid="COL-V-001",
                                           estado=Animal.Estado.ACTIVO)
        self.animal_borrador = make_animal(self.potrero, rfid="COL-V-002",
                                           estado=Animal.Estado.BORRADOR)

        # Transacción de referencia (COMPRA confirmada)
        self.tx = make_transaccion(self.animal_activo, self.user,
                                   tipo=Transaccion.Tipo.COMPRA)

    # ─── Listado ────────────────────────────────────────────────────────────

    # ── CP-VISTA-01 ──────────────────────────────────────────────────────────
    def test_list_retorna_200_y_contexto(self):
        r = self.client.get(reverse("transacciones:list"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("page_obj", r.context)
        pks = [t.pk for t in r.context["page_obj"].object_list]
        self.assertIn(self.tx.pk, pks)

    # ── CP-VISTA-02 ──────────────────────────────────────────────────────────
    def test_list_filtro_tipo(self):
        make_transaccion(self.animal_activo, self.user,
                         tipo=Transaccion.Tipo.VENTA)
        r = self.client.get(reverse("transacciones:list") + "?tipo=COM")
        self.assertEqual(r.status_code, 200)
        tipos = {t.tipo for t in r.context["page_obj"].object_list}
        self.assertEqual(tipos, {"COM"})

    # ── CP-VISTA-03 ──────────────────────────────────────────────────────────
    def test_list_filtro_q_por_rfid(self):
        r = self.client.get(reverse("transacciones:list") + "?q=COL-V-001")
        self.assertEqual(r.status_code, 200)
        results = list(r.context["page_obj"].object_list)
        self.assertTrue(
            all(t.animal.rfid == "COL-V-001" for t in results)
        )

    # ── CP-VISTA-04 ──────────────────────────────────────────────────────────
    def test_list_filtro_estado_anulado(self):
        self.tx.estado = Transaccion.Estado.ANULADO
        self.tx.save()
        r = self.client.get(reverse("transacciones:list") + "?estado=ANU")
        self.assertEqual(r.status_code, 200)
        estados = {t.estado for t in r.context["page_obj"].object_list}
        self.assertEqual(estados, {"ANU"})

    # ─── Detalle ────────────────────────────────────────────────────────────

    # ── CP-VISTA-05 ──────────────────────────────────────────────────────────
    def test_detail_retorna_200_con_datos(self):
        r = self.client.get(reverse("transacciones:detail", args=[self.tx.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["transaccion"].pk, self.tx.pk)

    # ── CP-VISTA-06 ──────────────────────────────────────────────────────────
    def test_detail_404_si_no_existe(self):
        r = self.client.get(reverse("transacciones:detail", args=[99999]))
        self.assertEqual(r.status_code, 404)

    # ─── Crear (AJAX) ───────────────────────────────────────────────────────

    # ── CP-VISTA-07 ──────────────────────────────────────────────────────────
    def test_create_get_retorna_json_con_html(self):
        r = self.client.get(
            reverse("transacciones:create"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("html", data)
        self.assertIn("<form", data["html"])

    # ── CP-VISTA-08 ──────────────────────────────────────────────────────────
    def test_create_get_con_animal_prellenado(self):
        r = self.client.get(
            reverse("transacciones:create") + f"?animal={self.animal_activo.pk}"
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("html", data)

    # ── CP-VISTA-09 ──────────────────────────────────────────────────────────
    def test_create_post_compra_crea_transaccion_y_activa_animal(self):
        """POST COMPRA sobre animal BORRADOR → transacción confirmada + animal ACTIVO."""
        animal = self.animal_borrador
        self.assertEqual(animal.estado, Animal.Estado.BORRADOR)

        r = self.client.post(
            reverse("transacciones:create"),
            {
                "tipo":           "COM",
                "fecha":          str(AYER),
                "animal":         animal.pk,
                "origen_destino": "Proveedor Test",
                "valor_cop":      "750000.00",
                "observaciones":  "",
            },
        )
        self.assertEqual(r.status_code, 200)
        resp = json.loads(r.content)
        self.assertTrue(resp.get("success"), resp)

        animal.refresh_from_db()
        self.assertEqual(animal.estado, Animal.Estado.ACTIVO)
        tx = Transaccion.objects.get(pk=resp["transaccion_id"])
        self.assertEqual(tx.tipo, Transaccion.Tipo.COMPRA)
        self.assertEqual(tx.estado, Transaccion.Estado.CONFIRMADO)

    # ── CP-VISTA-10 ──────────────────────────────────────────────────────────
    def test_create_post_venta_desactiva_animal(self):
        """POST VENTA sobre animal ACTIVO → transacción confirmada + animal INACTIVO."""
        animal = self.animal_activo

        r = self.client.post(
            reverse("transacciones:create"),
            {
                "tipo":           "VEN",
                "fecha":          str(AYER),
                "animal":         animal.pk,
                "origen_destino": "Comprador Test",
                "valor_cop":      "1200000.00",
                "observaciones":  "",
            },
        )
        self.assertEqual(r.status_code, 200)
        resp = json.loads(r.content)
        self.assertTrue(resp.get("success"), resp)

        animal.refresh_from_db()
        self.assertEqual(animal.estado, Animal.Estado.INACTIVO)

    # ── CP-VISTA-11 ──────────────────────────────────────────────────────────
    def test_create_post_sacrificio_desactiva_animal(self):
        """POST SACRIFICIO sobre animal ACTIVO → animal INACTIVO."""
        animal = self.animal_activo

        r = self.client.post(
            reverse("transacciones:create"),
            {
                "tipo":           "SAC",
                "fecha":          str(AYER),
                "animal":         animal.pk,
                "origen_destino": "Frigorífico",
                "valor_cop":      "900000.00",
                "observaciones":  "",
            },
        )
        self.assertEqual(r.status_code, 200)
        resp = json.loads(r.content)
        self.assertTrue(resp.get("success"), resp)

        animal.refresh_from_db()
        self.assertEqual(animal.estado, Animal.Estado.INACTIVO)

    # ── CP-VISTA-12 ──────────────────────────────────────────────────────────
    def test_create_post_datos_invalidos_retorna_400_con_errores(self):
        """POST con valor_cop=0 → 400 + JSON con errors."""
        r = self.client.post(
            reverse("transacciones:create"),
            {
                "tipo":           "COM",
                "fecha":          str(AYER),
                "animal":         self.animal_borrador.pk,
                "origen_destino": "Proveedor",
                "valor_cop":      "0",
            },
        )
        self.assertEqual(r.status_code, 400)
        resp = json.loads(r.content)
        self.assertFalse(resp.get("success"))
        self.assertIn("errors", resp)

    # ── CP-VISTA-13 ──────────────────────────────────────────────────────────
    def test_create_post_inline_animal_crea_animal_y_transaccion(self):
        """COMPRA + crear_animal=True → Animal nuevo en BORRADOR→ACTIVO + transacción."""
        conteo_antes = Animal.objects.count()

        r = self.client.post(
            reverse("transacciones:create"),
            {
                "tipo":           "COM",
                "fecha":          str(AYER),
                "origen_destino": "Finca Externa",
                "valor_cop":      "650000.00",
                "observaciones":  "",
                # AnimalInlineForm
                "crear_animal":   True,
                "ani_rfid":       "COL-INLINE-01",
                "ani_arete":      "",
                "ani_sexo":       "M",
                "ani_etapa":      "LEV",
                "ani_raza":       "Brahman",
                "ani_procedencia": "Proveedor Norte",
                "ani_peso_entrada": "240.00",
            },
        )
        self.assertEqual(r.status_code, 200)
        resp = json.loads(r.content)
        self.assertTrue(resp.get("success"), resp)

        # Se creó un animal nuevo
        self.assertEqual(Animal.objects.count(), conteo_antes + 1)
        nuevo = Animal.objects.get(rfid="COL-INLINE-01")
        self.assertEqual(nuevo.estado, Animal.Estado.ACTIVO)

        # La transacción apunta al nuevo animal
        tx = Transaccion.objects.get(pk=resp["transaccion_id"])
        self.assertEqual(tx.animal_id, nuevo.pk)

    # ─── Anular ─────────────────────────────────────────────────────────────

    # ── CP-VISTA-14 ──────────────────────────────────────────────────────────
    def test_anular_confirma_anulacion_y_revierte_inventario(self):
        """POST anular transacción COMPRA → estado ANULADO + animal vuelve a BORRADOR."""
        # Primero aplicar impacto para que el animal quede ACTIVO
        self.tx.aplicar_impacto_inventario()
        self.animal_activo.refresh_from_db()

        r = self.client.post(
            reverse("transacciones:anular", args=[self.tx.pk]),
            {"motivo": "Compra registrada por error en el sistema."},
        )
        self.assertEqual(r.status_code, 200)
        resp = json.loads(r.content)
        self.assertTrue(resp.get("success"), resp)

        self.tx.refresh_from_db()
        self.assertEqual(self.tx.estado, Transaccion.Estado.ANULADO)
        self.assertEqual(self.tx.anulado_por, self.user)

    # ── CP-VISTA-15 ──────────────────────────────────────────────────────────
    def test_anular_ya_anulada_retorna_400(self):
        self.tx.estado = Transaccion.Estado.ANULADO
        self.tx.save()

        r = self.client.post(
            reverse("transacciones:anular", args=[self.tx.pk]),
            {"motivo": "Intento de doble anulación del mismo registro."},
        )
        self.assertEqual(r.status_code, 400)
        resp = json.loads(r.content)
        self.assertFalse(resp.get("success"))

    # ── CP-VISTA-16 ──────────────────────────────────────────────────────────
    def test_anular_motivo_invalido_retorna_400(self):
        r = self.client.post(
            reverse("transacciones:anular", args=[self.tx.pk]),
            {"motivo": "Corto"},
        )
        self.assertEqual(r.status_code, 400)
        resp = json.loads(r.content)
        self.assertFalse(resp.get("success"))
        self.assertIn("errors", resp)

    # ─── Historial por animal ────────────────────────────────────────────────

    # ── CP-VISTA-17 ──────────────────────────────────────────────────────────
    def test_historial_animal_retorna_200_y_estadisticas(self):
        make_transaccion(self.animal_activo, self.user,
                         tipo=Transaccion.Tipo.VENTA)
        r = self.client.get(
            reverse("transacciones:historial_animal",
                    args=[self.animal_activo.pk])
        )
        self.assertEqual(r.status_code, 200)
        ctx = r.context
        self.assertEqual(ctx["animal"].pk, self.animal_activo.pk)
        self.assertGreaterEqual(ctx["total_compras"], 1)
        self.assertGreaterEqual(ctx["total_ventas"], 1)

    # ── CP-VISTA-18 ──────────────────────────────────────────────────────────
    def test_historial_animal_404_si_no_existe(self):
        r = self.client.get(
            reverse("transacciones:historial_animal", args=[99999])
        )
        self.assertEqual(r.status_code, 404)
