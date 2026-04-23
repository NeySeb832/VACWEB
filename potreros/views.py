# potreros/views.py
"""Vistas del módulo de Potreros/Lotes (CU-005).

Patrón de respuesta:
  - GET listado/detalle → HTML renderizado.
  - POST crear/editar/desactivar → JSON (para modales AJAX en el frontend).
"""

import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from authz.decorators import require_perm
from authz.models import AuditLog
from authz.utils import has_perm_code

from .forms import PotreroForm
from .models import Potrero


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registrar_auditoria(request, accion: str, potrero: Potrero, detalle: dict | None = None):
    """Registra una entrada en AuditLog para operaciones sobre Potrero."""
    metadata = {
        "entidad":    "Potrero",
        "entidad_id": potrero.pk,
        "accion":     accion,
    }
    if detalle:
        metadata["detalle"] = detalle

    AuditLog.objects.create(
        user=request.user,
        action=f"potrero.{accion.lower()}",
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        metadata=metadata,
    )


def _puede_escribir(user) -> bool:
    return has_perm_code(user, "potreros.write")


# ---------------------------------------------------------------------------
# Vista 1: Listado
# ---------------------------------------------------------------------------

@login_required
@require_perm("potreros.read")
def potreros_list(request):
    """Listado de potreros con filtros y paginación (12 por página)."""
    qs = Potrero.objects.all()

    q       = request.GET.get("q", "").strip()
    estado  = request.GET.get("estado", "").strip()
    tipo    = request.GET.get("tipo", "").strip()

    if q:
        qs = qs.filter(Q(nombre_codigo__icontains=q))
    if estado:
        qs = qs.filter(estado=estado)
    if tipo:
        qs = qs.filter(tipo_uso=tipo)

    # Enriquecer cada potrero con datos calculados
    potreros_data = []
    for p in qs:
        activos   = p.get_animales_activos_count()
        pct       = p.get_porcentaje_ocupacion()
        disponibles = max(0, p.capacidad_maxima - activos)
        potreros_data.append({
            "potrero":      p,
            "activos":      activos,
            "porcentaje":   pct,
            "disponibles":  disponibles,
        })

    paginator  = Paginator(potreros_data, 12)
    page_obj   = paginator.get_page(request.GET.get("page"))

    # Resumen global
    total_potreros  = Potrero.objects.count()
    total_activos   = sum(p.get_animales_activos_count() for p in Potrero.objects.all())
    total_capacidad = Potrero.objects.aggregate(t=Sum("capacidad_maxima"))["t"] or 0
    ocupacion_global = (
        round((total_activos / total_capacidad) * 100, 1) if total_capacidad > 0 else 0
    )

    resumen = {
        "total_potreros":  total_potreros,
        "animales_activos": total_activos,
        "capacidad_total": total_capacidad,
        "ocupacion_global": ocupacion_global,
    }

    ctx = {
        "page_obj":       page_obj,
        "total":          paginator.count,
        "q":              q,
        "estado_filtro":  estado,
        "tipo_filtro":    tipo,
        "resumen":        resumen,
        "puede_escribir": _puede_escribir(request.user),
        "tipo_choices":   Potrero.TipoUso.choices,
        "estado_choices": Potrero.Estado.choices,
        "form":           PotreroForm(),  # para el modal de creación
    }
    return render(request, "potreros/potreros_list.html", ctx)


# ---------------------------------------------------------------------------
# Vista 2: Crear
# ---------------------------------------------------------------------------

@login_required
@require_perm("potreros.write")
def potrero_create(request):
    """Crear un nuevo potrero. GET devuelve HTML del formulario (para modal).
    POST procesa la creación y devuelve JSON."""
    if request.method == "GET":
        form = PotreroForm()
        html = render_to_string(
            "potreros/_form_modal_body.html",
            {"form": form, "is_create": True},
            request=request,
        )
        return JsonResponse({"html": html})

    form = PotreroForm(request.POST)
    if form.is_valid():
        potrero = form.save(commit=False)
        potrero.estado     = Potrero.Estado.ACTIVO
        potrero.created_by = request.user
        potrero.save()
        _registrar_auditoria(request, "CREACION", potrero)
        return JsonResponse({
            "success": True,
            "message": "Potrero creado exitosamente.",
            "potrero_id": potrero.pk,
        })

    return JsonResponse({"success": False, "errors": form.errors}, status=400)


