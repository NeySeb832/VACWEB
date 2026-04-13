# pesajes/views.py
import logging
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404

from animals.models import Animal
from authz.decorators import require_perm
from .models import Pesaje
from .forms import PesajeForm

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades de validación de parámetros GET
# ─────────────────────────────────────────────────────────────────────────────

def _parse_animal_id(value: str):
    """Convierte el valor de ?animal= a entero positivo.
    Devuelve el entero si es válido, None en caso contrario.
    """
    try:
        pk = int(value)
        return pk if pk > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_date_filter(value: str) -> str:
    """Valida que el valor tenga formato YYYY-MM-DD.
    Devuelve el string original si es válido, cadena vacía si no.
    """
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except (ValueError, TypeError):
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Vistas
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_perm("pesajes.read")
def pesaje_list(request):
    """Lista de pesajes con filtros: ?q, ?animal, ?fecha_desde, ?fecha_hasta."""
    qs = Pesaje.objects.select_related("animal", "created_by")

    q = request.GET.get("q", "").strip()
    animal_filter_raw = request.GET.get("animal", "").strip()
    fecha_desde_raw = request.GET.get("fecha_desde", "").strip()
    fecha_hasta_raw = request.GET.get("fecha_hasta", "").strip()

    # Validar y sanear parámetros de filtro
    animal_filter_pk = _parse_animal_id(animal_filter_raw) if animal_filter_raw else None
    fecha_desde = _parse_date_filter(fecha_desde_raw) if fecha_desde_raw else ""
    fecha_hasta = _parse_date_filter(fecha_hasta_raw) if fecha_hasta_raw else ""

    if animal_filter_raw and animal_filter_pk is None:
        messages.warning(request, "El filtro de animal no es válido y fue ignorado.")

    if fecha_desde_raw and not fecha_desde:
        messages.warning(request, "El formato de 'Fecha desde' no es válido (usa YYYY-MM-DD).")

    if fecha_hasta_raw and not fecha_hasta:
        messages.warning(request, "El formato de 'Fecha hasta' no es válido (usa YYYY-MM-DD).")

    if q:
        qs = qs.filter(Q(responsable__icontains=q) | Q(observaciones__icontains=q))
    if animal_filter_pk:
        qs = qs.filter(animal_id=animal_filter_pk)
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)

    try:
        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(request.GET.get("page"))
        total = paginator.count
    except (DatabaseError, Exception) as exc:
        logger.exception("Error al listar pesajes: %s", exc)
        messages.error(request, "Ocurrió un error al cargar los pesajes. Intenta limpiar los filtros.")
        paginator = Paginator(Pesaje.objects.none(), 25)
        page_obj = paginator.get_page(1)
        total = 0

    return render(request, "pesajes/pesaje_list.html", {
        "page_obj": page_obj,
        "total": total,
        "q": q,
        "animal_filter": animal_filter_raw,
        "fecha_desde": fecha_desde_raw if fecha_desde else "",
        "fecha_hasta": fecha_hasta_raw if fecha_hasta else "",
        "animales": Animal.objects.order_by("rfid", "arete"),
    })


@login_required
@require_perm("pesajes.write")
def pesaje_create(request):
    """Registrar un nuevo pesaje.
    Si ?animal=<id> en GET, precarga el animal y lo bloquea.
    Calcula variación automáticamente al guardar (RN-6).
    """
    # Resolver animal desde GET de forma segura
    animal_id_raw = request.GET.get("animal", "").strip()
    animal_obj = None
    if animal_id_raw:
        animal_pk = _parse_animal_id(animal_id_raw)
        if animal_pk is None:
            # Parámetro no numérico: ignorar sin crash
            logger.warning("pesaje_create: ?animal= recibió valor no entero '%s'", animal_id_raw)
        else:
            animal_obj = get_object_or_404(Animal, pk=animal_pk, estado=Animal.Estado.ACTIVO)

    if request.method == "POST":
        form = PesajeForm(request.POST, request.FILES)
        if form.is_valid():
            pesaje = form.save(commit=False)
            pesaje.created_by = request.user
            try:
                pesaje.full_clean()
                pesaje.save()
                messages.success(request, "Pesaje registrado correctamente.")
                return redirect("pesajes:detail", pk=pesaje.pk)
            except ValidationError as exc:
                # Errores de reglas de negocio del modelo (RN-1, RN-2, fecha futura)
                for field, errs in exc.message_dict.items():
                    target_field = field if field in form.fields else None
                    for err in errs:
                        form.add_error(target_field, err)
            except ValueError as exc:
                # RN-3: intento de modificar un pesaje ya guardado (no debería ocurrir aquí)
                logger.error("Violación RN-3 en pesaje_create: %s", exc)
                form.add_error(None, str(exc))
            except DatabaseError as exc:
                logger.exception("Error de base de datos al guardar pesaje: %s", exc)
                form.add_error(None, "Error al guardar en la base de datos. Por favor intenta de nuevo.")
            except Exception as exc:
                logger.exception("Error inesperado al guardar pesaje: %s", exc)
                form.add_error(None, "Error inesperado. Por favor intenta de nuevo.")
    else:
        initial = {"animal": animal_obj} if animal_obj else {}
        form = PesajeForm(initial=initial)

    # Último pesaje del animal para referencia visual
    ultimo_pesaje = None
    if animal_obj:
        try:
            ultimo_pesaje = Pesaje.objects.filter(animal=animal_obj).first()
        except DatabaseError as exc:
            logger.exception("Error al consultar último pesaje del animal %s: %s", animal_obj.pk, exc)

    return render(request, "pesajes/pesaje_form.html", {
        "form": form,
        "animal_obj": animal_obj,
        "ultimo_pesaje": ultimo_pesaje,
    })


@login_required
@require_perm("pesajes.read")
def pesaje_detail(request, pk: int):
    """Detalle de un pesaje: datos completos + variación + animal."""
    pesaje = get_object_or_404(
        Pesaje.objects.select_related("animal", "animal__potrero", "created_by"),
        pk=pk,
    )
    try:
        anterior = (
            Pesaje.objects.filter(
                animal=pesaje.animal,
                fecha__lte=pesaje.fecha,
            )
            .exclude(pk=pesaje.pk)
            .order_by("-fecha", "-created_at")
            .first()
        )
    except DatabaseError as exc:
        logger.exception("Error al consultar pesaje anterior para pesaje %s: %s", pk, exc)
        anterior = None

    return render(request, "pesajes/pesaje_detail.html", {
        "pesaje": pesaje,
        "anterior": anterior,
    })
