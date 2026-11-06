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

# 5. Permisos y roles base del sistema (idempotente: no duplica ni borra nada)
python manage.py seed_rbac

# 6. Datos de demostración (usuarios demo, potreros, animales, pesajes, eventos)
#    - Se cargan automáticamente SOLO si la BD todavía no tiene usuarios
#      (primer deploy con una BD nueva). En los deploys siguientes se conservan
#      los datos que existan.
#    - Para RESETEAR la demo: en Render → Environment define
#      VACWEB_RESEED_DEMO=true, redespliega y luego quita la variable.
#      OJO: seed_demo borra los datos de negocio antes de recrearlos.
#    - Si la consulta falla por cualquier motivo, se asume que hay datos y NO
#      se siembra (nunca se borra nada por error).
if [ "${VACWEB_RESEED_DEMO:-false}" = "true" ] || \
   python manage.py shell -c "import sys; from django.contrib.auth.models import User; sys.exit(1 if User.objects.exists() else 0)"; then
    echo ">> Sembrando reglas de alertas y datos demo..."
    # Reglas de alertas (ninguna migración las crea; sin ellas no se generan alertas)
    python manage.py loaddata alertas/fixtures/reglas_alerta.json
    python manage.py seed_demo
    # seed_demo recrea los roles; completar las asignaciones del catálogo RBAC
    python manage.py seed_rbac
else
    echo ">> La BD ya tiene usuarios: se conservan los datos existentes."
fi
