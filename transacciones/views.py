# transacciones/views.py
"""Vistas del módulo de Transacciones Comerciales (CU-006).
Compras, Ventas y Sacrificios con impacto atómico en el inventario de animales.
"""
import logging
from datetime import datetime, date as _date

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from animals.models import Animal
from authz.decorators import require_perm
from authz.models import AuditLog
from authz.utils import has_perm_code

from .forms import AnulacionTransaccionForm, AnimalInlineForm, TransaccionForm
from .models import Transaccion

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registrar_auditoria(request, accion: str, transaccion: Transaccion, detalle: dict | None = None):
    metadata = {
        "entidad":    "Transaccion",
        "entidad_id": transaccion.pk,
        "accion":     accion,
    }
    if detalle:
        metadata["detalle"] = detalle
    AuditLog.objects.create(
        user=request.user,
        action=f"transaccion.{accion.lower()}",
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        metadata=metadata,
    )


def _parse_date_filter(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except (ValueError, TypeError):
        return ""


def _parse_animal_pk(value: str):
    try:
        pk = int(value)
        return pk if pk > 0 else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Vista 1: Listado
# ---------------------------------------------------------------------------

@login_required
@require_perm("transacciones.read")
def transaccion_list(request):
    """Listado de transacciones con filtros y paginación (10 por página)."""
    qs = Transaccion.objects.select_related("animal", "created_by", "anulado_por")

    q            = request.GET.get("q", "").strip()
    tipo_filtro  = request.GET.get("tipo", "").strip()
    estado_filtro = request.GET.get("estado", "").strip()
    desde_raw    = request.GET.get("desde", "").strip()
    hasta_raw    = request.GET.get("hasta", "").strip()
    animal_pk_raw = request.GET.get("animal", "").strip()

    desde = _parse_date_filter(desde_raw) if desde_raw else ""
    hasta = _parse_date_filter(hasta_raw) if hasta_raw else ""

    animal_filter = None
    if animal_pk_raw:
        animal_pk = _parse_animal_pk(animal_pk_raw)
        if animal_pk:
            try:
                animal_filter = Animal.objects.get(pk=animal_pk)
            except Animal.DoesNotExist:
                animal_filter = None

    if q:
        qs = qs.filter(Q(origen_destino__icontains=q) | Q(observaciones__icontains=q)
                       | Q(animal__rfid__icontains=q) | Q(animal__nombre__icontains=q))
    if tipo_filtro:
        qs = qs.filter(tipo=tipo_filtro)
    if estado_filtro:
        qs = qs.filter(estado=estado_filtro)
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)
    if animal_filter:
        qs = qs.filter(animal=animal_filter)

    total_compras     = qs.filter(tipo=Transaccion.Tipo.COMPRA).count()
    total_ventas      = qs.filter(tipo=Transaccion.Tipo.VENTA).count()
    total_sacrificios = qs.filter(tipo=Transaccion.Tipo.SACRIFICIO).count()

    paginator = Paginator(qs, 10)
    page_obj  = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj":         page_obj,
        "total":            paginator.count,
        "q":                q,
        "tipo_filtro":      tipo_filtro,
        "estado_filtro":    estado_filtro,
        "desde":            desde_raw,
        "hasta":            hasta_raw,
        "animal_filter":    animal_filter,
        "animal_pk_raw":    animal_pk_raw,
        "total_compras":    total_compras,
        "total_ventas":     total_ventas,
        "total_sacrificios": total_sacrificios,
        "puede_escribir":   has_perm_code(request.user, "transacciones.write"),
        "puede_anular":     has_perm_code(request.user, "transacciones.anular"),
        "tipo_choices":     Transaccion.Tipo.choices,
        "estado_choices":   Transaccion.Estado.choices,
        "animales":         Animal.objects.order_by("rfid", "nombre"),
        "today":            str(_date.today()),
    }
    return render(request, "transacciones/list.html", ctx)


# ---------------------------------------------------------------------------
# Vista 2: Detalle
# ---------------------------------------------------------------------------

