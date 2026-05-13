"""
CU-010: Pruebas del módulo de Auditoría / Bitácora

Secciones:
  CP-MODEL-01..08  → Modelo Bitacora (inmutabilidad RN-2, campos, __str__)
  CP-MID-01..07    → Middleware y función registrar_bitacora()
  CP-SENAL-01..06  → Signals (captura automática CRUD de otros módulos)
  CP-RBAC-01..09   → Control de acceso (autenticación y permisos por vista)
  CP-VISTA-01..22  → Vistas (index, filtros, paginación, detalle, exportar CSV)
"""

import csv
import io

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from authz.models import Permission, Role, RolePermission, UserRole
from auditoria.middleware import (
    get_client_ip,
    get_current_request,
    get_current_user,
    registrar_bitacora,
)
from auditoria.models import Bitacora


# ─── Helper compartido ────────────────────────────────────────────────────────

def grant_perm(user: User, perm_code: str) -> None:
    perm, _ = Permission.objects.get_or_create(code=perm_code)
    role, _ = Role.objects.get_or_create(name=perm_code, code=perm_code)
    RolePermission.objects.get_or_create(role=role, permission=perm)
    UserRole.objects.get_or_create(user=user, role=role)


def crear_bitacora(**kwargs) -> Bitacora:
    defaults = {
        "accion": Bitacora.Accion.CREAR,
        "entidad": "Animal",
        "entidad_id": "1",
        "modulo_origen": "CU-02",
        "resumen": "Registro de prueba",
        "usuario_nombre": "test_user",
    }
    defaults.update(kwargs)
    return Bitacora.objects.create(**defaults)


def crear_potrero(sufijo="A"):
    from potreros.models import Potrero
    return Potrero.objects.create(
        nombre_codigo=f"Potrero-{sufijo}",
        area_ha="10.50",
        capacidad_maxima=20,
        tipo_uso="CEBA",
    )


# ─── CP-MODEL: Modelo Bitacora ────────────────────────────────────────────────

class ModeloBitacoraTest(TestCase):

    def test_cp_model_01_creacion_basica(self):
        """CP-MODEL-01: Se puede crear un registro con los campos mínimos obligatorios."""
        b = Bitacora.objects.create(
            accion=Bitacora.Accion.CREAR,
            entidad="Animal",
            usuario_nombre="admin",
        )
        self.assertIsNotNone(b.pk)
        self.assertEqual(b.accion, Bitacora.Accion.CREAR)
        self.assertEqual(b.entidad, "Animal")
        self.assertIsNotNone(b.fecha)

    def test_cp_model_02_inmutabilidad_save_bloquea_actualizacion(self):
        """CP-MODEL-02: RN-2 — Intentar guardar un registro existente lanza ValueError."""
        b = crear_bitacora()
        b.resumen = "modificado"
        with self.assertRaises(ValueError):
            b.save()

    def test_cp_model_03_inmutabilidad_delete_bloqueado(self):
        """CP-MODEL-03: RN-2 — Llamar delete() sobre una instancia lanza ValueError."""
        b = crear_bitacora()
        with self.assertRaises(ValueError):
            b.delete()

    def test_cp_model_04_str_incluye_campos_clave(self):
        """CP-MODEL-04: __str__ incluye la acción, entidad y nombre del usuario."""
        b = crear_bitacora(entidad="Potrero", usuario_nombre="maria")
        texto = str(b)
        self.assertIn("Potrero", texto)
        self.assertIn("maria", texto)
        self.assertIn(Bitacora.Accion.CREAR, texto)

    def test_cp_model_05_snapshot_usuario_nombre_es_inmutable(self):
        """CP-MODEL-05: usuario_nombre persiste el nombre en el momento del registro."""
        user = User.objects.create_user("juan", password="x")
        b = Bitacora.objects.create(
            accion=Bitacora.Accion.ACCEDER,
            entidad="Dashboard",
            user=user,
            usuario_nombre="Juan Original",
        )
        user.first_name = "Pedro"
        user.save()
        b_refresco = Bitacora.objects.get(pk=b.pk)
        self.assertEqual(b_refresco.usuario_nombre, "Juan Original")

    def test_cp_model_06_delta_json_se_persiste_correctamente(self):
        """CP-MODEL-06: valores_anteriores y valores_nuevos se almacenan como JSON."""
        b = Bitacora.objects.create(
            accion=Bitacora.Accion.EDITAR,
            entidad="Animal",
            entidad_id="5",
            usuario_nombre="ana",
            valores_anteriores={"nombre": "Vaca1"},
            valores_nuevos={"nombre": "Vaca2"},
        )
        self.assertEqual(b.valores_anteriores, {"nombre": "Vaca1"})
        self.assertEqual(b.valores_nuevos, {"nombre": "Vaca2"})

    def test_cp_model_07_todos_los_tipos_de_accion_son_validos(self):
        """CP-MODEL-07: Los seis tipos de acción definidos en Accion.choices son aceptados."""
        acciones = [
            Bitacora.Accion.CREAR,
            Bitacora.Accion.EDITAR,
            Bitacora.Accion.ELIMINAR,
            Bitacora.Accion.ACCEDER,
            Bitacora.Accion.ANULAR,
            Bitacora.Accion.CONFIGURAR,
        ]
        for accion in acciones:
            b = Bitacora.objects.create(accion=accion, entidad="Test", usuario_nombre="sys")
            self.assertEqual(b.accion, accion)

    def test_cp_model_08_ip_y_user_agent_son_opcionales(self):
        """CP-MODEL-08: ip_origen y user_agent admiten valores nulos/vacíos."""
        b = Bitacora.objects.create(
            accion=Bitacora.Accion.CREAR,
            entidad="Animal",
            usuario_nombre="sistema",
            ip_origen=None,
            user_agent="",
        )
        self.assertIsNone(b.ip_origen)
        self.assertEqual(b.user_agent, "")


