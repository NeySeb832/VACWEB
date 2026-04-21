# reportes/views.py
"""Vistas del módulo de Reportes y Analítica (CU-007).
Genera, visualiza y exporta reportes de inventario, historial, sanitario y ventas.
"""
import csv
import logging
from datetime import date as _date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import render

from animals.models import Animal
from authz.decorators import require_perm
from authz.models import AuditLog
from eventos.models import EventoSanitario
from pesajes.models import Pesaje
from potreros.models import Potrero
from transacciones.models import Transaccion

from .models import LogReporte

logger = logging.getLogger(__name__)

PERM_REPORTES = "reportes.read"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str):
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError, AttributeError):
        return None


def _get_date_filters(request):
    """Extrae, parsea y valida rango de fechas desde GET params (RN-1)."""
    desde_raw = request.GET.get("desde", "").strip()
    hasta_raw = request.GET.get("hasta", "").strip()
    desde = _parse_date(desde_raw) if desde_raw else None
    hasta = _parse_date(hasta_raw) if hasta_raw else None
    error_fechas = None
    if desde and hasta and desde > hasta:
        error_fechas = (
            "El rango de fechas no es válido — "
            "la fecha inicial debe ser anterior o igual a la fecha final."
        )
    return desde, hasta, desde_raw, hasta_raw, error_fechas


def _registrar_log(request, tipo_reporte: str, filtros: dict, formato: str = ""):
    """Registra el evento en AuditLog (CU-10) y en LogReporte (RN-5)."""
    accion = f"reporte.{tipo_reporte}" + (f".{formato}" if formato else "")
    AuditLog.objects.create(
        user=request.user,
        action=accion,
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        metadata={
            "entidad": "Reporte",
            "tipo_reporte": tipo_reporte,
            "filtros": filtros,
            "formato": formato or "html",
        },
    )
    LogReporte.objects.create(
        usuario=request.user,
        tipo_reporte=tipo_reporte,
        filtros_aplicados=filtros,
        formato_exportacion=formato,
        ip=request.META.get("REMOTE_ADDR"),
    )


def _csv_response(filename: str) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("\ufeff")  # BOM para compatibilidad con Excel
    return resp


# ---------------------------------------------------------------------------
# Vista 1: Índice / selector de reportes
# ---------------------------------------------------------------------------

@login_required
@require_perm(PERM_REPORTES)
def reporte_index(request):
    potreros = Potrero.objects.filter(estado=Potrero.Estado.ACTIVO).order_by("nombre_codigo")
    ctx = {
        "potreros":      potreros,
        "desde":         request.GET.get("desde", ""),
        "hasta":         request.GET.get("hasta", ""),
        "lote_filtro":   request.GET.get("lote", ""),
        "estado_filtro": request.GET.get("estado", ""),
        "today":         str(_date.today()),
    }
    return render(request, "reportes/index.html", ctx)


# ---------------------------------------------------------------------------
# Vista 2: Inventario actual de animales
# ---------------------------------------------------------------------------

