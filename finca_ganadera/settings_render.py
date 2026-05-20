"""
Configuración de Django EXCLUSIVA para el despliegue en Render.

Diseño: importa todo desde el `settings.py` local (que no se toca) y solo
sobrescribe lo necesario para producción con Postgres + WhiteNoise + hardening.

Para usar este módulo, define en Render la variable de entorno:
    DJANGO_SETTINGS_MODULE = finca_ganadera.settings_render

(esto ya está configurado en `render.yaml`).

Para desarrollo local, NO definas esa variable y Django usará el `settings.py`
de siempre con tu MySQL local. Esta separación garantiza que el archivo
`settings.py` original no sea modificado por el flujo de despliegue.
"""
import os

import dj_database_url

# Importa toda la configuración base del settings.py local.
from .settings import *  # noqa: F401, F403
from .settings import BASE_DIR, MIDDLEWARE, CSRF_TRUSTED_ORIGINS

# ─── Seguridad / entorno ──────────────────────────────────────────────────────
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # obligatorio en Render
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")

# Render expone RENDER_EXTERNAL_HOSTNAME automáticamente.
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", ".onrender.com").split(",")
    if h.strip()
]
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

# ─── Base de datos: PostgreSQL administrado por Render ───────────────────────
# Render Postgres expone la URL via la variable DATABASE_URL.
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"],
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,  # Render Postgres requiere TLS
    )
}

# ─── WhiteNoise: archivos estáticos servidos por la propia app ───────────────
# Se inyecta JUSTO DESPUÉS de SecurityMiddleware (índice 1).
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    _security_idx = next(
        (i for i, m in enumerate(MIDDLEWARE)
         if m.endswith("SecurityMiddleware")),
        0,
    )
    MIDDLEWARE = (
        MIDDLEWARE[: _security_idx + 1]
        + ["whitenoise.middleware.WhiteNoiseMiddleware"]
        + MIDDLEWARE[_security_idx + 1 :]
    )

# Recolección y compresión de estáticos.
# IMPORTANTE: usamos CompressedStaticFilesStorage (sin "Manifest") porque
# algunos templates (ej. home.html) referencian {% static '...' %} sobre
# archivos que no están físicamente en el proyecto. La variante con manifiesto
# es estricta y lanza 500 ante esas referencias; la variante simple devuelve
# la URL aunque el archivo no exista (sale rota en HTML pero no rompe el render).
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# ─── CSRF: agregar dominio de Render ─────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS)  # copia para no mutar el original
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")
_extra_csrf = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS.extend(o.strip() for o in _extra_csrf.split(",") if o.strip())

# ─── Email vía SMTP (Gmail / Google Workspace) ───────────────────────────────
# En Render se configuran estas variables; si no están definidas, cae a consola.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("1", "true", "yes")
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False").lower() in ("1", "true", "yes")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "20"))  # segundos

# Remitente visible en los correos. Convención Gmail: usar el mismo correo del
# EMAIL_HOST_USER, opcionalmente con nombre amigable: "VACWEB <correo@dominio>".
DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL",
    f"VACWEB <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "no-reply@finca.local",
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL  # usado por Django para mensajes administrativos

# ─── Logging: mandar tracebacks de errores 500 a stderr (visible en Render) ──
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        # Mostrar tracebacks de las excepciones que Django captura en views.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# ─── Endurecimiento de seguridad (se activa solo si DEBUG=False) ─────────────
if not DEBUG:
    # Render termina TLS en su proxy; este header le indica a Django que la
    # petición original llegó por HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 días
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