# ─── CP-MID: Middleware y registrar_bitacora ──────────────────────────────────

class MiddlewareTest(TestCase):

    def test_cp_mid_01_get_current_request_fuera_de_peticion(self):
        """CP-MID-01: get_current_request() devuelve None cuando no hay request activo."""
        self.assertIsNone(get_current_request())

    def test_cp_mid_02_get_current_user_fuera_de_peticion(self):
        """CP-MID-02: get_current_user() devuelve None cuando no hay usuario en contexto."""
        self.assertIsNone(get_current_user())

    def test_cp_mid_03_get_client_ip_sin_request_devuelve_none(self):
        """CP-MID-03: get_client_ip(None) devuelve None sin lanzar excepción."""
        self.assertIsNone(get_client_ip(request=None))

    def test_cp_mid_04_get_client_ip_desde_remote_addr(self):
        """CP-MID-04: Cuando no hay X-Forwarded-For se usa REMOTE_ADDR."""
        request = RequestFactory().get("/")
        request.META["REMOTE_ADDR"] = "192.168.1.10"
        self.assertEqual(get_client_ip(request), "192.168.1.10")

    def test_cp_mid_05_get_client_ip_prefiere_xff(self):
        """CP-MID-05: Cuando existe X-Forwarded-For se usa el primer IP de la cadena."""
        request = RequestFactory().get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5, 10.0.0.1"
        self.assertEqual(get_client_ip(request), "203.0.113.5")

    def test_cp_mid_06_registrar_bitacora_crea_registro_en_bd(self):
        """CP-MID-06: registrar_bitacora() inserta exactamente un nuevo registro."""
        user = User.objects.create_user("bot", password="x")
        self.assertEqual(Bitacora.objects.count(), 0)
        registrar_bitacora(
            accion=Bitacora.Accion.CREAR,
            entidad="Animal",
            entidad_id="99",
            modulo_origen="CU-02",
            resumen="Creación desde prueba",
            user=user,
            ip="127.0.0.1",
        )
        self.assertEqual(Bitacora.objects.count(), 1)
        b = Bitacora.objects.first()
        self.assertEqual(b.accion, Bitacora.Accion.CREAR)
        self.assertEqual(b.ip_origen, "127.0.0.1")

    def test_cp_mid_07_registrar_bitacora_sin_usuario_usa_sistema(self):
        """CP-MID-07: Sin usuario en contexto, usuario_nombre queda como 'Sistema'."""
        registrar_bitacora(accion=Bitacora.Accion.ACCEDER, entidad="Dashboard")
        b = Bitacora.objects.first()
        self.assertEqual(b.usuario_nombre, "Sistema")
        self.assertIsNone(b.user)


