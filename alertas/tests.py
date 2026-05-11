# alertas/tests.py
"""
Pruebas funcionales – CU-008: Sistema de Alertas Automáticas
=============================================================
Bloque 1 – Modelo y Reglas de Negocio   (CP-MODEL-01 … CP-MODEL-08)
Bloque 2 – Services (evaluadores)       (CP-SVC-01   … CP-SVC-12)
Bloque 3 – Señales (integración)        (CP-SENAL-01 … CP-SENAL-02)
Bloque 4 – RBAC y Control de Acceso     (CP-RBAC-01  … CP-RBAC-10)
Bloque 5 – Vistas (comportamiento)      (CP-VISTA-01 … CP-VISTA-14)
"""

import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from animals.models import Animal
from authz.models import Permission, Role, RolePermission, UserRole
from eventos.models import EventoSanitario
from pesajes.models import Pesaje
from potreros.models import Potrero

from .models import Alerta, ReglaAlerta
from .services import (
    evaluar_inventario_borrador,
    evaluar_inventario_sin_potrero,
    evaluar_potrero_capacidad,
    evaluar_productiva_sin_pesaje,
    evaluar_productiva_variacion_peso,
    evaluar_sanitaria_proxima_vacuna,
    evaluar_sanitaria_vacuna_vencida,
)


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


def make_potrero(nombre: str = "P-ALT-01", capacidad: int = 10) -> Potrero:
    return Potrero.objects.create(
        nombre_codigo=nombre,
        estado="ACTIVO",
        area_ha="5.00",
        capacidad_maxima=capacidad,
        tipo_uso="CEBA",
    )


def make_animal(potrero=None, rfid: str = "COL-ALT-001",
                estado: str = Animal.Estado.ACTIVO) -> Animal:
    return Animal.objects.create(
        rfid=rfid,
        nombre=f"Animal-{rfid}",
        sexo=Animal.Sexo.MACHO,
        etapa=Animal.Etapa.LEVANTE,
        potrero=potrero,
        estado=estado,
    )


def make_evento(animal: Animal, user: User, **kwargs) -> EventoSanitario:
    defaults = {
        "tipo": "Vacuna Aftosa",
        "responsable": "vet01",
        "producto": "Aftovaxpur",
        "estado": EventoSanitario.Estado.CONFIRMADO,
        "created_by": user,
        "fecha": HOY,
    }
    defaults.update(kwargs)
    return EventoSanitario.objects.create(animal=animal, **defaults)


def make_alerta(tipo: str = "sanitaria", mensaje: str = "Alerta de prueba",
                evento: EventoSanitario = None) -> Alerta:
    return Alerta.objects.create(
        tipo=tipo,
        mensaje=mensaje,
        origen="test",
        evento_sanitario=evento,
    )


def make_regla(tipo: str, subtipo: str, umbral: float = 7.0,
               unidad: str = "dias", activa: bool = True) -> ReglaAlerta:
    regla, _ = ReglaAlerta.objects.get_or_create(
        tipo=tipo,
        subtipo=subtipo,
        defaults={
            "umbral_valor": umbral,
            "umbral_unidad": unidad,
            "activa": activa,
            "descripcion": f"Regla {tipo}/{subtipo} para tests",
        },
    )
    return regla


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 1 – Modelo y Reglas de Negocio
# ─────────────────────────────────────────────────────────────────────────────