# ---------------------------------------------------------------------------
# Vista 3: Detalle
# ---------------------------------------------------------------------------

@login_required
@require_perm("potreros.read")
def potrero_detail(request, pk: int):
    """Detalle de un potrero con lista de animales activos asignados."""
    potrero = get_object_or_404(Potrero, pk=pk)

    animales_activos = potrero.animales.filter(estado="ACT").select_related()
    activos_count    = animales_activos.count()
    porcentaje       = potrero.get_porcentaje_ocupacion()
    disponibles      = max(0, potrero.capacidad_maxima - activos_count)

    ctx = {
        "potrero":        potrero,
        "animales":       animales_activos,
        "activos_count":  activos_count,
        "porcentaje":     porcentaje,
        "disponibles":    disponibles,
        "puede_escribir": _puede_escribir(request.user),
    }
    return render(request, "potreros/potrero_detail.html", ctx)


# ---------------------------------------------------------------------------
# Vista 4: Editar
# ---------------------------------------------------------------------------

@login_required
@require_perm("potreros.write")
def potrero_edit(request, pk: int):
    """Editar un potrero existente. GET devuelve HTML del formulario (para modal).
    POST procesa la edición y devuelve JSON."""
    potrero = get_object_or_404(Potrero, pk=pk)

    if request.method == "GET":
        form = PotreroForm(instance=potrero)
        html = render_to_string(
            "potreros/_form_modal_body.html",
            {"form": form, "is_create": False, "potrero": potrero},
            request=request,
        )
        return JsonResponse({"html": html})

    form = PotreroForm(request.POST, instance=potrero)
    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors}, status=400)

    # Calcular delta de campos modificados para auditoría
    delta = {}
    for field in form.changed_data:
        delta[field] = {
            "anterior": str(getattr(potrero, field, "")),
            "nuevo":    str(form.cleaned_data.get(field, "")),
        }

    potrero_actualizado = form.save()

    # RN: advertir si la nueva capacidad es menor al número de animales activos
    activos_count = potrero_actualizado.get_animales_activos_count()
    warning = None
    if potrero_actualizado.capacidad_maxima < activos_count:
        warning = (
            f"La nueva capacidad ({potrero_actualizado.capacidad_maxima}) es menor al número "
            f"de animales actualmente asignados ({activos_count})."
        )

    _registrar_auditoria(request, "EDICION", potrero_actualizado, detalle=delta)

    response = {
        "success":    True,
        "message":    "Potrero actualizado exitosamente.",
        "potrero_id": potrero_actualizado.pk,
    }
    if warning:
        response["warning"] = warning
    return JsonResponse(response)


# ---------------------------------------------------------------------------
# Vista 5: Desactivar (baja lógica)
# ---------------------------------------------------------------------------

@login_required
@require_perm("potreros.write")
@require_POST
def potrero_deactivate(request, pk: int):
    """Desactiva un potrero (baja lógica). Solo acepta POST. Devuelve JSON.

    RN-2: No se puede desactivar si el potrero tiene animales activos asignados.
    """
    potrero = get_object_or_404(Potrero, pk=pk)

    animales_activos = list(
        potrero.animales.filter(estado="ACT").values("rfid", "nombre")[:50]
    )

    if animales_activos:
        return JsonResponse({
            "success": False,
            "blocked": True,
            "message": (
                f"No es posible desactivar este potrero — tiene "
                f"{len(animales_activos)} animales activos asignados."
            ),
            "animales": [
                {"rfid": a["rfid"] or "—", "nombre_alias": a["nombre"] or "—"}
                for a in animales_activos
            ],
        }, status=409)

    potrero.estado = Potrero.Estado.INACTIVO
    potrero.save(update_fields=["estado", "updated_at"])
    _registrar_auditoria(request, "DESACTIVACION", potrero)

    return JsonResponse({
        "success": True,
        "message": "Potrero desactivado exitosamente.",
    })
