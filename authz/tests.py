# =============================================================================
# VACWEB – Pruebas Funcionales Completas – CU-001
# Autenticación, Control de Acceso por Roles (RBAC) y Gestión de Usuarios
# =============================================================================
# Archivo:   authz/tests.py
# Ejecutar:  python manage.py test authz -v2
# Autores:   Neyder Orozco – Diego Rojas
# Fecha:     2026-03-24
# =============================================================================
#
# Contenido:
#   Sección 1  – PU-001 a PU-006  : utils.py (permisos RBAC)
#   Sección 2  – PU-007 a PU-014  : login_view / api_login
#   Sección 3  – PU-015 a PU-016  : logout_view
#   Sección 4  – PU-017 a PU-019  : decorador require_perm
#   Sección 5  – PU-020 a PU-021  : middleware Log403
#   Sección 6  – PU-022 a PU-024  : signals de auditoría
#   Sección 7  – PU-025 a PU-028  : API REST
#   Sección 8  – PU-029 a PU-031  : roles múltiples
#   Sección 9  – PE-001 a PE-011  : AFD ciclo de bloqueo
#   Sección 10 – PI-001 a PI-007  : integración
#   Sección 11 – PS-001 a PS-005  : sistema (end-to-end)
#
# NOTA: Los tests que esperan respuesta HTML renderizada (status 200 con
# template) usan el endpoint API (/api/auth/login) o RequestFactory para
# evitar un bug de compatibilidad entre Python 3.14 y Django 5.2 en el
# test client al copiar contextos de templates.
# (AttributeError: 'super' object has no attribute 'dicts')
#
# =============================================================================

from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User, AnonymousUser
from django.core.cache import cache
from django.conf import settings

from authz.models import Role, Permission, RolePermission, UserRole, AuditLog
from authz.utils import user_permission_codes, has_perm_code


# =============================================================================
# CLASE BASE – Datos de prueba reutilizables
# =============================================================================

class AuthzBaseTestCase(TestCase):
    """
    Configura el escenario de prueba común para todos los tests de authz:
    - 2 roles (ADMIN, OPERADOR) con permisos diferenciados
    - 3 usuarios (admin activo, operador activo, usuario inactivo)
    - Limpia caché antes y después de cada test
    """

    def setUp(self):
        cache.clear()

        # ── Roles ──
        self.rol_admin = Role.objects.create(name="Administrador", code="ADMIN")
        self.rol_operador = Role.objects.create(name="Operador", code="OPERADOR")

        # ── Permisos ──
        self.perm_animals_read = Permission.objects.create(
            code="animals.read", description="Consultar animales"
        )
        self.perm_animals_write = Permission.objects.create(
            code="animals.write", description="Crear/editar animales"
        )
        self.perm_users_manage = Permission.objects.create(
            code="users.manage", description="Gestionar usuarios"
        )

        # ── Asignación rol → permisos ──
        RolePermission.objects.create(role=self.rol_admin, permission=self.perm_animals_read)
        RolePermission.objects.create(role=self.rol_admin, permission=self.perm_animals_write)
        RolePermission.objects.create(role=self.rol_admin, permission=self.perm_users_manage)
        RolePermission.objects.create(role=self.rol_operador, permission=self.perm_animals_read)

        # ── Usuarios ──
        self.admin_user = User.objects.create_user(
            username="admin", password="Admin$1234", is_active=True
        )
        self.operador_user = User.objects.create_user(
            username="operador", password="Oper$1234", is_active=True
        )
        self.inactive_user = User.objects.create_user(
            username="inactivo", password="Inac$1234", is_active=False
        )

        # ── Asignación usuario → rol ──
        UserRole.objects.create(user=self.admin_user, role=self.rol_admin)
        UserRole.objects.create(user=self.operador_user, role=self.rol_operador)

        self.client = Client()

    def tearDown(self):
        cache.clear()


# =============================================================================
# SECCIÓN 1 – utils.py: user_permission_codes() y has_perm_code()
# Caminos: C1-C6
# =============================================================================