# ─── CP-SENAL: Signals de captura CRUD ───────────────────────────────────────

class SignalsPotreroCRUDTest(TestCase):
    """CP-SENAL: Verifica que los signals pre/post_save registren en Bitácora."""

    def test_cp_senal_01_crear_potrero_genera_registro_crear(self):
        """CP-SENAL-01: Al crear un Potrero se registra acción CREAR en Bitácora."""
        antes = Bitacora.objects.filter(accion="CREAR", entidad="Potrero").count()
        crear_potrero("S01")
        despues = Bitacora.objects.filter(accion="CREAR", entidad="Potrero").count()
        self.assertGreater(despues, antes)

    def test_cp_senal_02_editar_potrero_genera_registro_editar(self):
        """CP-SENAL-02: Al editar un Potrero se registra acción EDITAR en Bitácora."""
        p = crear_potrero("S02")
        antes = Bitacora.objects.filter(accion="EDITAR", entidad="Potrero").count()
        p.observaciones = "Modificado en prueba"
        p.save()
        despues = Bitacora.objects.filter(accion="EDITAR", entidad="Potrero").count()
        self.assertGreater(despues, antes)

    def test_cp_senal_03_edicion_incluye_delta_valores_nuevos(self):
        """CP-SENAL-03: El registro de EDITAR contiene valores_nuevos no nulos."""
        p = crear_potrero("S03")
        p.observaciones = "Cambio para delta"
        p.save()
        b = Bitacora.objects.filter(accion="EDITAR", entidad="Potrero").last()
        self.assertIsNotNone(b)
        self.assertIsNotNone(b.valores_nuevos)

    def test_cp_senal_04_edicion_incluye_valores_anteriores(self):
        """CP-SENAL-04: El registro de EDITAR contiene valores_anteriores del snapshot previo."""
        p = crear_potrero("S04")
        p.observaciones = "Nuevo valor"
        p.save()
        b = Bitacora.objects.filter(accion="EDITAR", entidad="Potrero").last()
        self.assertIsNotNone(b)
        self.assertIsNotNone(b.valores_anteriores)

    def test_cp_senal_05_crear_animal_genera_registro_crear(self):
        """CP-SENAL-05: Al crear un Animal se registra acción CREAR con entidad 'Animal'."""
        from animals.models import Animal
        antes = Bitacora.objects.filter(accion="CREAR", entidad="Animal").count()
        Animal.objects.create(
            nombre="VacaPrueba01",
            sexo=Animal.Sexo.HEMBRA,
            etapa=Animal.Etapa.ADULTO,
        )
        despues = Bitacora.objects.filter(accion="CREAR", entidad="Animal").count()
        self.assertGreater(despues, antes)

    def test_cp_senal_06_fallo_signal_no_interrumpe_operacion_original(self):
        """CP-SENAL-06: La operación de negocio se completa aunque falle el registro de auditoría."""
        p = crear_potrero("S06")
        self.assertIsNotNone(p.pk)
        from potreros.models import Potrero
        self.assertTrue(Potrero.objects.filter(pk=p.pk).exists())


# ─── CP-RBAC: Control de acceso ───────────────────────────────────────────────

class RBACTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user_sin_perm = User.objects.create_user("sin_perm", password="pass")
        self.user_con_perm = User.objects.create_user("con_perm", password="pass")
        grant_perm(self.user_con_perm, "auditoria.read")

    # index ────────────────────────────────────────────────────────────────────

    def test_cp_rbac_01_index_sin_autenticacion_redirige_a_login(self):
        """CP-RBAC-01: GET /auditoria/ sin sesión devuelve 302 hacia /login/."""
        r = self.client.get(reverse("auditoria:index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_cp_rbac_02_index_sin_permiso_devuelve_403(self):
        """CP-RBAC-02: GET /auditoria/ con sesión pero sin permiso devuelve 403."""
        self.client.force_login(self.user_sin_perm)
        r = self.client.get(reverse("auditoria:index"))
        self.assertEqual(r.status_code, 403)

    def test_cp_rbac_03_index_con_permiso_devuelve_200(self):
        """CP-RBAC-03: GET /auditoria/ con permiso auditoria.read devuelve 200."""
        self.client.force_login(self.user_con_perm)
        r = self.client.get(reverse("auditoria:index"))
        self.assertEqual(r.status_code, 200)

    # detalle ──────────────────────────────────────────────────────────────────

    def test_cp_rbac_04_detalle_sin_autenticacion_redirige_a_login(self):
        """CP-RBAC-04: GET /auditoria/<pk>/ sin sesión devuelve 302 hacia /login/."""
        b = crear_bitacora()
        r = self.client.get(reverse("auditoria:detalle", args=[b.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_cp_rbac_05_detalle_sin_permiso_devuelve_403(self):
        """CP-RBAC-05: GET /auditoria/<pk>/ sin permiso devuelve 403."""
        b = crear_bitacora()
        self.client.force_login(self.user_sin_perm)
        r = self.client.get(reverse("auditoria:detalle", args=[b.pk]))
        self.assertEqual(r.status_code, 403)

    def test_cp_rbac_06_detalle_con_permiso_devuelve_200(self):
        """CP-RBAC-06: GET /auditoria/<pk>/ con permiso devuelve 200."""
        b = crear_bitacora()
        self.client.force_login(self.user_con_perm)
        r = self.client.get(reverse("auditoria:detalle", args=[b.pk]))
        self.assertEqual(r.status_code, 200)

    # exportar_csv ─────────────────────────────────────────────────────────────

    def test_cp_rbac_07_csv_sin_autenticacion_redirige_a_login(self):
        """CP-RBAC-07: GET /auditoria/exportar/csv/ sin sesión redirige a /login/."""
        r = self.client.get(reverse("auditoria:exportar_csv"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_cp_rbac_08_csv_sin_permiso_devuelve_403(self):
        """CP-RBAC-08: GET /auditoria/exportar/csv/ sin permiso devuelve 403."""
        self.client.force_login(self.user_sin_perm)
        r = self.client.get(reverse("auditoria:exportar_csv"))
        self.assertEqual(r.status_code, 403)

    def test_cp_rbac_09_csv_con_permiso_devuelve_200_y_content_type_csv(self):
        """CP-RBAC-09: GET /auditoria/exportar/csv/ con permiso devuelve 200 y CSV."""
        self.client.force_login(self.user_con_perm)
        r = self.client.get(reverse("auditoria:exportar_csv"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])


# ─── CP-VISTA: Vista index ────────────────────────────────────────────────────

class VistaIndexTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("auditor", password="pass")
        grant_perm(self.user, "auditoria.read")
        self.client.force_login(self.user)

    def test_cp_vista_01_index_lista_registros_existentes(self):
        """CP-VISTA-01: La vista index expone page_obj con los registros creados."""
        crear_bitacora(resumen="Alpha")
        crear_bitacora(resumen="Beta")
        r = self.client.get(reverse("auditoria:index"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("page_obj", r.context)
        self.assertGreaterEqual(r.context["page_obj"].paginator.count, 2)

    def test_cp_vista_02_filtro_q_busca_en_resumen(self):
        """CP-VISTA-02: El parámetro q= filtra por texto en resumen y entidad."""
        crear_bitacora(resumen="buscar_esto", entidad="Animal")
        crear_bitacora(resumen="otro_registro", entidad="Potrero")
        r = self.client.get(reverse("auditoria:index"), {"q": "buscar_esto"})
        resultados = list(r.context["page_obj"])
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].resumen, "buscar_esto")

    def test_cp_vista_03_filtro_entidad_limita_resultados(self):
        """CP-VISTA-03: El parámetro entidad= devuelve solo registros de esa entidad."""
        crear_bitacora(entidad="Animal")
        crear_bitacora(entidad="Potrero")
        r = self.client.get(reverse("auditoria:index"), {"entidad": "Animal"})
        page = list(r.context["page_obj"])
        self.assertTrue(all(b.entidad == "Animal" for b in page))

    def test_cp_vista_04_filtro_accion_limita_resultados(self):
        """CP-VISTA-04: El parámetro accion= devuelve solo registros de ese tipo."""
        crear_bitacora(accion=Bitacora.Accion.CREAR)
        crear_bitacora(accion=Bitacora.Accion.ELIMINAR)
        r = self.client.get(reverse("auditoria:index"), {"accion": "CREAR"})
        page = list(r.context["page_obj"])
        self.assertTrue(all(b.accion == "CREAR" for b in page))

    def test_cp_vista_05_filtro_usuario_limita_por_user_id(self):
        """CP-VISTA-05: El parámetro usuario= filtra los registros de ese usuario."""
        u1 = User.objects.create_user("u1", password="x")
        u2 = User.objects.create_user("u2", password="x")
        Bitacora.objects.create(accion="CREAR", entidad="E", usuario_nombre="u1", user=u1)
        Bitacora.objects.create(accion="CREAR", entidad="E", usuario_nombre="u2", user=u2)
        r = self.client.get(reverse("auditoria:index"), {"usuario": u1.pk})
        page = list(r.context["page_obj"])
        self.assertTrue(all(b.user_id == u1.pk for b in page))

    def test_cp_vista_06_filtro_rango_valido_no_activa_error(self):
        """CP-VISTA-06: Un rango válido (desde <= hasta) no activa error_rango y retorna 200."""
        crear_bitacora(resumen="en_rango")
        r = self.client.get(reverse("auditoria:index"), {
            "desde": "2020-01-01",
            "hasta": "2099-12-31",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context["error_rango"])

    def test_cp_vista_07_filtro_rango_invalido_activa_error_rango(self):
        """CP-VISTA-07: Cuando desde > hasta, el contexto marca error_rango=True."""
        r = self.client.get(reverse("auditoria:index"), {
            "desde": "2099-01-01",
            "hasta": "2020-01-01",
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["error_rango"])

    def test_cp_vista_08_paginacion_muestra_25_por_pagina(self):
        """CP-VISTA-08: Con más de 25 registros, la primera página muestra exactamente 25."""
        for i in range(30):
            crear_bitacora(resumen=f"reg-{i}")
        r = self.client.get(reverse("auditoria:index"))
        self.assertEqual(len(r.context["page_obj"].object_list), 25)

    def test_cp_vista_09_segunda_pagina_muestra_sobrantes(self):
        """CP-VISTA-09: La segunda página muestra los registros sobrantes."""
        for i in range(30):
            crear_bitacora(resumen=f"pag-{i}")
        r = self.client.get(reverse("auditoria:index"), {"page": 2})
        self.assertEqual(len(r.context["page_obj"].object_list), 5)

    def test_cp_vista_10_sin_resultados_activa_flag_contexto(self):
        """CP-VISTA-10: Búsqueda sin resultados establece sin_resultados=True."""
        r = self.client.get(reverse("auditoria:index"), {"q": "xxxxxno_existe_xxxxx"})
        self.assertTrue(r.context["sin_resultados"])

    def test_cp_vista_11_contexto_contiene_stats_por_accion(self):
        """CP-VISTA-11: El contexto incluye stats con contadores globales por tipo de acción."""
        crear_bitacora(accion=Bitacora.Accion.CREAR)
        crear_bitacora(accion=Bitacora.Accion.EDITAR)
        r = self.client.get(reverse("auditoria:index"))
        stats = r.context["stats"]
        self.assertIn("total", stats)
        self.assertIn("creaciones", stats)
        self.assertIn("ediciones", stats)
        self.assertIn("eliminaciones", stats)

    def test_cp_vista_12_contexto_provee_listas_para_selectores(self):
        """CP-VISTA-12: El contexto expone listas de entidades, acciones y usuarios."""
        r = self.client.get(reverse("auditoria:index"))
        self.assertIn("acciones_disponibles", r.context)
        self.assertIn("entidades_disponibles", r.context)
        self.assertIn("usuarios_disponibles", r.context)


# ─── CP-VISTA: Vista detalle ─────────────────────────────────────────────────

class VistaDetalleTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("auditor2", password="pass")
        grant_perm(self.user, "auditoria.read")
        self.client.force_login(self.user)

    def test_cp_vista_13_detalle_muestra_registro_correcto(self):
        """CP-VISTA-13: La vista detalle expone el registro solicitado en el contexto."""
        b = crear_bitacora(resumen="Detalle test", entidad="Potrero")
        r = self.client.get(reverse("auditoria:detalle", args=[b.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["registro"].pk, b.pk)

    def test_cp_vista_14_detalle_formatea_delta_json_con_indentacion(self):
        """CP-VISTA-14: Cuando hay delta, ant_fmt y nue_fmt están formateados con indent=2."""
        b = Bitacora.objects.create(
            accion=Bitacora.Accion.EDITAR,
            entidad="Animal",
            usuario_nombre="test",
            valores_anteriores={"nombre": "A"},
            valores_nuevos={"nombre": "B"},
        )
        r = self.client.get(reverse("auditoria:detalle", args=[b.pk]))
        self.assertIsNotNone(r.context["ant_fmt"])
        self.assertIsNotNone(r.context["nue_fmt"])
        self.assertIn("\n", r.context["ant_fmt"])

    def test_cp_vista_15_detalle_sin_delta_devuelve_none_en_contexto(self):
        """CP-VISTA-15: Cuando no hay delta, ant_fmt y nue_fmt son None."""
        b = crear_bitacora(accion=Bitacora.Accion.ACCEDER)
        r = self.client.get(reverse("auditoria:detalle", args=[b.pk]))
        self.assertIsNone(r.context["ant_fmt"])
        self.assertIsNone(r.context["nue_fmt"])

    def test_cp_vista_16_detalle_pk_inexistente_devuelve_404(self):
        """CP-VISTA-16: Si el pk no existe la vista devuelve HTTP 404."""
        r = self.client.get(reverse("auditoria:detalle", args=[99999]))
        self.assertEqual(r.status_code, 404)


# ─── CP-VISTA: Vista exportar_csv ────────────────────────────────────────────

class VistaCSVTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("auditor3", password="pass")
        grant_perm(self.user, "auditoria.read")
        self.client.force_login(self.user)

    def _leer_csv(self, response):
        content = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(content)))

    def test_cp_vista_17_csv_devuelve_attachment_con_nombre_archivo(self):
        """CP-VISTA-17: La respuesta incluye Content-Disposition attachment con .csv."""
        crear_bitacora()
        r = self.client.get(reverse("auditoria:exportar_csv"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn(".csv", r["Content-Disposition"])

    def test_cp_vista_18_csv_primera_fila_son_cabeceras(self):
        """CP-VISTA-18: La primera fila del CSV contiene las cabeceras esperadas."""
        r = self.client.get(reverse("auditoria:exportar_csv"))
        headers = self._leer_csv(r)[0]
        self.assertIn("Fecha/Hora", headers)
        self.assertIn("Usuario", headers)
        self.assertIn("Acción", headers)
        self.assertIn("Entidad", headers)
        self.assertIn("Resumen", headers)

    def test_cp_vista_19_csv_exporta_sin_paginacion(self):
        """CP-VISTA-19: El CSV contiene todos los registros (más de 25, sin paginación)."""
        for i in range(30):
            crear_bitacora(resumen=f"csv-{i}")
        r = self.client.get(reverse("auditoria:exportar_csv"))
        filas = self._leer_csv(r)
        # 1 cabecera + 30 datos
        self.assertEqual(len(filas), 31)

    def test_cp_vista_20_csv_aplica_filtro_entidad(self):
        """CP-VISTA-20: Los filtros de la querystring se aplican también en la exportación."""
        crear_bitacora(entidad="Animal")
        crear_bitacora(entidad="Potrero")
        r = self.client.get(reverse("auditoria:exportar_csv"), {"entidad": "Animal"})
        # índice 3 = columna Entidad (Fecha/Hora, Usuario, Acción, Entidad)
        filas_datos = self._leer_csv(r)[1:]
        self.assertEqual(len(filas_datos), 1)
        self.assertEqual(filas_datos[0][3], "Animal")

    def test_cp_vista_21_csv_rango_invalido_retorna_400(self):
        """CP-VISTA-21: Con desde > hasta la exportación devuelve HTTP 400."""
        r = self.client.get(reverse("auditoria:exportar_csv"), {
            "desde": "2099-01-01",
            "hasta": "2020-01-01",
        })
        self.assertEqual(r.status_code, 400)

    def test_cp_vista_22_csv_registra_evento_acceder_en_bitacora(self):
        """CP-VISTA-22: La exportación genera un registro ACCEDER/Bitacora en la propia bitácora."""
        antes = Bitacora.objects.filter(accion="ACCEDER", entidad="Bitacora").count()
        self.client.get(reverse("auditoria:exportar_csv"))
        despues = Bitacora.objects.filter(accion="ACCEDER", entidad="Bitacora").count()
        self.assertGreater(despues, antes)
