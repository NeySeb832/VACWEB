# animals/tests.py
"""
Pruebas funcionales – CU-002: Gestionar CRUD de Animales
=========================================================
Bloque 1 – Modelo y Reglas de Negocio  (CP-MODEL-01 … CP-MODEL-11)
Bloque 2 – RBAC y Control de Acceso    (CP-RBAC-01  … CP-RBAC-10)
Bloque 3 – Vistas                      (CP-VISTA-01 … CP-VISTA-13)

Correspondencia con los CP del documento CU-002:
  CP-01 → CP-RBAC-01 + CP-VISTA-01
  CP-02 → CP-VISTA-06
  CP-03 → CP-MODEL-06
  CP-04 → CP-VISTA-06 (BORRADOR) + CP-VISTA-08 (ACTIVO inválido)
  CP-05 → CP-VISTA-11
  CP-06 → CP-MODEL-07
  CP-07 → CP-MODEL-11 + CP-VISTA-12 + CP-VISTA-13
  CP-08 → OMITIDO (módulo de transacciones no implementado aún)
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from authz.models import Permission, Role, RolePermission, UserRole
from .models import Animal, EventoSanitario, Movimiento, Pesaje, Potrero


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades compartidas
# ─────────────────────────────────────────────────────────────────────────────

def make_user(username: str, password: str = "testpass123") -> User:
    return User.objects.create_user(username=username, password=password)


def grant_perm(user: User, perm_code: str) -> None:
    """Asigna un permiso al usuario mediante un rol dedicado."""
    perm, _ = Permission.objects.get_or_create(code=perm_code)
    role, _ = Role.objects.get_or_create(name=perm_code, code=perm_code)
    RolePermission.objects.get_or_create(role=role, permission=perm)
    UserRole.objects.get_or_create(user=user, role=role)


def make_potrero(nombre: str = "P1", activo: bool = True) -> Potrero:
    return Potrero.objects.create(nombre=nombre, activo=activo)


def make_animal_activo(potrero: Potrero, rfid: str = "COL-1234567890", arete: str = "A-001") -> Animal:
    """Devuelve una instancia de Animal con datos mínimos para estado ACTIVO (sin guardar)."""
    return Animal(
        rfid=rfid,
        arete=arete,
        sexo=Animal.Sexo.MACHO,
        etapa=Animal.Etapa.LEVANTE,
        raza="Brahman",
        potrero=potrero,
        estado=Animal.Estado.ACTIVO,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Modelo y Reglas de Negocio
# ─────────────────────────────────────────────────────────────────────────────

class AnimalModelRNTests(TestCase):
    """
    Valida las reglas de negocio definidas en el modelo:
    RN-1 (inmutabilidad de identificadores con historial),
    RN-2 (datos mínimos para ACTIVO),
    RN-3 (baja lógica),
    RN-4 (potrero destino activo en movimientos).
    """

    def setUp(self):
        self.potrero = make_potrero("P1")

    # ── CP-MODEL-01 ──────────────────────────────────────────────────────────
    def test_activo_sin_identificador_lanza_error(self):
        """RN-2: estado ACTIVO sin RFID ni arete → ValidationError."""
        animal = Animal(
            sexo=Animal.Sexo.MACHO,
            etapa=Animal.Etapa.LEVANTE,
            potrero=self.potrero,
            estado=Animal.Estado.ACTIVO,
        )
        with self.assertRaises(ValidationError) as ctx:
            animal.full_clean()
        self.assertIn("RFID/Arete", str(ctx.exception))

    # ── CP-MODEL-02 ──────────────────────────────────────────────────────────
    def test_activo_sin_sexo_lanza_error(self):
        """RN-2: estado ACTIVO sin sexo → ValidationError."""
        animal = Animal(
            rfid="COL-001",
            etapa=Animal.Etapa.LEVANTE,
            potrero=self.potrero,
            estado=Animal.Estado.ACTIVO,
        )
        with self.assertRaises(ValidationError) as ctx:
            animal.full_clean()
        self.assertIn("Sexo", str(ctx.exception))

    # ── CP-MODEL-03 ──────────────────────────────────────────────────────────
    def test_activo_sin_etapa_lanza_error(self):
        """RN-2: estado ACTIVO sin etapa → ValidationError."""
        animal = Animal(
            rfid="COL-001",
            sexo=Animal.Sexo.MACHO,
            potrero=self.potrero,
            estado=Animal.Estado.ACTIVO,
        )
        with self.assertRaises(ValidationError) as ctx:
            animal.full_clean()
        self.assertIn("Etapa", str(ctx.exception))

    # ── CP-MODEL-04 ──────────────────────────────────────────────────────────
    def test_activo_sin_potrero_lanza_error(self):
        """RN-2: estado ACTIVO sin potrero → ValidationError."""
        animal = Animal(
            rfid="COL-001",
            sexo=Animal.Sexo.MACHO,
            etapa=Animal.Etapa.LEVANTE,
            estado=Animal.Estado.ACTIVO,
        )
        with self.assertRaises(ValidationError) as ctx:
            animal.full_clean()
        self.assertIn("Potrero", str(ctx.exception))

    # ── CP-MODEL-05 ──────────────────────────────────────────────────────────
    def test_borrador_sin_datos_minimos_se_guarda(self):
        """RN-2: estado BORRADOR sin datos mínimos → se guarda correctamente."""
        animal = Animal(estado=Animal.Estado.BORRADOR)
        animal.full_clean()  # no debe lanzar error
        animal.save()
        self.assertEqual(Animal.objects.filter(pk=animal.pk).count(), 1)

    # ── CP-MODEL-06 ──────────────────────────────────────────────────────────
    def test_rfid_duplicado_lanza_integrityerror(self):
        """Unicidad de RFID dentro del sistema → IntegrityError."""
        Animal.objects.create(rfid="COL-DUP-001", estado=Animal.Estado.BORRADOR)
        with self.assertRaises(IntegrityError):
            Animal.objects.create(rfid="COL-DUP-001", estado=Animal.Estado.BORRADOR)

    # ── CP-MODEL-07 ──────────────────────────────────────────────────────────
    def test_cambiar_rfid_con_historial_bloqueado(self):
        """RN-1: animal con historial (movimiento) → cambiar RFID lanza ValidationError."""
        animal = make_animal_activo(self.potrero, rfid="COL-HIST-001", arete="A-HIST-001")
        animal.save()
        potrero2 = make_potrero("P2")
        Movimiento.objects.create(
            animal=animal, desde=self.potrero, hacia=potrero2, responsable="tester"
        )
        animal.rfid = "COL-HIST-CAMBIADO"
        with self.assertRaises(ValidationError) as ctx:
            animal.full_clean()
        self.assertIn("rfid", ctx.exception.message_dict)

    # ── CP-MODEL-08 ──────────────────────────────────────────────────────────
    def test_cambiar_rfid_sin_historial_permitido(self):
        """RN-1: animal SIN historial → cambiar RFID permitido."""
        animal = make_animal_activo(self.potrero, rfid="COL-SIN-HIST", arete="A-SIN-HIST")
        animal.save()
        animal.rfid = "COL-SIN-HIST-NEW"
        animal.full_clean()  # no debe lanzar error
        animal.save()
        animal.refresh_from_db()
        self.assertEqual(animal.rfid, "COL-SIN-HIST-NEW")

    # ── CP-MODEL-09 ──────────────────────────────────────────────────────────
    def test_movimiento_potrero_destino_inactivo(self):
        """RN-4: movimiento hacia potrero inactivo → ValidationError."""
        animal = make_animal_activo(self.potrero)
        animal.save()
        potrero_inactivo = make_potrero("P-INACTIVO", activo=False)
        mov = Movimiento(
            animal=animal, desde=self.potrero, hacia=potrero_inactivo, responsable="tester"
        )
        with self.assertRaises(ValidationError):
            mov.full_clean()

    # ── CP-MODEL-10 ──────────────────────────────────────────────────────────
    def test_movimiento_origen_igual_destino(self):
        """RN-4: potrero origen igual a destino → ValidationError."""
        animal = make_animal_activo(self.potrero)
        animal.save()
        mov = Movimiento(
            animal=animal, desde=self.potrero, hacia=self.potrero, responsable="tester"
        )
        with self.assertRaises(ValidationError):
            mov.full_clean()

    # ── CP-MODEL-11 ──────────────────────────────────────────────────────────
    def test_baja_logica_no_elimina_registro(self):
        """RN-3: baja lógica → animal persiste en DB con estado INACTIVO y motivo guardado."""
        animal = make_animal_activo(self.potrero, rfid="COL-BAJA-001", arete="A-BAJA-001")
        animal.save()
        pk = animal.pk

        animal.estado = Animal.Estado.INACTIVO
        animal.motivo_baja = "Venta en pie"
        animal.save()

        recuperado = Animal.objects.get(pk=pk)
        self.assertEqual(recuperado.estado, Animal.Estado.INACTIVO)
        self.assertEqual(recuperado.motivo_baja, "Venta en pie")


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – RBAC y Control de Acceso
# ─────────────────────────────────────────────────────────────────────────────

class AnimalRBACTests(TestCase):
    """
    Valida que el decorador @require_perm restringe el acceso
    según el permiso (animals.read / animals.write) y el estado
    de autenticación del usuario.
    """

    def setUp(self):
        self.potrero = make_potrero("P-RBAC")
        self.animal = Animal.objects.create(
            rfid="COL-RBAC-001",
            arete="A-RBAC-001",
            sexo=Animal.Sexo.MACHO,
            etapa=Animal.Etapa.ADULTO,
            potrero=self.potrero,
            estado=Animal.Estado.ACTIVO,
        )

        # Usuario solo con lectura
        self.user_read = make_user("user_read")
        grant_perm(self.user_read, "animals.read")

        # Usuario con lectura y escritura
        self.user_write = make_user("user_write")
        grant_perm(self.user_write, "animals.read")
        grant_perm(self.user_write, "animals.write")

        # Usuario sin ningún permiso
        self.user_sin = make_user("user_sin_perms")

    # ── CP-RBAC-01 ───────────────────────────────────────────────────────────
    def test_list_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("animals:list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-02 ───────────────────────────────────────────────────────────
    def test_detail_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("animals:detail", args=[self.animal.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-03 ───────────────────────────────────────────────────────────
    def test_create_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("animals:create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-04 ───────────────────────────────────────────────────────────
    def test_list_sin_permiso_read_retorna_403(self):
        self.client.login(username="user_sin_perms", password="testpass123")
        r = self.client.get(reverse("animals:list"))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-05 ───────────────────────────────────────────────────────────
    def test_detail_sin_permiso_read_retorna_403(self):
        self.client.login(username="user_sin_perms", password="testpass123")
        r = self.client.get(reverse("animals:detail", args=[self.animal.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-06 ───────────────────────────────────────────────────────────
    def test_create_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.get(reverse("animals:create"))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-07 ───────────────────────────────────────────────────────────
    def test_update_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.get(reverse("animals:update", args=[self.animal.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-08 ───────────────────────────────────────────────────────────
    def test_baja_sin_permiso_write_retorna_403(self):
        self.client.login(username="user_read", password="testpass123")
        r = self.client.get(reverse("animals:baja", args=[self.animal.pk]))
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-09 ───────────────────────────────────────────────────────────
    def test_solo_read_puede_listar_y_ver_pero_no_escribir(self):
        self.client.login(username="user_read", password="testpass123")
        self.assertEqual(self.client.get(reverse("animals:list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("animals:detail", args=[self.animal.pk])).status_code, 200
        )
        self.assertEqual(self.client.get(reverse("animals:create")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("animals:update", args=[self.animal.pk])).status_code, 403
        )

    # ── CP-RBAC-10 ───────────────────────────────────────────────────────────
    def test_write_puede_acceder_a_todos_los_formularios(self):
        self.client.login(username="user_write", password="testpass123")
        self.assertEqual(self.client.get(reverse("animals:create")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("animals:update", args=[self.animal.pk])).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("animals:baja", args=[self.animal.pk])).status_code, 200
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – Vistas (comportamiento funcional)
# ─────────────────────────────────────────────────────────────────────────────

class AnimalVistaTests(TestCase):
    """
    Prueba el comportamiento de las vistas: listado con filtros,
    creación, detalle, edición y baja lógica.
    """

    def setUp(self):
        self.potrero = make_potrero("P1")
        self.potrero2 = make_potrero("P2")

        self.user = make_user("operario")
        grant_perm(self.user, "animals.read")
        grant_perm(self.user, "animals.write")
        self.client.login(username="operario", password="testpass123")

        # Animal de referencia reutilizado en varias pruebas
        self.animal = Animal.objects.create(
            rfid="COL-REF-001",
            arete="A-REF-001",
            sexo=Animal.Sexo.MACHO,
            etapa=Animal.Etapa.LEVANTE,
            raza="Brahman",
            potrero=self.potrero,
            estado=Animal.Estado.ACTIVO,
        )

    # ── CP-VISTA-01 ──────────────────────────────────────────────────────────
    def test_list_sin_filtros_retorna_200(self):
        """GET /animals/ → 200 y el animal de referencia aparece en la lista."""
        r = self.client.get(reverse("animals:list"))
        self.assertEqual(r.status_code, 200)
        pks = [a.pk for a in r.context["page_obj"].object_list]
        self.assertIn(self.animal.pk, pks)

    # ── CP-VISTA-02 ──────────────────────────────────────────────────────────
    def test_list_filtro_q_por_rfid(self):
        """GET ?q=COL-REF-001 → solo retorna el animal con ese RFID."""
        Animal.objects.create(rfid="COL-OTRO-999", estado=Animal.Estado.BORRADOR)
        r = self.client.get(reverse("animals:list") + "?q=COL-REF-001")
        self.assertEqual(r.status_code, 200)
        ids = [a.pk for a in r.context["page_obj"].object_list]
        self.assertIn(self.animal.pk, ids)
        self.assertEqual(len(ids), 1)

    # ── CP-VISTA-03 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_estado_activo(self):
        """GET ?estado=ACT → todos los resultados tienen estado ACTIVO."""
        Animal.objects.create(rfid="COL-BOR-001", estado=Animal.Estado.BORRADOR)
        r = self.client.get(reverse("animals:list") + "?estado=ACT")
        self.assertEqual(r.status_code, 200)
        for a in r.context["page_obj"].object_list:
            self.assertEqual(a.estado, Animal.Estado.ACTIVO)

    # ── CP-VISTA-04 ──────────────────────────────────────────────────────────
    def test_list_filtro_por_potrero(self):
        """GET ?lote=<id> → todos los resultados pertenecen a ese potrero."""
        Animal.objects.create(
            rfid="COL-P2-001",
            arete="A-P2-001",
            sexo=Animal.Sexo.HEMBRA,
            etapa=Animal.Etapa.ADULTO,
            potrero=self.potrero2,
            estado=Animal.Estado.ACTIVO,
        )
        r = self.client.get(reverse("animals:list") + f"?lote={self.potrero.pk}")
        self.assertEqual(r.status_code, 200)
        for a in r.context["page_obj"].object_list:
            self.assertEqual(a.potrero_id, self.potrero.pk)

    # ── CP-VISTA-05 ──────────────────────────────────────────────────────────
    def test_create_get_retorna_formulario_vacio(self):
        """GET /animals/new/ → 200, contexto contiene form y is_create=True."""
        r = self.client.get(reverse("animals:create"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)
        self.assertTrue(r.context["is_create"])

    # ── CP-VISTA-06 ──────────────────────────────────────────────────────────
    def test_create_post_valido_borrador_crea_animal(self):
        """
        POST con datos válidos y estado BORRADOR → animal creado,
        redirige al detalle. Corresponde a CP-02 y CP-04 del documento.
        """
        data = {
            "rfid": "COL-NEW-001",
            "arete": "A-NEW-001",
            "sexo": Animal.Sexo.MACHO,
            "etapa": Animal.Etapa.TERNERO,
            "raza": "Angus",
            "potrero": self.potrero.pk,
            "estado": Animal.Estado.BORRADOR,
            "motivo_baja": "",
        }
        r = self.client.post(reverse("animals:create"), data)
        self.assertEqual(r.status_code, 302)
        nuevo = Animal.objects.get(rfid="COL-NEW-001")
        self.assertEqual(nuevo.estado, Animal.Estado.BORRADOR)
        self.assertRedirects(r, reverse("animals:detail", args=[nuevo.pk]))

    # ── CP-VISTA-07 ──────────────────────────────────────────────────────────
    def test_create_post_con_peso_inicial_crea_pesaje(self):
        """POST con peso_inicial → se crea un Pesaje asociado al animal nuevo."""
        data = {
            "rfid": "COL-PESO-001",
            "arete": "A-PESO-001",
            "sexo": Animal.Sexo.MACHO,
            "etapa": Animal.Etapa.LEVANTE,
            "raza": "Brahman",
            "potrero": self.potrero.pk,
            "estado": Animal.Estado.ACTIVO,
            "motivo_baja": "",
            "peso_inicial": "254.50",
        }
        self.client.post(reverse("animals:create"), data)
        animal = Animal.objects.get(rfid="COL-PESO-001")
        self.assertEqual(animal.pesajes.count(), 1)
        self.assertEqual(animal.pesajes.first().peso_kg, Decimal("254.50"))

    # ── CP-VISTA-08 ──────────────────────────────────────────────────────────
    def test_create_post_activo_sin_datos_minimos_no_crea(self):
        """
        POST con estado ACTIVO pero sin identificadores → re-renderiza (200),
        no crea ningún animal. Corresponde a CP-04 del documento.
        """
        count_antes = Animal.objects.count()
        data = {
            "rfid": "",
            "arete": "",
            "sexo": "",
            "etapa": "",
            "raza": "",
            "potrero": "",
            "estado": Animal.Estado.ACTIVO,
            "motivo_baja": "",
        }
        r = self.client.post(reverse("animals:create"), data)
        self.assertEqual(r.status_code, 200)  # re-render con errores
        self.assertEqual(Animal.objects.count(), count_antes)

    # ── CP-VISTA-09 ──────────────────────────────────────────────────────────
    def test_detail_retorna_datos_del_animal(self):
        """GET /animals/<pk>/ → 200, contexto contiene el animal correcto."""
        r = self.client.get(reverse("animals:detail", args=[self.animal.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["animal"].pk, self.animal.pk)

    # ── CP-VISTA-10 ──────────────────────────────────────────────────────────
    def test_update_get_carga_formulario_con_datos(self):
        """GET /animals/<pk>/edit/ → 200, formulario cargado con la instancia del animal."""
        r = self.client.get(reverse("animals:update", args=[self.animal.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["form"].instance.pk, self.animal.pk)

    # ── CP-VISTA-11 ──────────────────────────────────────────────────────────
    def test_update_post_valido_actualiza_animal_y_last_modified_by(self):
        """
        POST con datos válidos → redirige, etapa actualizada,
        last_modified_by apunta al usuario que hizo el cambio.
        Corresponde a CP-05 del documento.
        """
        data = {
            "rfid": "COL-REF-001",
            "arete": "A-REF-001",
            "sexo": Animal.Sexo.MACHO,
            "etapa": Animal.Etapa.NOVILLO,  # cambio respecto al setUp
            "raza": "Brahman",
            "potrero": self.potrero.pk,
            "estado": Animal.Estado.ACTIVO,
            "motivo_baja": "",
        }
        r = self.client.post(reverse("animals:update", args=[self.animal.pk]), data)
        self.assertEqual(r.status_code, 302)
        self.animal.refresh_from_db()
        self.assertEqual(self.animal.etapa, Animal.Etapa.NOVILLO)
        self.assertEqual(self.animal.last_modified_by, self.user)

    # ── CP-VISTA-12 ──────────────────────────────────────────────────────────
    def test_baja_get_muestra_pantalla_confirmacion(self):
        """GET /animals/<pk>/baja/ → 200, contexto contiene el animal."""
        r = self.client.get(reverse("animals:baja", args=[self.animal.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["animal"].pk, self.animal.pk)

    # ── CP-VISTA-13 ──────────────────────────────────────────────────────────
    def test_baja_post_cambia_estado_a_inactivo_con_motivo(self):
        """
        POST /animals/<pk>/baja/ con motivo → estado INACTIVO,
        motivo_baja guardado, registro persiste en DB.
        Corresponde a CP-07 del documento.
        """
        r = self.client.post(
            reverse("animals:baja", args=[self.animal.pk]),
            {"motivo_baja": "Venta en pie"},
        )
        self.assertEqual(r.status_code, 302)
        self.animal.refresh_from_db()
        self.assertEqual(self.animal.estado, Animal.Estado.INACTIVO)
        self.assertEqual(self.animal.motivo_baja, "Venta en pie")
        # Verificación explícita de baja lógica: el registro sigue existiendo
        self.assertTrue(Animal.objects.filter(pk=self.animal.pk).exists())