class UtilsPermissionTest(AuthzBaseTestCase):
    """PU-001 a PU-006: Lógica interna de resolución de permisos RBAC."""

    def test_PU001_usuario_no_autenticado_retorna_vacio(self):
        """C1: AnonymousUser → is_authenticated == False → retorna set vacío."""
        anon = AnonymousUser()
        resultado = user_permission_codes(anon)
        self.assertEqual(resultado, set())

    def test_PU002_usuario_sin_roles_retorna_vacio(self):
        """C2: Usuario válido pero sin UserRole → set vacío (deny by default)."""
        user_sin_rol = User.objects.create_user(username="sinrol", password="Test$1234")
        resultado = user_permission_codes(user_sin_rol)
        self.assertEqual(resultado, set())

    def test_PU003_operador_tiene_solo_animals_read(self):
        """C3: Operador → 1 rol → 1 permiso → retorna {'animals.read'}."""
        resultado = user_permission_codes(self.operador_user)
        self.assertEqual(resultado, {"animals.read"})

    def test_PU004_admin_tiene_todos_los_permisos(self):
        """C4: Admin → 1 rol → 3 permisos → retorna los 3 códigos."""
        resultado = user_permission_codes(self.admin_user)
        esperado = {"animals.read", "animals.write", "users.manage"}
        self.assertEqual(resultado, esperado)

    def test_PU005_has_perm_code_permiso_existente(self):
        """C5: Operador tiene animals.read → has_perm_code retorna True."""
        self.assertTrue(has_perm_code(self.operador_user, "animals.read"))

    def test_PU006_has_perm_code_permiso_inexistente(self):
        """C6: Operador NO tiene animals.write → has_perm_code retorna False."""
        self.assertFalse(has_perm_code(self.operador_user, "animals.write"))


# =============================================================================
# SECCIÓN 2 – views.py → login_view() y api_login()
# Caminos: C7-C12
# =============================================================================

