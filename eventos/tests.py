# eventos/tests.py
"""
Pruebas funcionales – CU-003: Registro de Vacunas y Tratamientos
=================================================================
Bloque 1 – Modelo y Reglas de Negocio  (CP-MODEL-01 … CP-MODEL-12)
Bloque 2 – RBAC y Control de Acceso    (CP-RBAC-01  … CP-RBAC-10)
Bloque 3 – Vistas                      (CP-VISTA-01 … CP-VISTA-17)

Correspondencia con los CP del documento CU-003:
  CP-EV-01 → CP-VISTA-07  (registro válido → CONFIRMADO)
  CP-EV-02 → CP-VISTA-06  (navegación desde ficha con ?animal=)
  CP-EV-03 → CP-VISTA-05  (navegación desde módulo sin ?animal=)
  CP-EV-04 → CP-VISTA-08  (datos mínimos faltantes → re-renderiza)
  CP-EV-05 → CP-VISTA-09 + CP-MODEL-04  (animal dado de baja → bloqueado)
  CP-EV-06 → OMITIDO      (registro masivo no implementado aún)
  CP-EV-07 → CP-VISTA-11 + CP-VISTA-13  (inmutabilidad + corrección vinculada)
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from authz.models import Permission, Role, RolePermission, UserRole
from animals.models import Animal, Potrero
from .models import EventoSanitario


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


def make_animal(potrero: Potrero, rfid: str = "COL-EV-001",
                estado: str = Animal.Estado.ACTIVO) -> Animal:
    return Animal.objects.create(
        rfid=rfid,
        arete=f"AR-{rfid}",
        sexo=Animal.Sexo.MACHO,
        etapa=Animal.Etapa.LEVANTE,
        potrero=potrero,
        estado=estado,
    )


def make_evento(animal: Animal, user: User, **kwargs) -> EventoSanitario:
    """Crea un EventoSanitario CONFIRMADO con datos mínimos válidos."""
    defaults = {
        "tipo": "Vacuna Aftosa",
        "responsable": "veterinario01",
        "producto": "Aftovaxpur DOE",
        "estado": EventoSanitario.Estado.CONFIRMADO,
        "created_by": user,
    }
    defaults.update(kwargs)
    return EventoSanitario.objects.create(animal=animal, **defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Modelo y Reglas de Negocio
# ─────────────────────────────────────────────────────────────────────────────

class EventoModelRNTests(TestCase):
    """
    Valida las reglas de negocio implementadas en EventoSanitario.clean():
    RN-1 (datos mínimos obligatorios), RN-2 (animal no INACTIVO),
    RN-3 (inmutabilidad de estados terminales), RN-4 (nuevos eventos solo
    en estados mutables), y propiedades derivadas.
    """

    def setUp(self):
        self.potrero = make_potrero("P1")
        self.user = make_user("vet")
        self.animal_activo = make_animal(self.potrero, rfid="COL-ACT-001",
                                         estado=Animal.Estado.ACTIVO)
        self.animal_borrador = make_animal(self.potrero, rfid="COL-BOR-001",
                                           estado=Animal.Estado.BORRADOR)
        self.animal_inactivo = make_animal(self.potrero, rfid="COL-INA-001",
                                           estado=Animal.Estado.INACTIVO)

    # ── CP-MODEL-01 ──────────────────────────────────────────────────────────
    def test_rn1_sin_tipo_lanza_error(self):
        """RN-1: tipo es obligatorio → ValidationError en campo 'tipo'."""
        ev = EventoSanitario(
            animal=self.animal_activo, tipo="",
            responsable="vet01", producto="Producto X",
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            ev.full_clean()
        self.assertIn("tipo", ctx.exception.message_dict)

    # ── CP-MODEL-02 ──────────────────────────────────────────────────────────
    def test_rn1_sin_responsable_lanza_error(self):
        """RN-1: responsable es obligatorio → ValidationError en campo 'responsable'."""
        ev = EventoSanitario(
            animal=self.animal_activo, tipo="Vacuna Aftosa",
            responsable="", producto="Producto X",
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            ev.full_clean()
        self.assertIn("responsable", ctx.exception.message_dict)

    # ── CP-MODEL-03 ──────────────────────────────────────────────────────────
    def test_rn1_sin_producto_lanza_error(self):
        """RN-1: producto es obligatorio → ValidationError en campo 'producto'."""
        ev = EventoSanitario(
            animal=self.animal_activo, tipo="Vacuna Aftosa",
            responsable="vet01", producto="",
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            ev.full_clean()
        self.assertIn("producto", ctx.exception.message_dict)

    # ── CP-MODEL-04 ──────────────────────────────────────────────────────────
    def test_rn2_animal_inactivo_lanza_error(self):
        """RN-2: animal INACTIVO → ValidationError en campo 'animal'. (CP-EV-05)"""
        ev = EventoSanitario(
            animal=self.animal_inactivo, tipo="Vacuna Aftosa",
            responsable="vet01", producto="Producto X",
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            ev.full_clean()
        self.assertIn("animal", ctx.exception.message_dict)

    # ── CP-MODEL-05 ──────────────────────────────────────────────────────────
    def test_rn2_animal_activo_permitido(self):
        """RN-2: animal ACTIVO → se guarda sin error."""
        ev = EventoSanitario(
            animal=self.animal_activo, tipo="Vacuna Aftosa",
            responsable="vet01", producto="Producto X",
            created_by=self.user,
        )
        ev.full_clean()
        ev.save()
        self.assertEqual(EventoSanitario.objects.filter(pk=ev.pk).count(), 1)

    # ── CP-MODEL-06 ──────────────────────────────────────────────────────────
    def test_rn2_animal_borrador_permitido(self):
        """RN-2: animal BORRADOR → se guarda sin error."""
        ev = EventoSanitario(
            animal=self.animal_borrador, tipo="Desparasitación",
            responsable="vet01", producto="Ivermectina",
            created_by=self.user,
        )
        ev.full_clean()
        ev.save()
        self.assertEqual(EventoSanitario.objects.filter(pk=ev.pk).count(), 1)

    # ── CP-MODEL-07 ──────────────────────────────────────────────────────────
    def test_rn4_nuevo_evento_en_estado_cancelado_lanza_error(self):
        """RN-4: nuevo evento con estado CANCELADO → ValidationError en campo 'estado'."""
        ev = EventoSanitario(
            animal=self.animal_activo, tipo="Vacuna Aftosa",
            responsable="vet01", producto="Producto X",
            estado=EventoSanitario.Estado.CANCELADO,
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            ev.full_clean()
        self.assertIn("estado", ctx.exception.message_dict)

    # ── CP-MODEL-08 ──────────────────────────────────────────────────────────
    def test_rn4_nuevo_evento_en_estado_realizado_lanza_error(self):
        """RN-4: nuevo evento con estado REALIZADO → ValidationError en campo 'estado'."""
        ev = EventoSanitario(
            animal=self.animal_activo, tipo="Vacuna Aftosa",
            responsable="vet01", producto="Producto X",
            estado=EventoSanitario.Estado.REALIZADO,
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            ev.full_clean()
        self.assertIn("estado", ctx.exception.message_dict)

    # ── CP-MODEL-09 ──────────────────────────────────────────────────────────
    def test_rn3_evento_cancelado_no_puede_modificarse(self):
        """RN-3: evento en estado CANCELADO → full_clean() lanza ValidationError."""
        ev = make_evento(self.animal_activo, self.user)
        ev.estado = EventoSanitario.Estado.CANCELADO
        ev.save(update_fields=["estado"])
        ev.tipo = "Otro tipo"
        with self.assertRaises(ValidationError):
            ev.full_clean()

    # ── CP-MODEL-10 ──────────────────────────────────────────────────────────
    def test_rn3_evento_realizado_no_puede_modificarse(self):
        """RN-3: evento en estado REALIZADO → full_clean() lanza ValidationError."""
        ev = make_evento(self.animal_activo, self.user)
        ev.estado = EventoSanitario.Estado.REALIZADO
        ev.save(update_fields=["estado"])
        ev.tipo = "Otro tipo"
        with self.assertRaises(ValidationError):
            ev.full_clean()

    # ── CP-MODEL-11 ──────────────────────────────────────────────────────────
    def test_puede_modificarse_true_para_confirmado_y_aplazado(self):
        """puede_modificarse retorna True para estados CONFIRMADO y APLAZADO."""
        ev = make_evento(self.animal_activo, self.user)
        self.assertTrue(ev.puede_modificarse)
        ev.estado = EventoSanitario.Estado.APLAZADO
        self.assertTrue(ev.puede_modificarse)

    # ── CP-MODEL-12 ──────────────────────────────────────────────────────────
    def test_puede_modificarse_false_para_cancelado_y_realizado(self):
        """puede_modificarse retorna False para estados CANCELADO y REALIZADO."""
        ev = make_evento(self.animal_activo, self.user)
        ev.estado = EventoSanitario.Estado.CANCELADO
        self.assertFalse(ev.puede_modificarse)
        ev.estado = EventoSanitario.Estado.REALIZADO
        self.assertFalse(ev.puede_modificarse)

    # ── CP-MODEL-13 ──────────────────────────────────────────────────────────
    def test_es_correccion_true_con_original(self):
        """es_correccion retorna True cuando el evento tiene evento_original."""
        original = make_evento(self.animal_activo, self.user)
        correccion = make_evento(
            self.animal_activo, self.user,
            tipo="Corrección Vacuna", evento_original=original,
        )
        self.assertTrue(correccion.es_correccion)

    # ── CP-MODEL-14 ──────────────────────────────────────────────────────────
    def test_es_correccion_false_sin_original(self):
        """es_correccion retorna False cuando el evento no tiene evento_original."""
        ev = make_evento(self.animal_activo, self.user)
        self.assertFalse(ev.es_correccion)

    # ── CP-MODEL-15 ──────────────────────────────────────────────────────────
    def test_estado_por_defecto_es_confirmado(self):
        """El estado por defecto de un nuevo evento es CONFIRMADO."""
        ev = make_evento(self.animal_activo, self.user)
        self.assertEqual(ev.estado, EventoSanitario.Estado.CONFIRMADO)

    # ── CP-MODEL-16 ──────────────────────────────────────────────────────────
    def test_str_muestra_tipo_y_fecha(self):
        """__str__ retorna '{tipo} · {fecha:%Y-%m-%d}'."""
        ev = make_evento(self.animal_activo, self.user, tipo="Vacuna Brucelosis")
        self.assertIn("Vacuna Brucelosis", str(ev))
        self.assertIn(str(ev.fecha.year), str(ev))


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – RBAC y Control de Acceso
# ─────────────────────────────────────────────────────────────────────────────

class EventoRBACTests(TestCase):
    """
    Valida que @login_required + @require_perm restringen el acceso
    según los permisos eventos.read y eventos.write.
    """

    def setUp(self):
        self.potrero = make_potrero("P-RBAC")
        self.animal = make_animal(self.potrero, rfid="COL-RBAC-001")
        self.admin = make_user("admin_rbac")

        self.evento = make_evento(self.animal, self.admin)

        self.user_read = make_user("user_read")
        grant_perm(self.user_read, "eventos.read")

        self.user_write = make_user("user_write")
        grant_perm(self.user_write, "eventos.read")
        grant_perm(self.user_write, "eventos.write")

        self.user_sin = make_user("user_sin")

    # ── CP-RBAC-01 ───────────────────────────────────────────────────────────
    def test_list_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("eventos:list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-02 ───────────────────────────────────────────────────────────
    def test_detail_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("eventos:detail", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-03 ───────────────────────────────────────────────────────────
    def test_create_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("eventos:create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-04 ───────────────────────────────────────────────────────────
    def test_list_sin_permiso_read_retorna_403(self):
        self.client.login(username="user_sin", password="testpass123")
        r = self.client.get(reverse("eventos:list"))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-05 ───────────────────────────────────────────────────────────
    def test_detail_sin_permiso_read_retorna_403(self):
        self.client.login(username="user_sin", password="testpass123")
        r = self.client.get(reverse("eventos:detail", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-06 ───────────────────────────────────────────────────────────
    def test_create_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.get(reverse("eventos:create"))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-07 ───────────────────────────────────────────────────────────
    def test_correccion_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.get(reverse("eventos:correccion", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-08 ───────────────────────────────────────────────────────────
    def test_cancelar_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.post(reverse("eventos:cancelar", args=[self.evento.pk]),
                             {"motivo": "test"})
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-09 ───────────────────────────────────────────────────────────
    def test_realizar_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.post(reverse("eventos:realizar", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-10 ───────────────────────────────────────────────────────────
    def test_solo_read_puede_listar_y_ver_pero_no_crear(self):
        self.client.login(username="user_read", password="testpass123")
        self.assertEqual(self.client.get(reverse("eventos:list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("eventos:detail", args=[self.evento.pk])).status_code, 200
        )
        self.assertEqual(self.client.get(reverse("eventos:create")).status_code, 403)

    # ── CP-RBAC-11 ───────────────────────────────────────────────────────────
    def test_write_puede_acceder_a_create_y_correccion(self):
        self.client.login(username="user_write", password="testpass123")
        self.assertEqual(self.client.get(reverse("eventos:create")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("eventos:correccion", args=[self.evento.pk])).status_code, 200
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – Vistas (comportamiento funcional)
# ─────────────────────────────────────────────────────────────────────────────

class EventoVistaTests(TestCase):
    """
    Prueba el comportamiento funcional de todas las vistas del módulo
    de eventos: listado, filtros, creación, detalle, corrección,
    cancelación y realización.
    """

    def setUp(self):
        self.potrero = make_potrero("P1")
        self.potrero2 = make_potrero("P2")

        self.user = make_user("operario")
        grant_perm(self.user, "eventos.read")
        grant_perm(self.user, "eventos.write")
        self.client.login(username="operario", password="testpass123")

        self.animal = make_animal(self.potrero, rfid="COL-VIS-001")
        self.animal2 = make_animal(self.potrero2, rfid="COL-VIS-002")
        self.animal_ina = make_animal(self.potrero, rfid="COL-VIS-INA",
                                      estado=Animal.Estado.INACTIVO)

        self.evento = make_evento(self.animal, self.user, tipo="Vacuna Aftosa")

    def _post_create(self, **overrides):
        data = {
            "animal": self.animal.pk,
            "tipo": "Desparasitación",
            "fecha": "2026-04-12",
            "responsable": "veterinario01",
            "producto": "Ivermectina",
            "dosis": "2ml",
            "lote": "LOT-001",
            "via_aplicacion": "Subcutánea",
            "notas": "",
        }
        data.update(overrides)
        return self.client.post(reverse("eventos:create"), data)

    # ── CP-VISTA-01 ──────────────────────────────────────────────────────────
    def test_list_sin_filtros_retorna_200(self):
        """GET /eventos/ → 200, evento de referencia aparece en page_obj."""
        r = self.client.get(reverse("eventos:list"))
        self.assertEqual(r.status_code, 200)
        pks = [e.pk for e in r.context["page_obj"].object_list]
        self.assertIn(self.evento.pk, pks)

    # ── CP-VISTA-02 ──────────────────────────────────────────────────────────
    def test_list_filtro_q_por_tipo(self):
        """GET ?q=Aftosa → solo retorna eventos con ese tipo."""
        make_evento(self.animal2, self.user, tipo="Desparasitación")
        r = self.client.get(reverse("eventos:list") + "?q=Aftosa")
        self.assertEqual(r.status_code, 200)
        tipos = [e.tipo for e in r.context["page_obj"].object_list]
        self.assertTrue(all("Aftosa" in t for t in tipos))

    # ── CP-VISTA-03 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_animal(self):
        """GET ?animal=<pk> → solo retorna eventos de ese animal."""
        make_evento(self.animal2, self.user, tipo="Otro evento")
        r = self.client.get(reverse("eventos:list") + f"?animal={self.animal.pk}")
        self.assertEqual(r.status_code, 200)
        for ev in r.context["page_obj"].object_list:
            self.assertEqual(ev.animal_id, self.animal.pk)

    # ── CP-VISTA-04 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_estado_cancelado(self):
        """GET ?estado=CAN → solo retorna eventos CANCELADOS."""
        self.evento.estado = EventoSanitario.Estado.CANCELADO
        self.evento.save(update_fields=["estado"])
        r = self.client.get(reverse("eventos:list") + "?estado=CAN")
        self.assertEqual(r.status_code, 200)
        for ev in r.context["page_obj"].object_list:
            self.assertEqual(ev.estado, EventoSanitario.Estado.CANCELADO)

    # ── CP-VISTA-05 ──────────────────────────────────────────────────────────
    def test_create_get_retorna_formulario_vacio(self):
        """GET /eventos/new/ sin ?animal= → 200, formulario vacío. (CP-EV-03)"""
        r = self.client.get(reverse("eventos:create"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)
        self.assertIsNone(r.context.get("animal_obj"))

    # ── CP-VISTA-06 ──────────────────────────────────────────────────────────
    def test_create_get_con_animal_precarga_contexto(self):
        """GET /eventos/new/?animal=<pk> → animal_obj en contexto. (CP-EV-02)"""
        r = self.client.get(reverse("eventos:create") + f"?animal={self.animal.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.context.get("animal_obj"))
        self.assertEqual(r.context["animal_obj"].pk, self.animal.pk)

    # ── CP-VISTA-07 ──────────────────────────────────────────────────────────
    def test_create_post_valido_crea_evento_confirmado(self):
        """POST válido → evento CONFIRMADO, created_by=user, redirige a detail. (CP-EV-01)"""
        count_antes = EventoSanitario.objects.count()
        r = self._post_create()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(EventoSanitario.objects.count(), count_antes + 1)
        nuevo = EventoSanitario.objects.latest("created_at")
        self.assertEqual(nuevo.estado, EventoSanitario.Estado.CONFIRMADO)
        self.assertEqual(nuevo.created_by, self.user)
        self.assertRedirects(r, reverse("eventos:detail", args=[nuevo.pk]))

    # ── CP-VISTA-08 ──────────────────────────────────────────────────────────
    def test_create_post_sin_datos_minimos_no_crea(self):
        """POST sin tipo, responsable ni producto → re-renderiza 200, sin evento nuevo. (CP-EV-04)"""
        count_antes = EventoSanitario.objects.count()
        r = self._post_create(tipo="", responsable="", producto="")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(EventoSanitario.objects.count(), count_antes)

    # ── CP-VISTA-09 ──────────────────────────────────────────────────────────
    def test_create_post_animal_inactivo_rechazado(self):
        """POST con animal INACTIVO → form rechaza (queryset excluye INACTIVO),
        re-renderiza 200, sin evento creado. (CP-EV-05)"""
        count_antes = EventoSanitario.objects.count()
        r = self._post_create(animal=self.animal_ina.pk)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(EventoSanitario.objects.count(), count_antes)

    # ── CP-VISTA-10 ──────────────────────────────────────────────────────────
    def test_detail_retorna_datos_del_evento(self):
        """GET /eventos/<pk>/ → 200, evento en contexto con correcciones."""
        r = self.client.get(reverse("eventos:detail", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["evento"].pk, self.evento.pk)
        self.assertIn("correcciones", r.context)
        self.assertIn("puede_modificarse", r.context)

    # ── CP-VISTA-11 ──────────────────────────────────────────────────────────
    def test_correccion_get_sobre_confirmado_retorna_200(self):
        """GET /eventos/<pk>/correccion/ sobre evento CONFIRMADO → 200, form precargado. (CP-EV-07)"""
        r = self.client.get(reverse("eventos:correccion", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)
        self.assertEqual(r.context["evento"].pk, self.evento.pk)
        self.assertEqual(r.context["form"].initial.get("tipo"), self.evento.tipo)

    # ── CP-VISTA-12 ──────────────────────────────────────────────────────────
    def test_correccion_get_sobre_aplazado_retorna_200(self):
        """GET /eventos/<pk>/correccion/ sobre evento APLAZADO → 200 (estado mutable)."""
        self.evento.estado = EventoSanitario.Estado.APLAZADO
        self.evento.save(update_fields=["estado"])
        r = self.client.get(reverse("eventos:correccion", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 200)

    # ── CP-VISTA-13 ──────────────────────────────────────────────────────────
    def test_correccion_get_sobre_cancelado_retorna_404(self):
        """GET correccion sobre evento CANCELADO → 404 (estado terminal, no mutable)."""
        self.evento.estado = EventoSanitario.Estado.CANCELADO
        self.evento.save(update_fields=["estado"])
        r = self.client.get(reverse("eventos:correccion", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 404)

    # ── CP-VISTA-14 ──────────────────────────────────────────────────────────
    def test_correccion_get_sobre_realizado_retorna_404(self):
        """GET correccion sobre evento REALIZADO → 404 (estado terminal, no mutable)."""
        self.evento.estado = EventoSanitario.Estado.REALIZADO
        self.evento.save(update_fields=["estado"])
        r = self.client.get(reverse("eventos:correccion", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 404)

    # ── CP-VISTA-15 ──────────────────────────────────────────────────────────
    def test_correccion_post_crea_evento_vinculado_y_original_intacto(self):
        """POST corrección válida → nuevo evento con evento_original,
        animal heredado, original sin modificar. (CP-EV-07)"""
        data = {
            "tipo": "Corrección Vacuna Aftosa",
            "fecha": "2026-04-12",
            "responsable": "veterinario02",
            "producto": "Aftovaxpur DOE v2",
            "dosis": "",
            "lote": "",
            "via_aplicacion": "",
            "notas": "Dosis corregida por error de registro",
        }
        r = self.client.post(reverse("eventos:correccion", args=[self.evento.pk]), data)
        self.assertEqual(r.status_code, 302)

        correccion = EventoSanitario.objects.latest("created_at")
        self.assertEqual(correccion.evento_original_id, self.evento.pk)
        self.assertEqual(correccion.animal_id, self.evento.animal_id)
        self.assertEqual(correccion.estado, EventoSanitario.Estado.CONFIRMADO)
        self.assertEqual(correccion.created_by, self.user)

        self.evento.refresh_from_db()
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.CONFIRMADO)
        self.assertEqual(self.evento.tipo, "Vacuna Aftosa")

    # ── CP-VISTA-16 ──────────────────────────────────────────────────────────
    def test_cancelar_post_cambia_estado_y_antepone_motivo(self):
        """POST /eventos/<pk>/cancelar/ con motivo → estado CANCELADO, motivo en notas."""
        r = self.client.post(
            reverse("eventos:cancelar", args=[self.evento.pk]),
            {"motivo": "Error de registro duplicado"},
        )
        self.assertEqual(r.status_code, 302)
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.CANCELADO)
        self.assertIn("Error de registro duplicado", self.evento.notas)

    # ── CP-VISTA-17 ──────────────────────────────────────────────────────────
    def test_cancelar_get_redirige_a_detail_sin_cambios(self):
        """GET /eventos/<pk>/cancelar/ → redirige a detail, estado no cambia."""
        r = self.client.get(reverse("eventos:cancelar", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("eventos:detail", args=[self.evento.pk]))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.CONFIRMADO)

    # ── CP-VISTA-18 ──────────────────────────────────────────────────────────
    def test_realizar_post_cambia_estado_a_realizado(self):
        """POST /eventos/<pk>/realizar/ → estado REALIZADO."""
        r = self.client.post(
            reverse("eventos:realizar", args=[self.evento.pk]),
            {"notas_cierre": "Aplicado sin incidentes"},
        )
        self.assertEqual(r.status_code, 302)
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.REALIZADO)
        self.assertIn("Aplicado sin incidentes", self.evento.notas)

    # ── CP-VISTA-19 ──────────────────────────────────────────────────────────
    def test_realizar_get_redirige_a_detail_sin_cambios(self):
        """GET /eventos/<pk>/realizar/ → redirige a detail, estado no cambia."""
        r = self.client.get(reverse("eventos:realizar", args=[self.evento.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(r, reverse("eventos:detail", args=[self.evento.pk]))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.CONFIRMADO)

    # ── CP-VISTA-20 ──────────────────────────────────────────────────────────
    def test_cancelar_sobre_evento_terminal_retorna_404(self):
        """POST cancelar sobre evento ya REALIZADO → 404 (no está en estado mutable)."""
        self.evento.estado = EventoSanitario.Estado.REALIZADO
        self.evento.save(update_fields=["estado"])
        r = self.client.post(
            reverse("eventos:cancelar", args=[self.evento.pk]),
            {"motivo": "Intento inválido"},
        )
        self.assertEqual(r.status_code, 404)

    # ── CP-VISTA-21 ──────────────────────────────────────────────────────────
    def test_realizar_sobre_evento_terminal_retorna_404(self):
        """POST realizar sobre evento ya CANCELADO → 404 (no está en estado mutable)."""
        self.evento.estado = EventoSanitario.Estado.CANCELADO
        self.evento.save(update_fields=["estado"])
        r = self.client.post(
            reverse("eventos:realizar", args=[self.evento.pk]),
        )
        self.assertEqual(r.status_code, 404)