class AlertaModelTests(TestCase):
    """
    Valida el modelo Alerta: creación, reglas de estado unidireccional
    (RN-4 del modelo), método atender() y propagación al EventoSanitario.
    """

    def setUp(self):
        self.user = make_user("vet_model")
        self.potrero = make_potrero()
        self.animal = make_animal(self.potrero, rfid="COL-M-001")
        self.evento = make_evento(self.animal, self.user, fecha=MANANA)

    # ── CP-MODEL-01 ──────────────────────────────────────────────────────────
    def test_alerta_se_crea_con_datos_minimos(self):
        """Una Alerta con tipo, mensaje y origen se persiste correctamente."""
        a = make_alerta(tipo="sanitaria")
        self.assertIsNotNone(a.pk)
        self.assertEqual(a.estado, Alerta.Estado.PENDIENTE)
        self.assertIsNone(a.atendida_por)

    # ── CP-MODEL-02 ──────────────────────────────────────────────────────────
    def test_estado_no_puede_revertir_de_atendida_a_pendiente(self):
        """RN-4: cambiar estado de ATENDIDA a PENDIENTE lanza ValidationError."""
        a = make_alerta()
        a.estado = Alerta.Estado.ATENDIDA
        a.atendida_por = self.user
        a.fecha_atencion = timezone.now()
        a.save()

        a.estado = Alerta.Estado.PENDIENTE
        with self.assertRaises(ValidationError):
            a.full_clean()

    # ── CP-MODEL-03 ──────────────────────────────────────────────────────────
    def test_atender_registra_usuario_fecha_y_observacion(self):
        """atender() actualiza estado, atendida_por, fecha_atencion y observacion_atencion."""
        a = make_alerta()
        a.atender(self.user, "Vacuna aplicada sin incidentes")

        a.refresh_from_db()
        self.assertEqual(a.estado, Alerta.Estado.ATENDIDA)
        self.assertEqual(a.atendida_por, self.user)
        self.assertIsNotNone(a.fecha_atencion)
        self.assertEqual(a.observacion_atencion, "Vacuna aplicada sin incidentes")

    # ── CP-MODEL-04 ──────────────────────────────────────────────────────────
    def test_atender_marca_evento_sanitario_como_realizado(self):
        """atender() con evento_sanitario vinculado → evento queda en REALIZADO."""
        a = make_alerta(evento=self.evento)
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.CONFIRMADO)

        a.atender(self.user)

        self.evento.refresh_from_db()
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.REALIZADO)

    # ── CP-MODEL-05 ──────────────────────────────────────────────────────────
    def test_atender_no_falla_si_evento_ya_esta_en_terminal(self):
        """atender() no lanza error si el evento ya está en estado terminal (REALIZADO)."""
        self.evento.estado = EventoSanitario.Estado.REALIZADO
        self.evento.save(update_fields=["estado"])

        a = make_alerta(evento=self.evento)
        try:
            a.atender(self.user)
        except Exception as exc:
            self.fail(f"atender() lanzó excepción inesperada: {exc}")

        a.refresh_from_db()
        self.assertEqual(a.estado, Alerta.Estado.ATENDIDA)

    # ── CP-MODEL-06 ──────────────────────────────────────────────────────────
    def test_atender_sin_evento_vinculado_funciona(self):
        """atender() sin evento_sanitario no lanza error."""
        a = make_alerta(evento=None)
        try:
            a.atender(self.user, "Sin evento asociado")
        except Exception as exc:
            self.fail(f"atender() lanzó excepción inesperada: {exc}")
        a.refresh_from_db()
        self.assertEqual(a.estado, Alerta.Estado.ATENDIDA)

    # ── CP-MODEL-07 ──────────────────────────────────────────────────────────
    def test_str_muestra_tipo_y_mensaje(self):
        """__str__ incluye tipo y los primeros caracteres del mensaje."""
        a = make_alerta(tipo="productiva", mensaje="Variación de peso significativa en Animal-01")
        self.assertIn("productiva", str(a))
        self.assertIn("Variación", str(a))

    # ── CP-MODEL-08 ──────────────────────────────────────────────────────────
    def test_regla_alerta_str_muestra_tipo_subtipo_umbral(self):
        """ReglaAlerta.__str__ incluye tipo, subtipo y umbral."""
        regla = make_regla("sanitaria", "proxima_vacuna", umbral=7.0, unidad="dias")
        s = str(regla)
        self.assertIn("sanitaria", s.lower())
        self.assertIn("proxima_vacuna", s)
        self.assertIn("7.0", s)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 2 – Services (evaluadores)