@login_required
@require_perm(PERM_REPORTES)
def reporte_inventario(request):
    hoy = _date.today()
    desde, hasta, desde_raw, hasta_raw, error_fechas = _get_date_filters(request)
    lote_raw    = request.GET.get("lote", "").strip()
    estado_raw  = request.GET.get("estado", "").strip()
    exportar    = request.GET.get("exportar", "").strip()

    filtros = {"desde": desde_raw, "hasta": hasta_raw, "lote": lote_raw, "estado": estado_raw}

    qs = Animal.objects.select_related("potrero").prefetch_related(
        Prefetch(
            "pesajes",
            queryset=Pesaje.objects.order_by("-fecha", "-created_at"),
            to_attr="pesajes_list",
        )
    )

    if not error_fechas and desde:
        qs = qs.filter(fecha_ingreso__gte=desde)
    if not error_fechas and hasta:
        qs = qs.filter(fecha_ingreso__lte=hasta)

    if lote_raw:
        try:
            qs = qs.filter(potrero_id=int(lote_raw))
        except ValueError:
            pass

    if estado_raw:
        qs = qs.filter(estado=estado_raw)
    else:
        qs = qs.filter(estado=Animal.Estado.ACTIVO)

    qs = qs.order_by("potrero__nombre_codigo", "rfid", "arete")

    # Construir lista enriquecida con peso actual y días en finca
    animals_data = []
    for animal in qs:
        peso = animal.pesajes_list[0].peso_kg if animal.pesajes_list else None
        dias = (hoy - animal.fecha_ingreso).days if animal.fecha_ingreso else None
        animals_data.append({"animal": animal, "peso_actual": peso, "dias_en_finca": dias})

    # KPIs
    total   = len(animals_data)
    machos  = sum(1 for d in animals_data if d["animal"].sexo == Animal.Sexo.MACHO)
    hembras = sum(1 for d in animals_data if d["animal"].sexo == Animal.Sexo.HEMBRA)
    pesos   = [float(d["peso_actual"]) for d in animals_data if d["peso_actual"]]
    peso_promedio = round(sum(pesos) / len(pesos), 1) if pesos else None

    # Exportar CSV
    if exportar == "csv" and not error_fechas:
        _registrar_log(request, "inventario", filtros, "csv")
        resp = _csv_response(f"reporte_inventario_{hoy}.csv")
        writer = csv.writer(resp)
        writer.writerow(["RFID", "Arete", "Raza", "Sexo", "Etapa", "Nacimiento",
                         "Lote", "Peso (kg)", "Días en finca", "Estado"])
        for d in animals_data:
            a = d["animal"]
            writer.writerow([
                a.rfid or "",
                a.arete or "",
                a.raza or "",
                a.get_sexo_display() if a.sexo else "",
                a.get_etapa_display() if a.etapa else "",
                a.fecha_nacimiento.strftime("%d/%m/%Y") if a.fecha_nacimiento else "",
                str(a.potrero) if a.potrero else "",
                d["peso_actual"] or "",
                d["dias_en_finca"] if d["dias_en_finca"] is not None else "",
                a.get_estado_display(),
            ])
        return resp

    if not exportar and not error_fechas:
        _registrar_log(request, "inventario", filtros)

    potreros = Potrero.objects.filter(estado=Potrero.Estado.ACTIVO).order_by("nombre_codigo")
    ctx = {
        "animals_data":   animals_data,
        "total":          total,
        "machos":         machos,
        "hembras":        hembras,
        "peso_promedio":  peso_promedio,
        "potreros":       potreros,
        "desde":          desde_raw,
        "hasta":          hasta_raw,
        "lote_filtro":    lote_raw,
        "estado_filtro":  estado_raw,
        "error_fechas":   error_fechas,
        "estado_choices": Animal.Estado.choices,
        "today":          str(hoy),
        "fecha_gen":      hoy,
    }
    return render(request, "reportes/inventario.html", ctx)


# ---------------------------------------------------------------------------
# Vista 3: Historial individual por animal
# ---------------------------------------------------------------------------

