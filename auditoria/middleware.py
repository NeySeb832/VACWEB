"""
CU-010: Middleware de interceptación automática.

Responsabilidades:
  1. Almacena el request activo en thread-local para que los signal handlers
     puedan leer user e IP sin necesitar el contexto HTTP explícitamente.
  2. Expone get_current_request() y registrar_bitacora() como utilidades
     que cualquier módulo puede llamar directamente.
"""
import threading

_thread_local = threading.local()


# ─── Acceso al request activo ────────────────────────────────────────────────

def get_current_request():
    """Devuelve el HttpRequest activo en este hilo, o None."""
    return getattr(_thread_local, "request", None)


def get_current_user():
    req = get_current_request()
    if req and hasattr(req, "user") and req.user.is_authenticated:
        return req.user
    return None


def get_client_ip(request=None):
    request = request or get_current_request()
    if not request:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ─── Función principal de registro ───────────────────────────────────────────

def registrar_bitacora(
    *,
    accion,
    entidad,
    entidad_id="",
    modulo_origen="",
    resumen="",
    valores_anteriores=None,
    valores_nuevos=None,
    user=None,
    ip=None,
    request=None,
):
    """
    Crea un registro inmutable en Bitacora.
    Se puede llamar desde signal handlers, vistas o cualquier capa de negocio.
    Si no se pasan user/ip, los lee del thread-local.
    """
    # Import diferido para evitar circular imports en arranque de Django
    from auditoria.models import Bitacora

    req = request or get_current_request()
    resolved_user = user or get_current_user()
    resolved_ip = ip or get_client_ip(req)

    if resolved_user:
        nombre = resolved_user.get_full_name() or resolved_user.username
    else:
        nombre = "Sistema"

    ua = ""
    if req:
        ua = req.META.get("HTTP_USER_AGENT", "")[:255]

    Bitacora.objects.create(
        user=resolved_user,
        usuario_nombre=nombre,
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id else "",
        modulo_origen=modulo_origen,
        resumen=resumen,
        valores_anteriores=valores_anteriores,
        valores_nuevos=valores_nuevos,
        ip_origen=resolved_ip,
        user_agent=ua,
    )


# ─── Middleware Django ────────────────────────────────────────────────────────

class AuditoriaMiddleware:
    """
    Almacena el HttpRequest en thread-local para acceso desde signals.
    Debe registrarse DESPUÉS de AuthenticationMiddleware en MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_local.request = request
        try:
            response = self.get_response(request)
        finally:
            # Limpia siempre al terminar el ciclo de request
            _thread_local.request = None
        return response