# ─────────────────────────────────────────────────────────────────────────────

class AlertaServicesTests(TestCase):
    """
    Valida las funciones de services.py: generación correcta de alertas,
    filtrado por umbral, idempotencia (no duplicados) y FK al evento.
    """

    def setUp(self):
        self.user = make_user("vet_svc")
        self.potrero = make_potrero("P-SVC-01", capacidad=2)
        self.animal = make_animal(self.potrero, rfid="COL-SVC-001")

    # ── CP-SVC-01 ────────────────────────────────────────────────────────────
    def test_proxima_vacuna_genera_alerta_dentro_del_umbral(self):
        """Evento confirmado en los próximos 7 días → genera 1 alerta."""
        make_regla("sanitaria", "proxima_vacuna", umbral=7.0)
        make_evento(self.animal, self.user, fecha=HOY + timedelta(days=4))
        # La señal ya creó la alerta al guardar el evento; la borramos para
        # probar el servicio de forma aislada.
        Alerta.objects.all().delete()

        n = evaluar_sanitaria_proxima_vacuna()

        self.assertEqual(n, 1)
        a = Alerta.objects.get(tipo="sanitaria")
        self.assertIsNotNone(a.evento_sanitario_id)
        self.assertEqual(a.tipo_entidad, "animal")

    # ── CP-SVC-02 ────────────────────────────────────────────────────────────
    def test_proxima_vacuna_no_genera_alerta_fuera_del_umbral(self):
        """Evento confirmado a más de 7 días → no genera alerta."""
        make_regla("sanitaria", "proxima_vacuna", umbral=7.0)
        make_evento(self.animal, self.user, fecha=HOY + timedelta(days=10))

        n = evaluar_sanitaria_proxima_vacuna()

        self.assertEqual(n, 0)
        self.assertFalse(Alerta.objects.filter(tipo="sanitaria").exists())

    # ── CP-SVC-03 ────────────────────────────────────────────────────────────
    def test_proxima_vacuna_es_idempotente(self):
        """Llamar evaluar dos veces con el mismo evento no duplica la alerta."""
        make_regla("sanitaria", "proxima_vacuna", umbral=7.0)
        make_evento(self.animal, self.user, fecha=HOY + timedelta(days=3))

        evaluar_sanitaria_proxima_vacuna()
        n2 = evaluar_sanitaria_proxima_vacuna()

        self.assertEqual(n2, 0)
        self.assertEqual(Alerta.objects.filter(tipo="sanitaria").count(), 1)

    # ── CP-SVC-04 ────────────────────────────────────────────────────────────
    def test_proxima_vacuna_vincula_fk_al_evento(self):
        """La alerta generada tiene evento_sanitario apuntando al EventoSanitario correcto."""
        make_regla("sanitaria", "proxima_vacuna", umbral=7.0)
        ev = make_evento(self.animal, self.user, fecha=HOY + timedelta(days=2))

        evaluar_sanitaria_proxima_vacuna()

        a = Alerta.objects.get(tipo="sanitaria")
        self.assertEqual(a.evento_sanitario_id, ev.pk)

    # ── CP-SVC-05 ────────────────────────────────────────────────────────────
    def test_vacuna_vencida_genera_alerta_para_evento_pasado(self):
        """Evento CON con fecha pasada que no fue realizado → genera alerta."""
        make_regla("sanitaria", "vacuna_vencida", umbral=0.0)
        ev = make_evento(self.animal, self.user, fecha=AYER)
        # La señal ya generó la alerta al guardar el evento vencido.
        Alerta.objects.all().delete()

        n = evaluar_sanitaria_vacuna_vencida()

        self.assertEqual(n, 1)
        a = Alerta.objects.get(tipo="sanitaria")
        self.assertEqual(a.evento_sanitario_id, ev.pk)

    # ── CP-SVC-06 ────────────────────────────────────────────────────────────
    def test_vacuna_vencida_no_genera_alerta_para_evento_futuro(self):
        """Evento CON con fecha futura no cuenta como vencido."""
        make_regla("sanitaria", "vacuna_vencida", umbral=0.0)
        make_evento(self.animal, self.user, fecha=MANANA)

        n = evaluar_sanitaria_vacuna_vencida()

        self.assertEqual(n, 0)

    # ── CP-SVC-07 ────────────────────────────────────────────────────────────
    def test_variacion_peso_genera_alerta_cuando_supera_umbral(self):
        """Dos pesajes con variación > 10% → genera 1 alerta productiva."""
        make_regla("productiva", "variacion_peso", umbral=10.0, unidad="porcentaje")
        Pesaje.objects.create(animal=self.animal, fecha=AYER - timedelta(days=5),
                              peso_kg="100.00")
        Pesaje.objects.create(animal=self.animal, fecha=AYER, peso_kg="120.00")
        # La señal del segundo pesaje ya generó la alerta; borramos para
        # probar el servicio de forma aislada.
        Alerta.objects.all().delete()

        n = evaluar_productiva_variacion_peso()

        self.assertEqual(n, 1)
        self.assertTrue(Alerta.objects.filter(tipo="productiva",
                                               mensaje__icontains="variación").exists())

    # ── CP-SVC-08 ────────────────────────────────────────────────────────────
    def test_variacion_peso_no_genera_alerta_cuando_es_menor_al_umbral(self):
        """Variación de peso <= 10% → no genera alerta."""
        make_regla("productiva", "variacion_peso", umbral=10.0, unidad="porcentaje")
        Pesaje.objects.create(animal=self.animal, fecha=AYER - timedelta(days=5),
                              peso_kg="100.00")
        Pesaje.objects.create(animal=self.animal, fecha=AYER, peso_kg="105.00")

        n = evaluar_productiva_variacion_peso()

        self.assertEqual(n, 0)

    # ── CP-SVC-09 ────────────────────────────────────────────────────────────
    def test_sin_pesaje_genera_alerta_para_animal_sin_registro_reciente(self):
        """Animal activo sin pesaje en los últimos 30 días → genera alerta."""
        make_regla("productiva", "sin_pesaje", umbral=30.0)

        n = evaluar_productiva_sin_pesaje()

        self.assertEqual(n, 1)
        self.assertTrue(Alerta.objects.filter(tipo="productiva",
                                               mensaje__icontains="Sin pesaje").exists())

    # ── CP-SVC-10 ────────────────────────────────────────────────────────────
    def test_potrero_capacidad_genera_alerta_cuando_supera_umbral(self):
        """Potrero con capacidad=2 y 2 animales activos (100%) >= 90% → alerta."""
        make_regla("potrero", "capacidad", umbral=90.0, unidad="porcentaje")
        make_animal(self.potrero, rfid="COL-SVC-002")

        n = evaluar_potrero_capacidad()

        self.assertEqual(n, 1)
        self.assertTrue(Alerta.objects.filter(tipo="potrero").exists())

    # ── CP-SVC-11 ────────────────────────────────────────────────────────────
    def test_inventario_sin_potrero_genera_alerta_para_animal_activo(self):
        """Animal ACTIVO sin potrero asignado → genera alerta de inventario."""
        make_regla("inventario", "sin_potrero", umbral=0.0, unidad="activo")
        animal_sin_potrero = make_animal(potrero=None, rfid="COL-SVC-NOPTR")
        # La señal ya generó la alerta al guardar el animal sin potrero.
        Alerta.objects.all().delete()

        n = evaluar_inventario_sin_potrero()

        self.assertEqual(n, 1)
        a = Alerta.objects.get(tipo="inventario", mensaje__icontains="Sin potrero")
        self.assertEqual(a.id_entidad_referencia, str(animal_sin_potrero.pk))

    # ── CP-SVC-12 ────────────────────────────────────────────────────────────
    def test_inventario_borrador_genera_alerta_tras_n_dias(self):
        """Animal en BORRADOR con created_at hace 5 días y umbral=3 → genera alerta."""
        make_regla("inventario", "borrador", umbral=3.0)
        animal_bor = make_animal(potrero=self.potrero, rfid="COL-SVC-BOR",
                                 estado=Animal.Estado.BORRADOR)
        # Retrofechar created_at para superar el umbral (compara datetime, no date)
        Animal.objects.filter(pk=animal_bor.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )
        # La señal al crear no disparó alerta (animal recién creado, created_at=now).
        # Borramos cualquier alerta residual y probamos el servicio.
        Alerta.objects.all().delete()

        n = evaluar_inventario_borrador()

        self.assertEqual(n, 1)
        self.assertTrue(Alerta.objects.filter(tipo="inventario",
                                               mensaje__icontains="borrador").exists())


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 3 – Señales (integración)
# ─────────────────────────────────────────────────────────────────────────────