@login_required
@require_perm(PERM_REPORTES)
def reporte_historial_animal(request):
    hoy = _date.today()
    desde, hasta, desde_raw, hasta_raw, error_fechas = _get_date_filters(request)
    lote_raw   = request.GET.get("lote", "").strip()
    estado_raw = request.GET.get("estado", "").strip()
    exportar   = request.GET.get("exportar", "").strip()

    filtros = {"desde": desde_raw, "hasta": hasta_raw, "lote": lote_raw, "estado": estado_raw}

    # Construir querysets de sub-recursos con filtros de fecha
    eventos_qs = EventoSanitario.objects.all()
    pesajes_qs = Pesaje.objects.all()

    if not error_fechas:
        if desde:
            eventos_qs = eventos_qs.filter(fecha__gte=desde)
            pesajes_qs = pesajes_qs.filter(fecha__gte=desde)
        if hasta:
            eventos_qs = eventos_qs.filter(fecha__lte=hasta)
            pesajes_qs = pesajes_qs.filter(fecha__lte=hasta)

    qs = Animal.objects.select_related("potrero").prefetch_related(
        Prefetch("eventos",    queryset=eventos_qs,  to_attr="eventos_periodo"),
        Prefetch("pesajes",    queryset=pesajes_qs,  to_attr="pesajes_periodo"),
        Prefetch("movimientos", to_attr="movimientos_lista"),
    )

    if lote_raw:
        try:
            qs = qs.filter(potrero_id=int(lote_raw))
        except ValueError:
            pass

    if estado_raw:
        qs = qs.filter(estado=estado_raw)

    qs = qs.order_by("rfid", "arete")

    # Filtrar movimientos por rango de fechas en Python (no hay FK de fecha en prefetch fácil)
    animals_data = []
    for animal in qs:
        movs = list(animal.movimientos_lista)
        if not error_fechas:
            if desde:
                movs = [m for m in movs if m.fecha >= desde]
            if hasta:
                movs = [m for m in movs if m.fecha <= hasta]
        animals_data.append({
            "animal":     animal,
            "n_eventos":  len(animal.eventos_periodo),
            "n_pesajes":  len(animal.pesajes_periodo),
            "n_movs":     len(movs),
        })

    potreros = Potrero.objects.filter(estado=Potrero.Estado.ACTIVO).order_by("nombre_codigo")

    if exportar == "csv" and not error_fechas:
        _registrar_log(request, "historial", filtros, "csv")
        resp = _csv_response(f"reporte_historial_{hoy}.csv")
        writer = csv.writer(resp)
        writer.writerow(["RFID", "Arete", "Raza", "Lote", "Estado",
                         "Eventos Sanitarios", "Pesajes", "Movimientos"])
        for d in animals_data:
            a = d["animal"]
            writer.writerow([
                a.rfid or "",
                a.arete or "",
                a.raza or "",
                str(a.potrero) if a.potrero else "",
                a.get_estado_display(),
                d["n_eventos"],
                d["n_pesajes"],
                d["n_movs"],
            ])
        return resp

    if not exportar and not error_fechas:
        _registrar_log(request, "historial", filtros)

    total_eventos = sum(d["n_eventos"] for d in animals_data)
    total_pesajes = sum(d["n_pesajes"] for d in animals_data)

    ctx = {
        "animals_data":   animals_data,
        "total_animales": len(animals_data),
        "total_eventos":  total_eventos,
        "total_pesajes":  total_pesajes,
        "potreros":       potreros,
        "desde":          desde_raw,
        "hasta":          hasta_raw,
        "lote_filtro":    lote_raw,
        "estado_filtro":  estado_raw,
        "error_fechas":   error_fechas,
        "estado_choices": Animal.Estado.choices,
        "today":          str(hoy),
        "fecha_gen":      hoy,
    }
    return render(request, "reportes/historial_animal.html", ctx)


# ---------------------------------------------------------------------------
# Vista 4: Calendario sanitario
# ---------------------------------------------------------------------------

@login_required
@require_perm(PERM_REPORTES)
def reporte_sanitario(request):
    hoy = _date.today()
    desde, hasta, desde_raw, hasta_raw, error_fechas = _get_date_filters(request)
    lote_raw      = request.GET.get("lote", "").strip()
    estado_raw    = request.GET.get("estado", "").strip()
    exportar      = request.GET.get("exportar", "").strip()

    filtros = {"desde": desde_raw, "hasta": hasta_raw, "lote": lote_raw, "estado": estado_raw}

    qs = (
        EventoSanitario.objects
        .select_related("animal", "animal__potrero", "created_by")
        .order_by("fecha", "animal__rfid")
    )

    if not error_fechas:
        if desde:
            qs = qs.filter(fecha__gte=desde)
        else:
            qs = qs.filter(fecha__gte=hoy)  # default: desde hoy hacia adelante
        if hasta:
            qs = qs.filter(fecha__lte=hasta)

    if lote_raw:
        try:
            qs = qs.filter(animal__potrero_id=int(lote_raw))
        except ValueError:
            pass

    if estado_raw:
        qs = qs.filter(estado=estado_raw)
    else:
        qs = qs.filter(estado__in=[EventoSanitario.Estado.CONFIRMADO, EventoSanitario.Estado.APLAZADO])

    eventos = list(qs)
    potreros = Potrero.objects.filter(estado=Potrero.Estado.ACTIVO).order_by("nombre_codigo")

    if exportar == "csv" and not error_fechas:
        _registrar_log(request, "sanitario", filtros, "csv")
        resp = _csv_response(f"reporte_sanitario_{hoy}.csv")
        writer = csv.writer(resp)
        writer.writerow(["Fecha", "Animal (RFID/Arete)", "Lote", "Tipo",
                         "Producto", "Dosis", "Responsable", "Estado"])
        for e in eventos:
            animal_id = e.animal.rfid or e.animal.arete or "SIN-ID"
            writer.writerow([
                e.fecha.strftime("%d/%m/%Y"),
                animal_id,
                str(e.animal.potrero) if e.animal.potrero else "",
                e.tipo,
                e.producto,
                e.dosis or "",
                e.responsable,
                e.get_estado_display(),
            ])
        return resp

    if not exportar and not error_fechas:
        _registrar_log(request, "sanitario", filtros)

    confirmados = sum(1 for e in eventos if e.estado == EventoSanitario.Estado.CONFIRMADO)
    aplicados   = sum(1 for e in eventos if e.estado == EventoSanitario.Estado.APLAZADO)

    ctx = {
        "eventos":        eventos,
        "total_eventos":  len(eventos),
        "confirmados":    confirmados,
        "aplicados":      aplicados,
        "potreros":       potreros,
        "desde":          desde_raw,
        "hasta":          hasta_raw,
        "lote_filtro":    lote_raw,
        "estado_filtro":  estado_raw,
        "error_fechas":   error_fechas,
        "estado_choices": EventoSanitario.Estado.choices,
        "today":          str(hoy),
        "fecha_gen":      hoy,
    }
    return render(request, "reportes/sanitario.html", ctx)