@login_required
@require_perm("transacciones.read")
def transaccion_detail(request, pk: int):
    """Detalle completo de una transacción."""
    transaccion = get_object_or_404(
        Transaccion.objects.select_related(
            "animal", "animal__potrero", "created_by", "anulado_por"
        ),
        pk=pk,
    )
    ctx = {
        "transaccion":   transaccion,
        "puede_anular":  has_perm_code(request.user, "transacciones.anular"),
    }
    return render(request, "transacciones/detail.html", ctx)


# ---------------------------------------------------------------------------
# Vista 3: Crear (AJAX)
# ---------------------------------------------------------------------------

@login_required
@require_perm("transacciones.write")
def transaccion_create(request):
    """Crear una nueva transacción.

    GET  → devuelve JSON con HTML del formulario para modal AJAX.
           ?animal=<pk> prellenar el campo animal (ruta B desde ficha).
    POST → procesa el formulario; devuelve JSON {success, transaccion_id} o {success, errors}.
           Usa transaction.atomic() para atomicidad (RN-5).
    """
    if request.method == "GET":
        animal_prellenado = None
        animal_pk = _parse_animal_pk(request.GET.get("animal", "").strip())
        if animal_pk:
            try:
                animal_prellenado = Animal.objects.get(pk=animal_pk)
            except Animal.DoesNotExist:
                pass

        initial = {"animal": animal_prellenado} if animal_prellenado else {}
        form       = TransaccionForm(initial=initial)
        animal_form = AnimalInlineForm()
        html = render_to_string(
            "transacciones/_form.html",
            {
                "form":             form,
                "animal_form":      animal_form,
                "animal_prellenado": animal_prellenado,
                "today":            str(_date.today()),
            },
            request=request,
        )
        return JsonResponse({"html": html})

    # POST ──────────────────────────────────────────────────────────────────
    form        = TransaccionForm(request.POST)
    animal_form = AnimalInlineForm(request.POST)

    # Validar animal_form primero para saber si se va a crear un animal inline.
    # Esto permite relajar el campo 'animal' del formulario principal antes de
    # validarlo, evitando el error "Este campo es obligatorio" cuando el usuario
    # marcó "Crear nuevo animal en esta compra" (CU-006).
    animal_form_valid = animal_form.is_valid()
    crear_animal = animal_form.cleaned_data.get("crear_animal", False) if animal_form_valid else False

    if crear_animal:
        form.fields["animal"].required = False

    form_valid = form.is_valid()

    if not form_valid:
        return JsonResponse({"success": False, "errors": form.errors}, status=400)

    # Si quieren crear animal inline, validar que el sub-formulario sea válido
    if crear_animal and not animal_form_valid:
        return JsonResponse({"success": False, "errors": animal_form.errors}, status=400)

    try:
        with transaction.atomic():
            # CU-006: si COMPRA + crear_animal, crear el animal primero
            if crear_animal and form.cleaned_data.get("tipo") == "COM":
                ad = animal_form.cleaned_data
                new_animal = Animal(
                    rfid          = ad.get("ani_rfid",   "") or None,
                    nombre        = ad.get("ani_nombre", "") or None,
                    sexo          = ad.get("ani_sexo",  "") or None,
                    etapa         = ad.get("ani_etapa", "") or None,
                    raza          = ad.get("ani_raza",  "") or None,
                    procedencia   = ad.get("ani_procedencia", "") or None,
                    peso_entrada  = ad.get("ani_peso_entrada") or None,
                    estado        = Animal.Estado.BORRADOR,
                    last_modified_by = request.user,
                )
                new_animal.save()
                # Sobreescribir el animal en el formulario de transacción
                form.instance.animal = new_animal
            else:
                new_animal = None

            transaccion = form.save(commit=False)
            transaccion.created_by = request.user
            if new_animal:
                transaccion.animal = new_animal
            transaccion.full_clean()
            transaccion.save()
            transaccion.aplicar_impacto_inventario()
            _registrar_auditoria(request, "CREACION", transaccion, {
                "tipo":           transaccion.tipo,
                "animal_id":      transaccion.animal_id,
                "valor_cop":      str(transaccion.valor_cop),
                "origen_destino": transaccion.origen_destino,
                "animal_creado":  bool(new_animal),
            })
        return JsonResponse({"success": True, "transaccion_id": transaccion.pk})

    except Exception as exc:
        logger.exception("Error al crear transacción: %s", exc)
        return JsonResponse({"success": False, "errors": {"__all__": [str(exc)]}}, status=400)