class LoginViewTest(AuthzBaseTestCase):
    """PU-007 a PU-014: Caminos de decisión en la vista de login."""

    def test_PU007_get_login_retorna_200(self):
        """C7: GET /login/ → status 200.
        Usa RequestFactory para evitar bug de template context.
        """
        from authz.views import login_view
        factory = RequestFactory()
        request = factory.get("/login/")
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()
        response = login_view(request)
        self.assertEqual(response.status_code, 200)

    def test_PU008_login_exitoso_redirige_y_audita(self):
        """C8: POST válido → authenticate OK → login() → redirect 302.
        NOTA: Se generan 2 registros login_success por cada login:
        uno creado manualmente en la vista y otro por el signal
        user_logged_in de Django. Validamos que exista al menos 1.
        """
        initial_count = AuditLog.objects.filter(action="login_success").count()
        response = self.client.post("/login/", {
            "username": "admin",
            "password": "Admin$1234",
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(
            AuditLog.objects.filter(action="login_success").count(),
            initial_count + 1
        )

    def test_PU009_login_fallido_audita_y_retorna_401(self):
        """C9: POST inválido → authenticate == None → _register_failed()
        → AuditLog(login_failed) → respuesta de error (401 vía API).
        """
        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "incorrecta"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertTrue(
            AuditLog.objects.filter(action="login_failed").exists()
        )

    def test_PU010_login_exitoso_limpia_contadores(self):
        """C8 complemento: _clear_counters() borra las claves de caché
        tras un login exitoso.
        """
        for _ in range(2):
            self.client.post(
                "/api/auth/login",
                {"username": "admin", "password": "incorrecta"},
                content_type="application/json",
            )
        self.client.post("/login/", {
            "username": "admin",
            "password": "Admin$1234",
        })
        from authz.views import _is_blocked
        self.assertFalse(_is_blocked("admin", "127.0.0.1"))

    def test_PU011_cuenta_inactiva_no_autentica(self):
        """C11: is_active=False → Django authenticate() retorna None
        → misma rama que credenciales incorrectas → error 401.
        """
        response = self.client.post(
            "/api/auth/login",
            {"username": "inactivo", "password": "Inac$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_PU012_bloqueo_tras_N_intentos(self):
        """C12: N fallos consecutivos → _register_failed incrementa hasta
        attempts >= MAX → cache.set(k_block) → 429.
        """
        max_attempts = settings.AUTHZ_LOGIN_MAX_ATTEMPTS
        for i in range(max_attempts):
            self.client.post(
                "/api/auth/login",
                {"username": "admin", "password": "incorrecta"},
                content_type="application/json",
            )
        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertTrue(
            AuditLog.objects.filter(action="login_blocked").exists()
        )

    def test_PU013_bloqueo_impide_login_valido(self):
        """C10: Con bloqueo activo en caché → ni credenciales correctas
        superan la verificación → 429.
        """
        from authz.views import _login_keys
        _, k_block = _login_keys("admin", "127.0.0.1")
        cache.set(k_block, 1, timeout=600)

        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

    def test_PU014_mensaje_generico_no_revela_existencia(self):
        """Anti-enumeración: tanto usuario inexistente como contraseña
        incorrecta producen el mismo status y estructura de respuesta.
        """
        resp_inexistente = self.client.post(
            "/api/auth/login",
            {"username": "fantasma", "password": "cualquiera"},
            content_type="application/json",
        )
        resp_incorrecto = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "incorrecta"},
            content_type="application/json",
        )
        self.assertEqual(resp_inexistente.status_code, 401)
        self.assertEqual(resp_incorrecto.status_code, 401)
        self.assertEqual(
            resp_inexistente.json()["detail"],
            resp_incorrecto.json()["detail"],
        )


# =============================================================================
# SECCIÓN 3 – views.py → logout_view()
# =============================================================================

class LogoutViewTest(AuthzBaseTestCase):
    """PU-015 a PU-016: Flujo de cierre de sesión."""

    def test_PU015_logout_redirige_y_audita(self):
        """Logout → AuditLog(logout) → redirect a /login/."""
        self.client.login(username="admin", password="Admin$1234")
        response = self.client.get("/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        self.assertTrue(
            AuditLog.objects.filter(
                action="logout", user=self.admin_user
            ).exists()
        )

    def test_PU016_logout_invalida_sesion(self):
        """Tras logout, acceder a vista protegida redirige a login."""
        self.client.login(username="admin", password="Admin$1234")
        self.client.get("/logout/")
        response = self.client.get("/demo/secure")
        self.assertIn(response.status_code, [302, 403])


# =============================================================================
# SECCIÓN 4 – decorators.py → require_perm() (deny by default)
# Caminos: C13-C15
# =============================================================================

class RequirePermDecoratorTest(AuthzBaseTestCase):
    """PU-017 a PU-019: Decorador de autorización RBAC."""

    def test_PU017_con_permiso_accede(self):
        """C13: Operador tiene animals.read → /demo/secure retorna 200."""
        self.client.login(username="operador", password="Oper$1234")
        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

    def test_PU018_sin_permiso_403(self):
        """C14: Usuario sin roles → deny by default → 403."""
        User.objects.create_user(username="sinperm", password="Test$1234")
        self.client.login(username="sinperm", password="Test$1234")
        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 403)

    def test_PU019_no_autenticado_redirige(self):
        """C15: Sin sesión → @login_required redirige a LOGIN_URL (302)."""
        response = self.client.get("/demo/secure")
        self.assertIn(response.status_code, [302, 403])


# =============================================================================
# SECCIÓN 5 – middleware.py → Log403Middleware
# Caminos: C16-C17
# =============================================================================

class Log403MiddlewareTest(AuthzBaseTestCase):
    """PU-020 a PU-021: Middleware de auditoría para respuestas 403."""

    def test_PU020_403_genera_auditlog(self):
        """C16: Respuesta 403 → middleware crea AuditLog(forbidden_403)."""
        User.objects.create_user(username="noperm", password="Test$1234")
        self.client.login(username="noperm", password="Test$1234")
        self.client.get("/demo/secure")
        self.assertTrue(
            AuditLog.objects.filter(action="forbidden_403").exists()
        )
        log = AuditLog.objects.filter(action="forbidden_403").first()
        self.assertEqual(log.metadata.get("path"), "/demo/secure")

    def test_PU021_200_no_genera_auditlog_403(self):
        """C17: Respuesta 200 → middleware no crea AuditLog de tipo 403."""
        count_before = AuditLog.objects.filter(action="forbidden_403").count()
        self.client.login(username="operador", password="Oper$1234")
        self.client.get("/demo/secure")
        count_after = AuditLog.objects.filter(action="forbidden_403").count()
        self.assertEqual(count_before, count_after)


# =============================================================================
# SECCIÓN 6 – signals.py → Señales de auditoría de Django
# Caminos: C18-C20
# =============================================================================

class AuditSignalsTest(AuthzBaseTestCase):
    """PU-022 a PU-024: Señales user_logged_in/out/failed → AuditLog."""

    def test_PU022_signal_login_success(self):
        """C18: login() dispara user_logged_in → AuditLog con signal=True."""
        self.client.login(username="admin", password="Admin$1234")
        self.assertTrue(
            AuditLog.objects.filter(
                action="login_success",
                user=self.admin_user,
                metadata__signal=True,
            ).exists()
        )

    def test_PU023_signal_logout(self):
        """C19: logout() dispara user_logged_out → AuditLog(logout)."""
        self.client.login(username="admin", password="Admin$1234")
        self.client.get("/logout/")
        self.assertTrue(
            AuditLog.objects.filter(
                action="logout",
                user=self.admin_user,
            ).exists()
        )

    def test_PU024_signal_login_failed(self):
        """C20: authenticate() fallido dispara user_login_failed."""
        self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "incorrecta"},
            content_type="application/json",
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action="login_failed",
                metadata__username="admin",
            ).exists()
        )


