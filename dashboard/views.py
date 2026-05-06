"""
CU-009: Panel Principal (Dashboard)
Vista de solo lectura que agrega KPIs de todos los módulos en tiempo real.
"""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Subquery, OuterRef
from django.shortcuts import render
from django.utils import timezone

from animals.models import Animal
from alertas.models import Alerta
from authz.decorators import require_perm
from authz.models import AuditLog
from eventos.models import EventoSanitario
from pesajes.models import Pesaje
from potreros.models import Potrero
from transacciones.models import Transaccion


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _rango_mes_anterior(hoy):
    if hoy.month == 1:
        inicio = date(hoy.year - 1, 12, 1)
        fin = date(hoy.year, 1, 1) - timedelta(days=1)
    else:
        inicio = date(hoy.year, hoy.month - 1, 1)
        fin = date(hoy.year, hoy.month, 1) - timedelta(days=1)
    return inicio, fin


def _variacion(actual, anterior):
    """Devuelve dict con delta y signo, o None si no hay datos anteriores."""
    if anterior is None or anterior == 0:
        return None
    delta = round(actual - anterior, 1)
    return {"delta": delta, "delta_abs": abs(delta), "positivo": delta >= 0}


def _calcular_kpis():
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    inicio_mes_anterior, fin_mes_anterior = _rango_mes_anterior(hoy)

    # ── KPI 1: Animales Activos (CU-002) ────────────────────────────────────
    total_activos = Animal.objects.filter(estado=Animal.Estado.ACTIVO).count()

    # ── KPI 2: Peso Promedio del Hato kg (CU-004) ───────────────────────────
    ultimo_pesaje_sq = (
        Pesaje.objects.filter(animal=OuterRef("pk"))
        .order_by("-fecha", "-created_at")
        .values("peso_kg")[:1]
    )
    peso_result = (
        Animal.objects.filter(estado=Animal.Estado.ACTIVO)
        .annotate(ultimo_peso=Subquery(ultimo_pesaje_sq))
        .aggregate(avg=Avg("ultimo_peso"))
    )
    peso_promedio = round(float(peso_result["avg"] or 0), 1)

    # Peso promedio mes anterior (pesajes registrados en ese periodo)
    peso_anterior_result = Pesaje.objects.filter(
        fecha__range=(inicio_mes_anterior, fin_mes_anterior),
        animal__estado=Animal.Estado.ACTIVO,
    ).aggregate(avg=Avg("peso_kg"))
    peso_anterior = round(float(peso_anterior_result["avg"] or 0), 1)

    # ── KPI 3: Ocupación Promedio Potreros % (CU-005) ───────────────────────
    potreros_activos = Potrero.objects.filter(estado="ACTIVO", capacidad_maxima__gt=0)
    total_pct = 0.0
    count_p = 0
    for p in potreros_activos:
        activos_p = Animal.objects.filter(
            potrero=p, estado=Animal.Estado.ACTIVO
        ).count()
        total_pct += activos_p / p.capacidad_maxima * 100
        count_p += 1
    ocupacion_promedio = round(total_pct / count_p, 1) if count_p > 0 else 0.0

    # ── KPI 4: Alertas Pendientes (CU-008) ──────────────────────────────────
    alertas_pendientes = Alerta.objects.filter(
        estado=Alerta.Estado.PENDIENTE
    ).count()

    # ── KPI 5: Transacciones del Mes (CU-006) ───────────────────────────────
    transacciones_mes = Transaccion.objects.filter(
        fecha__gte=inicio_mes,
        estado=Transaccion.Estado.CONFIRMADO,
    ).count()
    transacciones_anterior = Transaccion.objects.filter(
        fecha__range=(inicio_mes_anterior, fin_mes_anterior),
        estado=Transaccion.Estado.CONFIRMADO,
    ).count()

    # ── KPI 6: Cumplimiento Sanitario % (CU-003) ────────────────────────────
    fecha_limite = hoy - timedelta(days=90)
    animales_al_dia = (
        Animal.objects.filter(
            estado=Animal.Estado.ACTIVO,
            eventos__estado=EventoSanitario.Estado.REALIZADO,
            eventos__fecha__gte=fecha_limite,
        )
        .distinct()
        .count()
    )
    cumplimiento = round(animales_al_dia / total_activos * 100, 1) if total_activos > 0 else 0.0

    fecha_limite_ant = hoy - timedelta(days=180)
    animales_al_dia_ant = (
        Animal.objects.filter(
            estado=Animal.Estado.ACTIVO,
            eventos__estado=EventoSanitario.Estado.REALIZADO,
            eventos__fecha__gte=fecha_limite_ant,
            eventos__fecha__lt=fecha_limite,
        )
        .distinct()
        .count()
    )
    cumplimiento_anterior = (
        round(animales_al_dia_ant / total_activos * 100, 1) if total_activos > 0 else 0.0
    )

    return {
        "animales_activos": {
            "titulo": "Animales Activos",
            "valor": total_activos,
            "unidad": "animales",
            "icono": "bi-tag",
            "color": "primary",
            "variacion": None,
            "url_nombre": "animals:list",
        },
        "peso_promedio": {
            "titulo": "Peso Promedio del Hato",
            "valor": peso_promedio,
            "unidad": "kg",
            "icono": "bi-graph-up",
            "color": "info",
            "variacion": _variacion(peso_promedio, peso_anterior),
            "url_nombre": "pesajes:list",
        },
        "ocupacion_potreros": {
            "titulo": "Ocupación Promedio Potreros",
            "valor": ocupacion_promedio,
            "unidad": "%",
            "icono": "bi-grid-3x3-gap",
            "color": "success",
            "variacion": None,
            "url_nombre": "potreros:list",
        },
        "alertas_pendientes": {
            "titulo": "Alertas Pendientes",
            "valor": alertas_pendientes,
            "unidad": "alertas",
            "icono": "bi-bell",
            "color": "danger",
            "variacion": None,
            "url_nombre": "alertas:index",
        },
        "transacciones_mes": {
            "titulo": "Transacciones del Mes",
            "valor": transacciones_mes,
            "unidad": "transacciones",
            "icono": "bi-arrow-left-right",
            "color": "warning",
            "variacion": _variacion(transacciones_mes, transacciones_anterior),
            "url_nombre": "transacciones:list",
        },
        "cumplimiento_sanitario": {
            "titulo": "Cumplimiento Sanitario",
            "valor": cumplimiento,
            "unidad": "%",
            "icono": "bi-shield-check",
            "color": "success",
            "variacion": _variacion(cumplimiento, cumplimiento_anterior),
            "url_nombre": "eventos:list",
        },
    }


