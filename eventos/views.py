# eventos/views.py
"""Vistas del módulo de Eventos Sanitarios (CU-003).
Registro, detalle, corrección, cancelación y realización de vacunas/tratamientos.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404

from animals.models import Animal
from authz.decorators import require_perm
from potreros.models import Potrero
from .models import EventoSanitario
from .forms import EventoSanitarioForm, CorreccionEventoForm, EventoMasivoForm


@login_required
@require_perm("eventos.read")
def evento_list(request):
    """Lista de eventos sanitarios con filtros opcionales.

    Filtros GET: ?q=<tipo|responsable>, ?animal=<id>, ?estado=<CON|APL|CAN|REA>
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
        "animales": Animal.objects.order_by("rfid", "nombre"),
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
        "puede_modificarse": evento.puede_modificarse,
    }
    return render(request, "eventos/evento_detail.html", ctx)


@login_required
@require_perm("eventos.write")
def evento_correccion(request, pk: int):
    """Registrar una corrección sobre un evento CONFIRMADO o APLAZADO.

    GET  → muestra el formulario precargado con los datos del original.
    POST → crea un nuevo EventoSanitario con:
             - estado = CONFIRMADO
             - evento_original = evento original (pk)
             - animal = heredado del original
             - created_by = request.user
           El evento original NO se modifica.
    Solo acepta eventos en estados mutables (CONFIRMADO o APLAZADO).
    """
    evento_original = get_object_or_404(
        EventoSanitario.objects.select_related("animal"),
        pk=pk,
        estado__in=list(EventoSanitario.ESTADOS_MUTABLES),
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
def evento_cancelar(request, pk: int):
    """Cancelar un evento CONFIRMADO o APLAZADO.

    Solo acepta POST. Cambia el estado a CANCELADO.
    Requiere campo 'motivo' en POST: se antepone a las notas existentes.
    """
    if request.method != "POST":
        return redirect("eventos:detail", pk=pk)

    evento = get_object_or_404(
        EventoSanitario,
        pk=pk,
        estado__in=list(EventoSanitario.ESTADOS_MUTABLES),
    )
    motivo = request.POST.get("motivo", "").strip()

    if motivo:
        prefijo = f"[Motivo de cancelación: {motivo}]"
        evento.notas = f"{prefijo}\n\n{evento.notas}" if evento.notas else prefijo

    evento.estado = EventoSanitario.Estado.CANCELADO
    evento.save(update_fields=["estado", "notas"])

    return redirect("eventos:detail", pk=pk)


@login_required
@require_perm("eventos.write")
def evento_realizar(request, pk: int):
    """Marcar un evento CONFIRMADO o APLAZADO como REALIZADO.

    Solo acepta POST. Cambia el estado a REALIZADO.
    Acepta campo opcional 'notas' en POST para agregar observaciones de cierre.
    """
    if request.method != "POST":
        return redirect("eventos:detail", pk=pk)

    evento = get_object_or_404(
        EventoSanitario,
        pk=pk,
        estado__in=list(EventoSanitario.ESTADOS_MUTABLES),
    )
    notas_cierre = request.POST.get("notas_cierre", "").strip()

    if notas_cierre:
        prefijo = f"[Notas de cierre: {notas_cierre}]"
        evento.notas = f"{evento.notas}\n\n{prefijo}" if evento.notas else prefijo

    evento.estado = EventoSanitario.Estado.REALIZADO
    evento.save(update_fields=["estado", "notas"])

    return redirect("eventos:detail", pk=pk)


@login_required
@require_perm("eventos.write")
def evento_masivo_create(request):
    """CU-003 pasos 13-14: Registro masivo de un evento sanitario para varios animales.

    GET  → muestra el formulario; ?potrero=<id> filtra la lista de animales.
    POST → valida y crea un EventoSanitario por cada animal seleccionado,
           dentro de una transacción atómica.
    """
    # Potrero de filtro (opcional)
    potrero_id  = request.GET.get("potrero", "").strip()
    potrero_obj = None
    if potrero_id:
        try:
            potrero_obj = Potrero.objects.get(pk=potrero_id, estado="ACTIVO")
        except Potrero.DoesNotExist:
            potrero_obj = None

    if request.method == "POST":
        # En POST, el potrero puede venir como campo oculto del formulario
        post_potrero_id = request.POST.get("potrero_id", "").strip()
        if post_potrero_id and not potrero_obj:
            try:
                potrero_obj = Potrero.objects.get(pk=post_potrero_id, estado="ACTIVO")
            except Potrero.DoesNotExist:
                pass

        form = EventoMasivoForm(request.POST, potrero=potrero_obj)
        if form.is_valid():
            animales = form.cleaned_data["animales"]
            datos_evento = {
                k: form.cleaned_data[k]
                for k in ["tipo", "fecha", "responsable", "producto",
                          "dosis", "lote", "via_aplicacion", "notas"]
            }
            creados = 0
            errores = []
            try:
                with transaction.atomic():
                    for animal in animales:
                        evento = EventoSanitario(
                            animal=animal,
                            estado=EventoSanitario.Estado.CONFIRMADO,
                            created_by=request.user,
                            **datos_evento,
                        )
                        evento.full_clean()
                        evento.save()
                        creados += 1
            except Exception as exc:
                errores.append(str(exc))

            if errores:
                messages.error(request, f"Error al crear eventos: {errores[0]}")
            else:
                messages.success(
                    request,
                    f"Se registraron {creados} evento{'s' if creados != 1 else ''} sanitario{'s' if creados != 1 else ''} correctamente."
                )
                return redirect("eventos:list")
    else:
        form = EventoMasivoForm(potrero=potrero_obj)

    ctx = {
        "form":       form,
        "potrero_obj": potrero_obj,
        "potreros":   Potrero.objects.filter(estado="ACTIVO").order_by("nombre_codigo"),
        "potrero_id": potrero_id,
    }
    return render(request, "eventos/evento_masivo.html", ctx)
