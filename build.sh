#!/usr/bin/env bash
# Build script ejecutado por Render en cada deploy.
# Usa el módulo settings_render para no tocar el settings.py local.
set -o errexit

export DJANGO_SETTINGS_MODULE=finca_ganadera.settings_render

# 1. Instalar dependencias Python
pip install --upgrade pip
pip install -r requirements.txt

# 2. Recolectar archivos estáticos en staticfiles/ (servido por WhiteNoise)
python manage.py collectstatic --noinput

# 3. Crear la tabla de cache de Django (idempotente; si ya existe no falla)
python manage.py createcachetable || true

# 4. Aplicar migraciones de base de datos
python manage.py migrate --noinput