class AlertaSenalesTests(TestCase):
    """
    Verifica que las señales post_save disparan la evaluación de alertas
    automáticamente al guardar registros en otros módulos.
    """

    def setUp(self):
        self.user = make_user("vet_senal")
        self.potrero = make_potrero("P-SEN-01")
        self.animal = make_animal(self.potrero, rfid="COL-SEN-001")

    # ── CP-SENAL-01 ──────────────────────────────────────────────────────────
    def test_guardar_evento_dentro_del_umbral_dispara_alerta(self):
        """Crear EventoSanitario con fecha dentro del umbral activa la señal y genera alerta."""
        make_regla("sanitaria", "proxima_vacuna", umbral=7.0)

        make_evento(self.animal, self.user, fecha=HOY + timedelta(days=3))

        self.assertEqual(Alerta.objects.filter(tipo="sanitaria").count(), 1)

    # ── CP-SENAL-02 ──────────────────────────────────────────────────────────
    def test_guardar_evento_fuera_del_umbral_no_genera_alerta(self):
        """EventoSanitario con fecha fuera del umbral → señal se dispara pero no hay alerta."""
        make_regla("sanitaria", "proxima_vacuna", umbral=7.0)

        make_evento(self.animal, self.user, fecha=HOY + timedelta(days=15))

        self.assertFalse(Alerta.objects.filter(tipo="sanitaria").exists())


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 4 – RBAC y Control de Acceso
# ─────────────────────────────────────────────────────────────────────────────