# ---------------------------------------------------------------------------
# Vista 4: Anular
# ---------------------------------------------------------------------------

@login_required
@require_perm("transacciones.anular")
def transaccion_anular(request, pk: int):
    """Anular una transacción CONFIRMADA.

    GET  → redirige al detalle.
    POST → procesa la anulación; devuelve JSON {success} o {success, error}.
           Revierte el impacto en el animal dentro de transaction.atomic().
    """
    if request.method != "POST":
        return redirect("transacciones:detail", pk=pk)

    transaccion = get_object_or_404(
        Transaccion.objects.select_related("animal"),
        pk=pk,
    )

    if not transaccion.es_anulable:
        return JsonResponse({"success": False, "error": "La transacción ya está anulada."}, status=400)

    form = AnulacionTransaccionForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors}, status=400)

    motivo = form.cleaned_data["motivo"]
    estado_previo_animal = transaccion.animal.estado

    # Determinar el estado al que vuelve el animal (inverso de aplicar_impacto_inventario)
    if transaccion.tipo == Transaccion.Tipo.COMPRA:
        estado_revertido = Animal.Estado.BORRADOR
    else:
        estado_revertido = Animal.Estado.ACTIVO

    try:
        with transaction.atomic():
            transaccion.estado           = Transaccion.Estado.ANULADO
            transaccion.motivo_anulacion = motivo
            transaccion.anulado_por      = request.user
            transaccion.fecha_anulacion  = timezone.now()
            transaccion.save()
            transaccion.revertir_impacto_inventario(estado_revertido)
            _registrar_auditoria(request, "ANULACION", transaccion, {
                "motivo":               motivo,
                "estado_previo_animal": estado_previo_animal,
                "estado_revertido":     estado_revertido,
            })
        return JsonResponse({"success": True})

    except Exception as exc:
        logger.exception("Error al anular transacción %s: %s", pk, exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


# ---------------------------------------------------------------------------
# Vista 5: Historial por animal
# ---------------------------------------------------------------------------

@login_required
@require_perm("transacciones.read")
def transaccion_historial_animal(request, animal_pk: int):
    """Historial completo de transacciones de un animal específico."""
    animal = get_object_or_404(Animal, pk=animal_pk)

    qs = (
        Transaccion.objects
        .filter(animal=animal)
        .select_related("created_by", "anulado_por")
        .order_by("-fecha", "-created_at")
    )

    confirmadas = qs.filter(estado=Transaccion.Estado.CONFIRMADO)

    ctx = {
        "animal":                  animal,
        "transacciones":           qs,
        "total_compras":           qs.filter(tipo=Transaccion.Tipo.COMPRA).count(),
        "total_ventas":            qs.filter(tipo=Transaccion.Tipo.VENTA).count(),
        "total_sacrificios":       qs.filter(tipo=Transaccion.Tipo.SACRIFICIO).count(),
        "total_anuladas":          qs.filter(estado=Transaccion.Estado.ANULADO).count(),
        "valor_total_confirmadas": confirmadas.aggregate(t=Sum("valor_cop"))["t"] or 0,
        "primera_transaccion":     qs.last(),
        "ultima_transaccion":      qs.first(),
        "puede_anular":            has_perm_code(request.user, "transacciones.anular"),
        "puede_escribir":          has_perm_code(request.user, "transacciones.write"),
        "today":                   str(_date.today()),
    }
    return render(request, "transacciones/historial_animal.html", ctx)