def _get_actividad_reciente():
    """Últimas 10 operaciones del sistema (pesajes + eventos + transacciones)."""
    pesajes = list(
        Pesaje.objects.select_related("animal", "created_by")
        .order_by("-created_at")[:10]
    )
    eventos = list(
        EventoSanitario.objects.select_related("animal", "created_by")
        .order_by("-created_at")[:10]
    )
    transacciones = list(
        Transaccion.objects.select_related("animal", "created_by")
        .order_by("-created_at")[:10]
    )

    items = []
    for p in pesajes:
        items.append({
            "tipo": "Pesaje",
            "fecha": p.created_at,
            "descripcion": f"Pesaje registrado: {p.peso_kg} kg",
            "animal": p.animal,
            "usuario": p.created_by,
            "icono": "bi-graph-up",
            "color": "primary",
            "url": f"/pesajes/{p.pk}/",
        })
    for e in eventos:
        items.append({
            "tipo": "Evento sanitario",
            "fecha": e.created_at,
            "descripcion": e.tipo,
            "animal": e.animal,
            "usuario": e.created_by,
            "icono": "bi-activity",
            "color": "success",
            "url": f"/animals/{e.animal_id}/",
        })
    for t in transacciones:
        items.append({
            "tipo": "Transacción",
            "fecha": t.created_at,
            "descripcion": t.get_tipo_display(),
            "animal": t.animal,
            "usuario": t.created_by,
            "icono": "bi-arrow-left-right",
            "color": "warning",
            "url": f"/transacciones/{t.pk}/",
        })

    items.sort(key=lambda x: x["fecha"], reverse=True)
    return items[:10]


def _get_potreros_ocupacion():
    resultado = []
    for p in Potrero.objects.filter(estado="ACTIVO"):
        activos = Animal.objects.filter(
            potrero=p, estado=Animal.Estado.ACTIVO
        ).count()
        if p.capacidad_maxima > 0:
            pct = min(round(activos / p.capacidad_maxima * 100), 100)
        else:
            pct = 0
        color = "danger" if pct >= 90 else ("warning" if pct >= 70 else "success")
        resultado.append({
            "potrero": p,
            "activos": activos,
            "pct": pct,
            "color": color,
        })
    resultado.sort(key=lambda x: x["pct"], reverse=True)
    return resultado


@login_required
@require_perm("dashboard.read")
def index(request):
    kpis = {}
    error_kpis = False
    try:
        kpis = _calcular_kpis()
    except Exception:
        error_kpis = True

    actividad = []
    try:
        actividad = _get_actividad_reciente()
    except Exception:
        pass

    potreros_ocupacion = []
    try:
        potreros_ocupacion = _get_potreros_ocupacion()
    except Exception:
        pass

    alertas_urgentes = list(
        Alerta.objects.filter(estado=Alerta.Estado.PENDIENTE)
        .order_by("fecha_objetivo")[:5]
    )

    sin_datos = Animal.objects.filter(estado=Animal.Estado.ACTIVO).count() == 0

    # RN-5: Auditoría de acceso al Dashboard (CU-010)
    AuditLog.objects.create(
        user=request.user,
        action="dashboard_acceso",
        ip=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
    )

    return render(request, "dashboard/index.html", {
        "kpis": kpis,
        "error_kpis": error_kpis,
        "actividad": actividad,
        "potreros_ocupacion": potreros_ocupacion,
        "alertas_urgentes": alertas_urgentes,
        "sin_datos": sin_datos,
        "now": timezone.now(),
    })
