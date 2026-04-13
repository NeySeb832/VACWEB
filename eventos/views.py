# eventos/views.py
"""Vistas del módulo de Eventos Sanitarios (CU-003).
Registro, detalle, corrección y anulación de vacunas/tratamientos.
"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404

from animals.models import Animal
from authz.decorators import require_perm
from .models import EventoSanitario
from .forms import EventoSanitarioForm, CorreccionEventoForm


@login_required
@require_perm("eventos.read")
def evento_list(request):
    """Lista de eventos sanitarios con filtros opcionales.

    Filtros GET: ?q=<tipo|responsable>, ?animal=<id>, ?estado=<CON|ANU>
    Paginación: 25 por página.
    Contexto: page_obj, total, q, animal_filter, estado, animales
    """
    qs = EventoSanitario.objects.select_related("animal", "evento_original")

    q = request.GET.get("q", "").strip()
    animal_filter = request.GET.get("animal", "").strip()
    estado = request.GET.get("estado", "").strip()

    if q:
        qs = qs.filter(Q(tipo__icontains=q) | Q(responsable__icontains=q))
    if animal_filter:
        qs = qs.filter(animal_id=animal_filter)
    if estado:
        qs = qs.filter(estado=estado)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "q": q,
        "animal_filter": animal_filter,
        "estado": estado,
        "animales": Animal.objects.order_by("rfid", "arete"),
        "estado_choices": EventoSanitario.Estado.choices,
    }
    return render(request, "eventos/evento_list.html", ctx)


@login_required
@require_perm("eventos.write")
def evento_create(request):
    """Registrar un nuevo evento sanitario.

    Si ?animal=<id> en GET, precarga el campo animal y lo deshabilita.
    POST crea el evento con estado CONFIRMADO y created_by=request.user.
    """
    animal_id = request.GET.get("animal", "").strip()
    animal_obj = None
    if animal_id:
        animal_obj = get_object_or_404(Animal, pk=animal_id)

    if request.method == "POST":
        form = EventoSanitarioForm(request.POST)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.estado = EventoSanitario.Estado.CONFIRMADO
            evento.created_by = request.user
            evento.full_clean()
            evento.save()
            return redirect("eventos:detail", pk=evento.pk)
    else:
        initial = {"animal": animal_obj} if animal_obj else {}
        form = EventoSanitarioForm(initial=initial)

    ctx = {
        "form": form,
        "animal_obj": animal_obj,
    }
    return render(request, "eventos/evento_form.html", ctx)


@login_required
@require_perm("eventos.read")
def evento_detail(request, pk: int):
    """Detalle completo de un evento y lista de correcciones vinculadas."""
    evento = get_object_or_404(
        EventoSanitario.objects.select_related("animal", "animal__potrero", "evento_original", "created_by"),
        pk=pk,
    )
    correcciones = evento.correcciones.select_related("created_by").order_by("-created_at")

    ctx = {
        "evento": evento,
        "correcciones": correcciones,
    }
    return render(request, "eventos/evento_detail.html", ctx)


@login_required
@require_perm("eventos.write")
def evento_correccion(request, pk: int):
    """Registrar una corrección sobre un evento CONFIRMADO.

    GET  → muestra el formulario precargado con los datos del original.
    POST → crea un nuevo EventoSanitario con:
             - estado = CONFIRMADO
             - evento_original = evento original (pk)
             - animal = heredado del original
             - created_by = request.user
           El evento original NO se modifica.
    """
    evento_original = get_object_or_404(
        EventoSanitario.objects.select_related("animal"),
        pk=pk,
        estado=EventoSanitario.Estado.CONFIRMADO,
    )

    if request.method == "POST":
        form = CorreccionEventoForm(request.POST)
        if form.is_valid():
            correccion = form.save(commit=False)
            correccion.animal = evento_original.animal
            correccion.estado = EventoSanitario.Estado.CONFIRMADO
            correccion.evento_original = evento_original
            correccion.created_by = request.user
            correccion.full_clean()
            correccion.save()
            return redirect("eventos:detail", pk=correccion.pk)
    else:
        form = CorreccionEventoForm(initial={
            "tipo": evento_original.tipo,
            "fecha": evento_original.fecha,
            "responsable": evento_original.responsable,
            "producto": evento_original.producto,
            "dosis": evento_original.dosis,
            "lote": evento_original.lote,
            "via_aplicacion": evento_original.via_aplicacion,
            "notas": evento_original.notas,
        })

    ctx = {
        "form": form,
        "evento": evento_original,
    }
    return render(request, "eventos/evento_correccion.html", ctx)


@login_required
@require_perm("eventos.write")
def evento_anular(request, pk: int):
    """Anular un evento existente.

    Solo acepta POST. Cambia el estado a ANULADO.
    Requiere campo 'motivo' en POST: se antepone a las notas existentes.
    """
    if request.method != "POST":
        return redirect("eventos:detail", pk=pk)

    evento = get_object_or_404(EventoSanitario, pk=pk)
    motivo = request.POST.get("motivo", "").strip()

    if motivo:
        if evento.notas:
            evento.notas = f"[Motivo de anulación: {motivo}]\n\n{evento.notas}"
        else:
            evento.notas = f"[Motivo de anulación: {motivo}]"

    evento.estado = EventoSanitario.Estado.ANULADO
    # save() directo con update_fields: la anulación es una acción administrativa;
    # la RN-3 del clean() solo aplica a instancias nuevas (not self.pk).
    evento.save(update_fields=["estado", "notas"])

    return redirect("eventos:detail", pk=pk)
