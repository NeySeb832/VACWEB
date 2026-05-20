# Despliegue de VACWEB en Render (rama `render`)

Este documento describe cómo desplegar VACWEB en [Render](https://render.com)
usando **PostgreSQL administrado** por la propia Render. Tu desarrollo local
sigue funcionando con MySQL exactamente como antes — la rama `render` es la
única que contiene la configuración de despliegue.

---

## Arquitectura

| Entorno | Rama git | Settings module | Base de datos | Servidor |
|---|---|---|---|---|
| **Local** | `main` | `finca_ganadera.settings` | MySQL `soft_animales@localhost` | `runserver` |
| **Render** | `render` | `finca_ganadera.settings_render` | PostgreSQL administrado por Render | Gunicorn + WhiteNoise |

`settings_render.py` importa todo de `settings.py` y solo sobrescribe lo
necesario para producción (DB, hosts, hardening, estáticos). De esa forma
**el `settings.py` original nunca se modifica**.

---

## Despliegue paso a paso

### 1. Subir la rama `render` a GitHub

Desde la raíz del proyecto, estando en la rama `render`:

```bash
git push -u origin render
```

> Si te aparece un error de "main has unstaged changes", confirmá que estés
> en `render` con `git branch --show-current`. La rama `render` ya tiene los
> archivos de despliegue commiteados.

### 2. Conectar Render al repo

1. Entrá a [Render Dashboard](https://dashboard.render.com).
2. Click en **New +** → **Blueprint**.
3. Conectá tu cuenta de GitHub si no lo hiciste antes.
4. Seleccioná el repositorio del proyecto.
5. **Importante:** asegurate de que la rama seleccionada sea **`render`**, no
   `main`. Render lee el `render.yaml` de esa rama.

### 3. Confirmar el blueprint

Render detectará `render.yaml` y propondrá crear:

- Un servicio web llamado **`vacweb`** (plan free).
- Una base de datos PostgreSQL llamada **`vacweb-db`** (plan free, 90 días).

Click en **Apply**. Render generará automáticamente:

- `DJANGO_SECRET_KEY` (variable con `generateValue: true`).
- `DATABASE_URL` (rellenado con la cadena de conexión a `vacweb-db`).

### 4. Esperar el primer deploy

El build toma ~3-5 minutos la primera vez. Lo que pasa en orden:

1. `pip install -r requirements.txt` (incluye `psycopg2-binary`, no `mysqlclient`).
2. `collectstatic` → genera `staticfiles/` con WhiteNoise.
3. `createcachetable` → crea la tabla de cache de Django.
4. `migrate` → aplica todas las migraciones contra el Postgres recién creado.
5. Gunicorn arranca y atiende peticiones.

Si todo va bien, el servicio queda **Live** y podés abrir
`https://vacweb.onrender.com` (o el subdominio que Render asigne).

### 5. Crear el primer superusuario

En el panel del servicio, abrí **Shell** (icono de terminal) y ejecutá:

```bash
python manage.py createsuperuser
```

O si tenés el comando de seed para datos demo:

```bash
python manage.py seed_demo
```

---

## Mantener la rama `render` al día

Cuando trabajés en `main` y querás llevar esos cambios al despliegue:

```bash
# Estando en main, commiteá tus cambios normalmente.
git checkout main
git add ...
git commit -m "feat: nueva funcionalidad"

# Llevá los cambios a render:
git checkout render
git merge main
git push origin render
```

Render detecta el push y redespliega automáticamente.

> **Atención al conflicto:** si hay un cambio en `settings.py` en `main`,
> verificá que tu `settings_render.py` siga sobrescribiendo correctamente lo
> que necesita. Por lo general no hay conflictos porque cada archivo se edita
> en su propia rama.

---

## Solución a problemas comunes

### `OperationalError: connection refused`
- Causa: la base Postgres aún no está lista cuando arranca Gunicorn.
- Solución: esperá 1-2 minutos al primer deploy. Render crea la BD antes que
  el web service, pero a veces hay desfase.

### `DJANGO_SECRET_KEY no está definida`
- Causa: el blueprint no se aplicó correctamente.
- Solución: en el panel del servicio → Environment → verificá que
  `DJANGO_SECRET_KEY` exista. Si no, agregala manualmente con una cadena
  aleatoria larga.

### Cold starts lentos (plan free)
- El servicio duerme tras 15 min de inactividad.
- La primera petición tras dormir tarda ~30-50 segundos en responder.
- Es comportamiento esperado del plan free; pagar el plan Starter lo elimina.

### Fotos que desaparecen tras un deploy
- En plan free el disco es **efímero**: `media/` se vacía en cada redeploy.
- Para persistencia real:
  - Integrar AWS S3 con `django-storages`, o
  - Usar el disco persistente de Render (plan pago, ~7 USD/mes).

### Cambios en local que no se reflejan en Render
- Render solo despliega desde la rama `render`. Si pusheaste a `main`, hacé
  el merge:
  ```bash
  git checkout render && git merge main && git push origin render
  ```

---

## Volver a desarrollo local

Tu `main` no fue tocada por nada de esto. Para volver a desarrollar:

```bash
git checkout main
```

Tu `settings.py` original con MySQL `soft_animales@localhost` está intacto.
Las variables de entorno de Render no afectan a tu entorno local (Django
solo las usa si `DJANGO_SETTINGS_MODULE=finca_ganadera.settings_render`,
cosa que en local nunca se define).