class AlertaRBACTests(TestCase):
    """
    Verifica que @login_required y @require_perm protegen correctamente
    las vistas según los permisos alertas.view_alertas, alertas.atender_alertas
    y alertas.configurar_alertas.
    """

    def setUp(self):
        self.potrero = make_potrero("P-RBAC")
        self.animal = make_animal(self.potrero, rfid="COL-RBAC-001")
        self.user_admin = make_user("admin_rbac")
        self.alerta = make_alerta(tipo="sanitaria")

        self.user_view = make_user("user_view")
        grant_perm(self.user_view, "alertas.view_alertas")

        self.user_atender = make_user("user_atender")
        grant_perm(self.user_atender, "alertas.view_alertas")
        grant_perm(self.user_atender, "alertas.atender_alertas")

        self.user_config = make_user("user_config")
        grant_perm(self.user_config, "alertas.view_alertas")
        grant_perm(self.user_config, "alertas.configurar_alertas")

        self.user_sin = make_user("user_sin")

    # ── CP-RBAC-01 ───────────────────────────────────────────────────────────
    def test_index_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("alertas:index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-02 ───────────────────────────────────────────────────────────
    def test_detalle_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("alertas:detalle", args=[self.alerta.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-03 ───────────────────────────────────────────────────────────
    def test_atender_sin_auth_redirige_a_login(self):
        r = self.client.post(reverse("alertas:atender", args=[self.alerta.pk]),
                             {"observacion": ""})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-04 ───────────────────────────────────────────────────────────
    def test_configuracion_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse("alertas:configuracion"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    # ── CP-RBAC-05 ───────────────────────────────────────────────────────────
    def test_index_sin_permiso_view_retorna_403(self):
        self.client.force_login(self.user_sin)
        self.assertEqual(self.client.get(reverse("alertas:index")).status_code, 403)

    # ── CP-RBAC-06 ───────────────────────────────────────────────────────────
    def test_detalle_sin_permiso_view_retorna_403(self):
        self.client.force_login(self.user_sin)
        self.assertEqual(
            self.client.get(reverse("alertas:detalle", args=[self.alerta.pk])).status_code,
            403,
        )

    # ── CP-RBAC-07 ───────────────────────────────────────────────────────────
    def test_atender_sin_permiso_atender_retorna_403(self):
        self.client.force_login(self.user_view)
        r = self.client.post(reverse("alertas:atender", args=[self.alerta.pk]),
                             {"observacion": ""})
        self.assertEqual(r.status_code, 403)

    # ── CP-RBAC-08 ───────────────────────────────────────────────────────────
    def test_configuracion_sin_permiso_configurar_retorna_403(self):
        self.client.force_login(self.user_view)
        self.assertEqual(self.client.get(reverse("alertas:configuracion")).status_code, 403)

    # ── CP-RBAC-09 ───────────────────────────────────────────────────────────
    def test_usuario_view_puede_listar_y_ver_pero_no_atender_ni_configurar(self):
        self.client.force_login(self.user_view)
        self.assertEqual(self.client.get(reverse("alertas:index")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("alertas:detalle", args=[self.alerta.pk])).status_code,
            200,
        )
        # Sin permiso atender
        self.assertEqual(
            self.client.post(reverse("alertas:atender", args=[self.alerta.pk]),
                             {"observacion": ""}).status_code,
            403,
        )
        # Sin permiso configurar
        self.assertEqual(self.client.get(reverse("alertas:configuracion")).status_code, 403)

    # ── CP-RBAC-10 ───────────────────────────────────────────────────────────
    def test_usuario_con_todos_los_permisos_accede_a_todo(self):
        full_user = make_user("user_full")
        grant_perm(full_user, "alertas.view_alertas")
        grant_perm(full_user, "alertas.atender_alertas")
        grant_perm(full_user, "alertas.configurar_alertas")
        self.client.force_login(full_user)

        self.assertEqual(self.client.get(reverse("alertas:index")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("alertas:detalle", args=[self.alerta.pk])).status_code,
            200,
        )
        self.assertEqual(self.client.get(reverse("alertas:configuracion")).status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 5 – Vistas (comportamiento funcional)
# ─────────────────────────────────────────────────────────────────────────────

class AlertaVistaTests(TestCase):
    """
    Prueba el comportamiento de las vistas: listado con filtros, detalle,
    atender (HTML y API), configuración de reglas y endpoint de campana.
    """

    def setUp(self):
        self.user = make_user("operario_alt")
        grant_perm(self.user, "alertas.view_alertas")
        grant_perm(self.user, "alertas.atender_alertas")
        grant_perm(self.user, "alertas.configurar_alertas")
        self.client.force_login(self.user)

        self.potrero = make_potrero("P-VIS-01")
        self.animal = make_animal(self.potrero, rfid="COL-VIS-001")
        self.evento = make_evento(self.animal, self.user, fecha=MANANA)

        self.alerta_san = make_alerta(tipo="sanitaria", mensaje="Vacuna próxima",
                                      evento=self.evento)
        self.alerta_pro = make_alerta(tipo="productiva", mensaje="Variación de peso detectada")
        self.regla = make_regla("sanitaria", "proxima_vacuna", umbral=7.0)

    # ── CP-VISTA-01 ──────────────────────────────────────────────────────────
    def test_index_retorna_200_y_contexto_con_kpis(self):
        """GET /alertas/ → 200, page_obj y KPIs de conteo en contexto."""
        r = self.client.get(reverse("alertas:index"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("page_obj", r.context)
        self.assertIn("total_pendientes", r.context)
        self.assertIn("sanitarias_pendientes", r.context)
        self.assertGreaterEqual(r.context["total_pendientes"], 2)

    # ── CP-VISTA-02 ──────────────────────────────────────────────────────────
    def test_index_filtro_por_tipo(self):
        """GET ?tipo=sanitaria → solo alertas sanitarias en page_obj."""
        r = self.client.get(reverse("alertas:index") + "?tipo=sanitaria")
        self.assertEqual(r.status_code, 200)
        tipos = {a.tipo for a in r.context["page_obj"].object_list}
        self.assertEqual(tipos, {"sanitaria"})

    # ── CP-VISTA-03 ──────────────────────────────────────────────────────────
    def test_index_filtro_por_estado_pendiente(self):
        """GET ?estado=pendiente → solo alertas en estado PENDIENTE."""
        self.alerta_san.atender(self.user)
        r = self.client.get(reverse("alertas:index") + "?estado=pendiente")
        self.assertEqual(r.status_code, 200)
        estados = {a.estado for a in r.context["page_obj"].object_list}
        self.assertEqual(estados, {"pendiente"})

    # ── CP-VISTA-04 ──────────────────────────────────────────────────────────
    def test_index_filtro_q_por_mensaje(self):
        """GET ?q=Vacuna → solo alertas cuyo mensaje contiene 'Vacuna'."""
        r = self.client.get(reverse("alertas:index") + "?q=Vacuna")
        self.assertEqual(r.status_code, 200)
        for a in r.context["page_obj"].object_list:
            self.assertIn("Vacuna", a.mensaje)

    # ── CP-VISTA-05 ──────────────────────────────────────────────────────────
    def test_index_filtro_por_fecha_objetivo(self):
        """GET ?fecha_desde y ?fecha_hasta → filtra por rango de fecha_objetivo."""
        self.alerta_san.fecha_objetivo = MANANA
        self.alerta_san.save(update_fields=["fecha_objetivo"])

        fecha_str = MANANA.isoformat()
        r = self.client.get(
            reverse("alertas:index") + f"?fecha_desde={fecha_str}&fecha_hasta={fecha_str}"
        )
        self.assertEqual(r.status_code, 200)
        pks = [a.pk for a in r.context["page_obj"].object_list]
        self.assertIn(self.alerta_san.pk, pks)
        self.assertNotIn(self.alerta_pro.pk, pks)

    # ── CP-VISTA-06 ──────────────────────────────────────────────────────────
    def test_detalle_retorna_200_con_alerta_en_contexto(self):
        """GET /alertas/detalle/<pk>/ → 200, alerta y animal en contexto."""
        r = self.client.get(reverse("alertas:detalle", args=[self.alerta_san.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["alerta"].pk, self.alerta_san.pk)
        self.assertIn("animal", r.context)

    # ── CP-VISTA-07 ──────────────────────────────────────────────────────────
    def test_detalle_404_si_alerta_no_existe(self):
        """GET con UUID inexistente → 404."""
        import uuid
        fake_uuid = uuid.uuid4()
        r = self.client.get(reverse("alertas:detalle", args=[fake_uuid]))
        self.assertEqual(r.status_code, 404)

    # ── CP-VISTA-08 ──────────────────────────────────────────────────────────
    def test_atender_post_valido_marca_alerta_y_redirige(self):
        """POST /alertas/atender/<pk>/ → alerta ATENDIDA, redirige a index."""
        r = self.client.post(
            reverse("alertas:atender", args=[self.alerta_pro.pk]),
            {"observacion": "Revisado y corregido"},
        )
        self.assertRedirects(r, reverse("alertas:index"))
        self.alerta_pro.refresh_from_db()
        self.assertEqual(self.alerta_pro.estado, Alerta.Estado.ATENDIDA)
        self.assertEqual(self.alerta_pro.atendida_por, self.user)

    # ── CP-VISTA-09 ──────────────────────────────────────────────────────────
    def test_atender_post_y_evento_queda_realizado(self):
        """POST atender alerta vinculada a EventoSanitario → evento pasa a REALIZADO."""
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.CONFIRMADO)

        self.client.post(
            reverse("alertas:atender", args=[self.alerta_san.pk]),
            {"observacion": "Vacuna aplicada"},
        )

        self.evento.refresh_from_db()
        self.assertEqual(self.evento.estado, EventoSanitario.Estado.REALIZADO)

    # ── CP-VISTA-10 ──────────────────────────────────────────────────────────
    def test_atender_alerta_ya_atendida_redirige_con_warning(self):
        """POST sobre alerta ya ATENDIDA → redirige a detalle (sin error 500)."""
        self.alerta_pro.atender(self.user)
        r = self.client.post(
            reverse("alertas:atender", args=[self.alerta_pro.pk]),
            {"observacion": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.assertRedirects(
            r, reverse("alertas:detalle", args=[self.alerta_pro.pk])
        )

    # ── CP-VISTA-11 ──────────────────────────────────────────────────────────
    def test_configuracion_get_retorna_200_con_reglas(self):
        """GET /alertas/configuracion/ → 200, reglas en contexto."""
        r = self.client.get(reverse("alertas:configuracion"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("reglas", r.context)
        self.assertGreaterEqual(len(r.context["reglas"]), 1)

    # ── CP-VISTA-12 ──────────────────────────────────────────────────────────
    def test_configuracion_post_actualiza_umbral_y_activa(self):
        """POST en configuracion → regla queda con nuevo umbral_valor."""
        r = self.client.post(
            reverse("alertas:configuracion"),
            {
                f"activa_{self.regla.pk}": "on",
                f"umbral_valor_{self.regla.pk}": "14.0",
                f"umbral_unidad_{self.regla.pk}": "dias",
            },
        )
        self.assertRedirects(r, reverse("alertas:configuracion"))
        self.regla.refresh_from_db()
        self.assertEqual(float(self.regla.umbral_valor), 14.0)
        self.assertTrue(self.regla.activa)

    # ── CP-VISTA-13 ──────────────────────────────────────────────────────────
    def test_api_pendientes_retorna_json_con_count(self):
        """GET /alertas/api/pendientes/ → JSON con count >= 0 y lista ultimas."""
        r = self.client.get(reverse("alertas:api_pendientes"))
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("count", data)
        self.assertIn("ultimas", data)
        self.assertGreaterEqual(data["count"], 2)

    # ── CP-VISTA-14 ──────────────────────────────────────────────────────────
    def test_api_atender_patch_marca_alerta_como_atendida(self):
        """PATCH /alertas/api/atender/<pk>/ → JSON ok, alerta ATENDIDA."""
        r = self.client.generic(
            "PATCH",
            reverse("alertas:api_atender", args=[self.alerta_pro.pk]),
            data=json.dumps({"observacion": "Atendida vía API"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertEqual(data["status"], "ok")

        self.alerta_pro.refresh_from_db()
        self.assertEqual(self.alerta_pro.estado, Alerta.Estado.ATENDIDA)

    # ── CP-VISTA-15 (bonus) ──────────────────────────────────────────────────
    def test_api_atender_patch_sobre_ya_atendida_retorna_400(self):
        """PATCH sobre alerta ya ATENDIDA → 400 con mensaje de error."""
        self.alerta_pro.atender(self.user)
        r = self.client.generic(
            "PATCH",
            reverse("alertas:api_atender", args=[self.alerta_pro.pk]),
            data=json.dumps({"observacion": ""}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        data = json.loads(r.content)
        self.assertIn("error", data)