# =============================================================================
# SECCIÓN 7 – API REST (api_login, api_logout, api_me)
# =============================================================================

class APILoginTest(AuthzBaseTestCase):
    """PU-025 a PU-028: Endpoints API para autenticación."""

    def test_PU025_api_login_exitoso(self):
        """POST /api/auth/login con credenciales válidas → 200."""
        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_PU026_api_login_fallido(self):
        """POST /api/auth/login con contraseña incorrecta → 401."""
        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "incorrecta"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_PU027_api_login_bloqueado(self):
        """POST /api/auth/login con bloqueo activo → 429."""
        from authz.views import _login_keys
        _, k_block = _login_keys("admin", "127.0.0.1")
        cache.set(k_block, 1, timeout=600)

        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

    def test_PU028_api_me_retorna_roles_y_permisos(self):
        """GET /api/auth/me → JSON con username, roles[] y permissions[]."""
        self.client.login(username="admin", password="Admin$1234")
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "admin")
        self.assertIn("ADMIN", data["roles"])
        self.assertIn("animals.read", data["permissions"])
        self.assertIn("animals.write", data["permissions"])
        self.assertIn("users.manage", data["permissions"])


# =============================================================================
# SECCIÓN 8 – Pruebas de roles múltiples y propagación
# =============================================================================

class MultipleRolesTest(AuthzBaseTestCase):
    """PU-029 a PU-031: Unión de permisos con múltiples roles asignados."""

    def test_PU029_usuario_con_dos_roles_tiene_union_de_permisos(self):
        """Asignar ADMIN + OPERADOR al mismo usuario → unión de permisos."""
        UserRole.objects.create(user=self.operador_user, role=self.rol_admin)
        resultado = user_permission_codes(self.operador_user)
        esperado = {"animals.read", "animals.write", "users.manage"}
        self.assertEqual(resultado, esperado)

    def test_PU030_eliminar_rol_remueve_permisos(self):
        """Al eliminar el UserRole del operador → pierde animals.read."""
        UserRole.objects.filter(
            user=self.operador_user, role=self.rol_operador
        ).delete()
        resultado = user_permission_codes(self.operador_user)
        self.assertEqual(resultado, set())

    def test_PU031_permiso_sin_rol_asignado_no_otorga_acceso(self):
        """Un permiso existente en BD pero no vinculado a ningún rol
        del usuario → no aparece en sus permisos.
        """
        Permission.objects.create(code="reports.export", description="Exportar reportes")
        resultado = user_permission_codes(self.operador_user)
        self.assertNotIn("reports.export", resultado)


