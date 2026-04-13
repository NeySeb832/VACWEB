import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "django-insecure-change-me"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "authz",    # app del CU-001
    "animals",  # app del CU-002
    "eventos",  # app del CU-003
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Middleware para auditar 403 (CU-001, RN-4)
    "authz.middleware.Log403Middleware",
]

ROOT_URLCONF = "finca_ganadera.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "finca_ganadera.wsgi.application"

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'soft_animales',
        'USER': 'root',
        'PASSWORD': 'OneySeb832@',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CU-001: Políticas de sesión (RN-2)
SESSION_COOKIE_AGE = 30 * 60  # 30 min
SESSION_SAVE_EVERY_REQUEST = True  # renovar expiración por actividad

# --- CU-001: Email de recuperación (dev: consola)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@finca.local"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# --- DRF base (deny by default con IsAuthenticated en vistas; decoradores aplicarán permisos)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "2000/hour",
        "anon": "60/hour",
    },
}

# --- CU-001: Bloqueo por intentos (RN-1)
AUTHZ_LOGIN_MAX_ATTEMPTS = 5
AUTHZ_LOGIN_BLOCK_MINUTES = 10

# --- Cache para contadores y bloqueo (RN-1)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "authz-locmem",
        "TIMEOUT": None,
    }
}

# Al lado de STATIC_URL
STATIC_URL = "static/"

MEDIA_URL = "/media/"              # OJO: con / al inicio y al final
MEDIA_ROOT = BASE_DIR / "media"    # <proyecto>/media