# ---------------------------------------------------------------------------
# Vista 5: Reporte de ventas
# ---------------------------------------------------------------------------

@login_required
@require_perm(PERM_REPORTES)
def reporte_ventas(request):
    hoy = _date.today()
    desde, hasta, desde_raw, hasta_raw, error_fechas = _get_date_filters(request)
    lote_raw = request.GET.get("lote", "").strip()
    exportar = request.GET.get("exportar", "").strip()

    filtros = {"desde": desde_raw, "hasta": hasta_raw, "lote": lote_raw}

    qs = (
        Transaccion.objects
        .filter(tipo=Transaccion.Tipo.VENTA, estado=Transaccion.Estado.CONFIRMADO)
        .select_related("animal", "animal__potrero", "created_by")
        .order_by("-fecha", "-created_at")
    )

    if not error_fechas:
        if desde:
            qs = qs.filter(fecha__gte=desde)
        if hasta:
            qs = qs.filter(fecha__lte=hasta)

    if lote_raw:
        try:
            qs = qs.filter(animal__potrero_id=int(lote_raw))
        except ValueError:
            pass

    ventas       = list(qs)
    total_ventas = len(ventas)
    peso_total   = sum(float(v.peso_final_kg) for v in ventas if v.peso_final_kg) or 0
    valor_total  = sum(float(v.valor_cop) for v in ventas) or 0

    potreros = Potrero.objects.filter(estado=Potrero.Estado.ACTIVO).order_by("nombre_codigo")

    if exportar == "csv" and not error_fechas:
        _registrar_log(request, "ventas", filtros, "csv")
        resp = _csv_response(f"reporte_ventas_{hoy}.csv")
        writer = csv.writer(resp)
        writer.writerow(["Fecha", "Animal (RFID/Arete)", "Lote", "Destino",
                         "Peso (kg)", "Valor (COP)", "Registrado por"])
        for v in ventas:
            animal_id = v.animal.rfid or v.animal.arete or "SIN-ID"
            registrado = ""
            if v.created_by:
                registrado = v.created_by.get_full_name() or v.created_by.username
            writer.writerow([
                v.fecha.strftime("%d/%m/%Y"),
                animal_id,
                str(v.animal.potrero) if v.animal.potrero else "",
                v.origen_destino,
                v.peso_final_kg or "",
                v.valor_cop,
                registrado,
            ])
        return resp

    if not exportar and not error_fechas:
        _registrar_log(request, "ventas", filtros)

    ctx = {
        "ventas":        ventas,
        "total_ventas":  total_ventas,
        "peso_total":    peso_total,
        "valor_total":   valor_total,
        "potreros":      potreros,
        "desde":         desde_raw,
        "hasta":         hasta_raw,
        "lote_filtro":   lote_raw,
        "error_fechas":  error_fechas,
        "today":         str(hoy),
        "fecha_gen":     hoy,
    }
    return render(request, "reportes/ventas.html", ctx)