# =============================================================================
# SECCIÓN 9 – Pruebas Basadas en Estado (AFD): Ciclo de bloqueo de login
#
# Autómata: M = ({Libre, Acumulando, Bloqueado}, {login_fallido,
#           login_exitoso, timeout_expira}, δ, Libre, {Bloqueado})
#
# Mapeo a código real (authz/views.py):
#   Libre      → k_attempts no existe Y k_block no existe
#   Acumulando → k_attempts existe (1 ≤ val < N) Y k_block no existe
#   Bloqueado  → k_block existe
#
# Configuración: N=5 intentos, TTL=10 minutos (settings.py)
# =============================================================================

class AFDBloqueoLoginTest(AuthzBaseTestCase):
    """PE-001 a PE-011: Pruebas de transición del AFD de bloqueo."""

    def _get_keys(self, username="admin", ip="127.0.0.1"):
        """Helper: obtiene las claves de caché para un par usuario/IP."""
        from authz.views import _login_keys
        return _login_keys(username, ip)

    def _get_attempts(self, username="admin", ip="127.0.0.1"):
        """Helper: retorna el contador actual de intentos fallidos."""
        k_attempts, _ = self._get_keys(username, ip)
        return cache.get(k_attempts, 0)

    def _is_blocked(self, username="admin", ip="127.0.0.1"):
        """Helper: verifica si el par usuario/IP está bloqueado."""
        from authz.views import _is_blocked
        return _is_blocked(username, ip)

    def _do_failed_login(self, username="admin"):
        """Helper: ejecuta un intento de login fallido vía API."""
        return self.client.post(
            "/api/auth/login",
            {"username": username, "password": "incorrecta"},
            content_type="application/json",
        )

    def _do_success_login(self, username="admin", password="Admin$1234"):
        """Helper: ejecuta un login exitoso vía HTML (redirect 302)."""
        return self.client.post("/login/", {
            "username": username,
            "password": password,
        })

    # ── Transición: Libre → Acumulando (primer fallo) ──

    def test_PE001_libre_a_acumulando_primer_fallo(self):
        """δ(Libre, login_fallido) = Acumulando(1)."""
        self.assertEqual(self._get_attempts(), 0)
        self.assertFalse(self._is_blocked())

        self._do_failed_login()

        self.assertEqual(self._get_attempts(), 1)
        self.assertFalse(self._is_blocked())

    # ── Transición: Acumulando → Acumulando (fallos intermedios) ──

    def test_PE002_acumulando_a_acumulando_fallos_intermedios(self):
        """δ(Acumulando(n), login_fallido) = Acumulando(n+1) para n < N-1."""
        for expected in range(1, settings.AUTHZ_LOGIN_MAX_ATTEMPTS - 1):
            self._do_failed_login()
            self.assertEqual(self._get_attempts(), expected)
            self.assertFalse(self._is_blocked())

    # ── Transición: Acumulando(N-1) → Bloqueado (fallo N) ──

    def test_PE003_acumulando_a_bloqueado_fallo_N(self):
        """δ(Acumulando(N-1), login_fallido) = Bloqueado."""
        for _ in range(settings.AUTHZ_LOGIN_MAX_ATTEMPTS):
            self._do_failed_login()

        self.assertTrue(self._is_blocked())
        self.assertGreaterEqual(
            self._get_attempts(),
            settings.AUTHZ_LOGIN_MAX_ATTEMPTS,
        )

    # ── Transición: Bloqueado → Bloqueado (fallo adicional) ──

    def test_PE004_bloqueado_permanece_bloqueado_con_fallo(self):
        """δ(Bloqueado, login_fallido) = Bloqueado."""
        for _ in range(settings.AUTHZ_LOGIN_MAX_ATTEMPTS):
            self._do_failed_login()
        self.assertTrue(self._is_blocked())

        response = self._do_failed_login()
        self.assertEqual(response.status_code, 429)
        self.assertTrue(self._is_blocked())

    # ── Transición: Bloqueado → Bloqueado (login válido rechazado) ──

    def test_PE005_bloqueado_rechaza_credenciales_validas(self):
        """δ(Bloqueado, login_exitoso) = Bloqueado."""
        for _ in range(settings.AUTHZ_LOGIN_MAX_ATTEMPTS):
            self._do_failed_login()
        self.assertTrue(self._is_blocked())

        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertTrue(self._is_blocked())

    # ── Transición: Acumulando → Libre (login exitoso limpia) ──

    def test_PE006_acumulando_a_libre_login_exitoso(self):
        """δ(Acumulando(n), login_exitoso) = Libre."""
        for _ in range(3):
            self._do_failed_login()
        self.assertEqual(self._get_attempts(), 3)
        self.assertFalse(self._is_blocked())

        self._do_success_login()

        self.assertEqual(self._get_attempts(), 0)
        self.assertFalse(self._is_blocked())

    # ── Transición: Libre → Libre (login exitoso, no-op) ──

    def test_PE007_libre_permanece_libre_con_login_exitoso(self):
        """δ(Libre, login_exitoso) = Libre."""
        self.assertEqual(self._get_attempts(), 0)
        self.assertFalse(self._is_blocked())

        self._do_success_login()

        self.assertEqual(self._get_attempts(), 0)
        self.assertFalse(self._is_blocked())

    # ── Transición: Bloqueado → Libre (timeout expira) ──

    def test_PE008_bloqueado_a_libre_por_timeout(self):
        """δ(Bloqueado, timeout_expira) = Libre."""
        for _ in range(settings.AUTHZ_LOGIN_MAX_ATTEMPTS):
            self._do_failed_login()
        self.assertTrue(self._is_blocked())

        k_attempts, k_block = self._get_keys()
        cache.delete(k_attempts)
        cache.delete(k_block)

        self.assertFalse(self._is_blocked())
        self.assertEqual(self._get_attempts(), 0)

    # ── Transición: Acumulando → Libre (timeout expira) ──

    def test_PE009_acumulando_a_libre_por_timeout(self):
        """δ(Acumulando(n), timeout_expira) = Libre."""
        for _ in range(3):
            self._do_failed_login()
        self.assertEqual(self._get_attempts(), 3)

        k_attempts, _ = self._get_keys()
        cache.delete(k_attempts)

        self.assertEqual(self._get_attempts(), 0)
        self.assertFalse(self._is_blocked())

    # ── Recorrido completo del autómata ──

    def test_PE010_recorrido_completo_libre_acumulando_bloqueado_libre(self):
        """Recorrido: Libre → Acumulando(1..4) → Bloqueado → timeout → Libre."""
        self.assertEqual(self._get_attempts(), 0)
        self.assertFalse(self._is_blocked())

        for i in range(1, settings.AUTHZ_LOGIN_MAX_ATTEMPTS):
            self._do_failed_login()
            self.assertEqual(self._get_attempts(), i)
            self.assertFalse(self._is_blocked())

        self._do_failed_login()
        self.assertTrue(self._is_blocked())

        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

        k_attempts, k_block = self._get_keys()
        cache.delete(k_attempts)
        cache.delete(k_block)
        self.assertFalse(self._is_blocked())

        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    # ── Aislamiento por usuario/IP ──

    def test_PE011_bloqueo_aislado_por_usuario(self):
        """El bloqueo de un usuario NO afecta a otro usuario."""
        for _ in range(settings.AUTHZ_LOGIN_MAX_ATTEMPTS):
            self._do_failed_login("admin")
        self.assertTrue(self._is_blocked("admin"))

        self.assertFalse(self._is_blocked("operador"))
        response = self.client.post(
            "/api/auth/login",
            {"username": "operador", "password": "Oper$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)


# =============================================================================
# SECCIÓN 10 – Pruebas de Integración (4.3)
#
# Verifican la interacción entre componentes reales de authz:
# views ↔ utils ↔ models ↔ middleware ↔ signals ↔ decorators
# y la integración cross-app con el módulo animals.
# =============================================================================

class IntegracionLoginRBACTest(AuthzBaseTestCase):
    """PI-001 a PI-007: Cadenas de integración entre componentes."""

    # ── Cadena 1: Login → RBAC → Recurso protegido → Auditoría ──

    def test_PI001_login_rbac_acceso_y_auditoria_completa(self):
        """Cadena completa: login vía API → sesión creada → acceso a
        recurso protegido (/demo/secure) verificado por decorador
        require_perm → AuditLog registra login_success.
        Componentes: api_login → authenticate → login → session →
        require_perm → has_perm_code → user_permission_codes.
        """
        response = self.client.post(
            "/api/auth/login",
            {"username": "operador", "password": "Oper$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            AuditLog.objects.filter(
                action="login_success",
                user=self.operador_user,
            ).exists()
        )

    # ── Cadena 2: Login → Sin permiso → 403 → Middleware audita ──

    def test_PI002_login_sin_permiso_403_middleware_audita(self):
        """Cadena: login OK → acceso a recurso sin permiso → decorador
        retorna 403 → Log403Middleware captura → AuditLog(forbidden_403).
        Componentes: login → require_perm → HttpResponseForbidden →
        Log403Middleware → AuditLog.
        """
        user_limitado = User.objects.create_user(
            username="limitado", password="Lim$1234"
        )
        self.client.login(username="limitado", password="Lim$1234")

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 403)

        log = AuditLog.objects.filter(
            action="forbidden_403",
            user=user_limitado,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get("path"), "/demo/secure")

    # ── Cadena 3: Cambio de permisos → Efecto inmediato ──

    def test_PI003_cambio_de_rol_efecto_inmediato(self):
        """Cadena: operador accede OK → se elimina su rol → siguiente
        request retorna 403 → se reasigna rol → accede de nuevo.
        Componentes: require_perm → user_permission_codes → UserRole.
        """
        self.client.login(username="operador", password="Oper$1234")

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

        UserRole.objects.filter(
            user=self.operador_user, role=self.rol_operador
        ).delete()

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 403)

        UserRole.objects.create(user=self.operador_user, role=self.rol_operador)

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

    # ── Cadena 4: Login → Acceso cross-app a animals ──

    def test_PI004_login_acceso_cross_app_animals(self):
        """Cadena cross-app: login authz → acceso a /animals/ (app animals)
        protegido por @require_perm("animals.read") → listado OK.
        Componentes: authz.login → animals.views.animal_list →
        authz.decorators.require_perm.
        """
        self.client.login(username="operador", password="Oper$1234")
        response = self.client.get("/animals/")
        self.assertEqual(response.status_code, 200)

    def test_PI005_login_sin_permiso_animals_403(self):
        """Cadena cross-app denegada: usuario sin animals.read intenta
        acceder a /animals/ → 403.
        """
        User.objects.create_user(username="noanimal", password="NoAn$1234")
        self.client.login(username="noanimal", password="NoAn$1234")
        response = self.client.get("/animals/")
        self.assertEqual(response.status_code, 403)

    # ── Cadena 5: Bloqueo → Timeout → Login exitoso → Acceso ──

    def test_PI006_bloqueo_timeout_recuperacion_completa(self):
        """Cadena completa de bloqueo: N fallos → Bloqueado → 429 →
        timeout (simulado) → login exitoso → acceso a recurso OK.
        Componentes: _register_failed → _is_blocked → cache expiry →
        authenticate → login → require_perm.
        """
        for _ in range(settings.AUTHZ_LOGIN_MAX_ATTEMPTS):
            self.client.post(
                "/api/auth/login",
                {"username": "admin", "password": "incorrecta"},
                content_type="application/json",
            )

        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

        cache.clear()

        response = self.client.post(
            "/api/auth/login",
            {"username": "admin", "password": "Admin$1234"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

    # ── Cadena 6: Logout → Sesión invalidada → Recurso inaccesible ──

    def test_PI007_logout_invalida_acceso_a_recursos(self):
        """Cadena: login → acceso OK → logout → mismo recurso redirige.
        Componentes: login → session → logout → session destroyed →
        @login_required redirect.
        """
        self.client.login(username="admin", password="Admin$1234")

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

        self.client.get("/logout/")

        response = self.client.get("/demo/secure")
        self.assertIn(response.status_code, [302, 403])


# =============================================================================
# SECCIÓN 11 – Pruebas de Sistema (4.4)
#
# Simulan flujos completos de usuario de principio a fin, tal como los
# ejecutaría un actor real a través del navegador.
# =============================================================================

class SistemaFlujoCompletoTest(AuthzBaseTestCase):
    """PS-001 a PS-005: Flujos de sistema end-to-end."""

    # ── Flujo 1: Jornada completa de Administrador ──

    def test_PS001_jornada_admin_login_navegar_logout(self):
        """Flujo: Admin inicia sesión → accede al listado de animales →
        verifica su identidad vía API → cierra sesión →
        no puede acceder después.
        """
        response = self.client.post("/login/", {
            "username": "admin",
            "password": "Admin$1234",
        })
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/animals/")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/auth/me")
        data = response.json()
        self.assertEqual(data["username"], "admin")
        self.assertIn("ADMIN", data["roles"])

        response = self.client.get("/logout/")
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/animals/")
        self.assertIn(response.status_code, [302, 403])

    # ── Flujo 2: Operador limitado por RBAC ──

    def test_PS002_operador_accede_solo_lectura(self):
        """Flujo: Operador inicia sesión → puede ver animales (read) →
        NO tiene permiso users.manage → cierra sesión.
        """
        self.client.login(username="operador", password="Oper$1234")

        response = self.client.get("/animals/")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/auth/me")
        data = response.json()
        self.assertIn("animals.read", data["permissions"])
        self.assertNotIn("users.manage", data["permissions"])

        response = self.client.get("/logout/")
        self.assertEqual(response.status_code, 302)

    # ── Flujo 3: Múltiples usuarios concurrentes aislados ──

    def test_PS003_sesiones_aisladas_entre_usuarios(self):
        """Flujo: Admin y Operador inician sesión en clientes separados →
        cada uno ve sus propios permisos → el logout de uno no afecta
        al otro.
        """
        client_admin = Client()
        client_operador = Client()

        client_admin.login(username="admin", password="Admin$1234")
        client_operador.login(username="operador", password="Oper$1234")

        resp_admin = client_admin.get("/api/auth/me")
        self.assertIn("users.manage", resp_admin.json()["permissions"])

        resp_oper = client_operador.get("/api/auth/me")
        self.assertNotIn("users.manage", resp_oper.json()["permissions"])

        client_admin.get("/logout/")

        response = client_operador.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

        response = client_admin.get("/demo/secure")
        self.assertIn(response.status_code, [302, 403])

    # ── Flujo 4: Recuperación de contraseña accesible ──

    def test_PS004_flujo_recuperacion_contrasena_accesible(self):
        """Flujo: Usuario no autenticado accede a /password_reset/ →
        el formulario está disponible (200).
        """
        response = self.client.get("/password_reset/")
        self.assertEqual(response.status_code, 200)

    # ── Flujo 5: Auditoría completa de una sesión ──

    def test_PS005_auditoria_completa_de_sesion(self):
        """Flujo: Login → acceso a recurso → logout. Verifica que
        TODOS los eventos quedan registrados en AuditLog con la
        secuencia correcta (login_success antes de logout).
        """
        AuditLog.objects.all().delete()

        self.client.post("/login/", {
            "username": "operador",
            "password": "Oper$1234",
        })

        response = self.client.get("/demo/secure")
        self.assertEqual(response.status_code, 200)

        self.client.get("/logout/")

        logs = list(
            AuditLog.objects.order_by("created_at").values_list("action", flat=True)
        )
        login_indices = [i for i, a in enumerate(logs) if a == "login_success"]
        logout_indices = [i for i, a in enumerate(logs) if a == "logout"]
        self.assertTrue(len(login_indices) > 0, "No se registró login_success")
        self.assertTrue(len(logout_indices) > 0, "No se registró logout")
        self.assertLess(
            login_indices[0], logout_indices[0],
            "login_success debe ocurrir antes que logout en la auditoría"
        )