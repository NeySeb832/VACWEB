"""
CU-010: Vistas del módulo de Auditoría / Bitácora.

Flujos cubiertos:
  - index      → listado paginado con filtros (GET)
  - detalle    → detalle completo de un registro con delta JSON
  - exportar_csv → descarga CSV con todos los registros filtrados
"""
import csv
import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from authz.decorators import require_perm
from auditoria.middleware import registrar_bitacora
from auditoria.models import Bitacora


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _aplicar_filtros(request, qs):
    """Aplica los filtros de la querystring al queryset. Devuelve (qs, filtros, error_rango)."""
    q       = request.GET.get("q", "").strip()
    usuario = request.GET.get("usuario", "").strip()
    entidad = request.GET.get("entidad", "").strip()
    accion  = request.GET.get("accion", "").strip()
    desde   = request.GET.get("desde", "").strip()
    hasta   = request.GET.get("hasta", "").strip()

    if q:
        qs = qs.filter(
            Q(usuario_nombre__icontains=q)
            | Q(entidad__icontains=q)
            | Q(resumen__icontains=q)
            | Q(entidad_id__icontains=q)
        )
    if usuario:
        qs = qs.filter(user_id=usuario)
    if entidad:
        qs = qs.filter(entidad=entidad)
    if accion:
        qs = qs.filter(accion=accion)

    error_rango = False
    if desde and hasta and desde > hasta:
        error_rango = True

    if not error_rango:
        if desde:
            qs = qs.filter(fecha__date__gte=desde)
        if hasta:
            qs = qs.filter(fecha__date__lte=hasta)

    filtros = {
        "q": q, "usuario": usuario, "entidad": entidad,
        "accion": accion, "desde": desde, "hasta": hasta,
    }
    return qs, filtros, error_rango


# ─── Vista principal ──────────────────────────────────────────────────────────

@login_required
@require_perm("auditoria.read")
def index(request):
    """Listado paginado de la bitácora con filtros (RN-5, CP-05, CP-10, CP-11)."""
    qs = Bitacora.objects.select_related("user").order_by("-fecha")
    qs, filtros, error_rango = _aplicar_filtros(request, qs)

    total = qs.count()

    # Contadores por tipo de acción (para los badges del mockup)
    stats = {
        "total":      total,
        "creaciones": Bitacora.objects.filter(accion=Bitacora.Accion.CREAR).count(),
        "ediciones":  Bitacora.objects.filter(accion=Bitacora.Accion.EDITAR).count(),
        "eliminaciones": Bitacora.objects.filter(accion=Bitacora.Accion.ELIMINAR).count(),
    }

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get("page", 1))

    # Opciones para los selectores de filtro
    usuarios_con_registros = (
        User.objects.filter(bitacora_entries__isnull=False)
        .distinct()
        .order_by("username")
    )
    entidades_disponibles = (
        Bitacora.objects.values_list("entidad", flat=True)
        .distinct()
        .order_by("entidad")
    )

    context = {
        "page_obj":              page_obj,
        "total":                 total,
        "stats":                 stats,
        "filtros":               filtros,
        "error_rango":           error_rango,
        "sin_resultados":        total == 0 and not error_rango,
        "usuarios_disponibles":  usuarios_con_registros,
        "entidades_disponibles": list(entidades_disponibles),
        "acciones_disponibles":  Bitacora.Accion.choices,
    }
    return render(request, "auditoria/index.html", context)


# ─── Vista de detalle ─────────────────────────────────────────────────────────

@login_required
@require_perm("auditoria.read")
def detalle(request, pk):
    """Detalle completo de un registro: campos, delta JSON, IP, módulo (CP-06)."""
    registro = get_object_or_404(Bitacora, pk=pk)

    # Formateo del delta para el visor de diferencias
    ant_fmt = (
        json.dumps(registro.valores_anteriores, indent=2, ensure_ascii=False)
        if registro.valores_anteriores else None
    )
    nue_fmt = (
        json.dumps(registro.valores_nuevos, indent=2, ensure_ascii=False)
        if registro.valores_nuevos else None
    )

    # Rol del usuario (primer rol asignado, si existe)
    rol_usuario = "—"
    if registro.user:
        from authz.models import UserRole
        ur = UserRole.objects.filter(user=registro.user).select_related("role").first()
        if ur:
            rol_usuario = ur.role.name

    context = {
        "registro":   registro,
        "ant_fmt":    ant_fmt,
        "nue_fmt":    nue_fmt,
        "rol_usuario": rol_usuario,
    }
    return render(request, "auditoria/detalle.html", context)


# ─── Exportación CSV ─────────────────────────────────────────────────────────

@login_required
@require_perm("auditoria.read")
def exportar_csv(request):
    """
    Descarga CSV con todos los registros filtrados (sin paginación).
    Registra la exportación en la propia bitácora (CP-07 / paso 10).
    """
    qs = Bitacora.objects.select_related("user").order_by("-fecha")
    qs, filtros, error_rango = _aplicar_filtros(request, qs)

    if error_rango:
        return HttpResponse("Rango de fechas inválido.", status=400)

    nombre_archivo = f"auditoria_{date.today().isoformat()}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'

    writer = csv.writer(response)
    writer.writerow([
        "Fecha/Hora", "Usuario", "Acción", "Entidad",
        "ID Entidad", "Módulo", "Resumen", "IP Origen",
    ])
    for r in qs:
        writer.writerow([
            r.fecha.strftime("%Y-%m-%d %H:%M:%S"),
            r.usuario_nombre,
            r.accion,
            r.entidad,
            r.entidad_id,
            r.modulo_origen,
            r.resumen,
            r.ip_origen or "",
        ])

    # Registrar la exportación como evento de auditoría (paso 10 del flujo normal)
    try:
        registrar_bitacora(
            accion=Bitacora.Accion.ACCEDER,
            entidad="Bitacora",
            entidad_id="",
            modulo_origen="CU-10",
            resumen=f"Exportación CSV de bitácora ({qs.count()} registros) — filtros: {filtros}",
            request=request,
        )
    except Exception:
        pass

    return response
