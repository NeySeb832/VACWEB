# animals/views.py
"""Vistas del módulo de Animales (CU-002).
CRUD básico de animales: lista, detalle, creación, edición y baja lógica.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.shortcuts import render, redirect, get_object_or_404

from authz.decorators import require_perm
from .models import Animal, Potrero, Movimiento
from .forms import AnimalForm
from eventos.models import EventoSanitario


@login_required
@require_perm("animals.read")
def animal_list(request):
    """CU-002: Lista de animales.

    Pre:
        - Usuario autenticado.
        - Permiso "animals.read".

    Comportamiento:
        - Busca por RFID / arete / raza (?q=).
        - Filtra por estado (?estado=) y potrero (?lote=).
        - Pagina los resultados (25 por página).
    """
    qs = (
        Animal.objects.select_related("potrero")
        .all()
        .order_by("-created_at")
    )

    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()
    lote = request.GET.get("lote", "").strip()

    if q:
        qs = qs.filter(
            Q(rfid__icontains=q)
            | Q(arete__icontains=q)
            | Q(raza__icontains=q)
        )

    if estado:
        qs = qs.filter(estado=estado)

    if lote:
        qs = qs.filter(potrero_id=lote)

    # Columna derivada: nº de eventos sanitarios del animal
    qs = qs.annotate(
        num_alertas=Count("eventos"),
    )

    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "q": q,
        "estado": estado,
        "lote": lote,
        "estados_choices": Animal.Estado.choices,
        "lotes": Potrero.objects.filter(activo=True).order_by("nombre"),
    }
    return render(request, "animals/animal_list.html", ctx)


@login_required
@require_perm("animals.write")  # 🔐 Ajusta el código si usas otro permiso de escritura
def animal_create(request):
    """Crear un nuevo animal."""
    if request.method == "POST":
        form = AnimalForm(request.POST, request.FILES)
        if form.is_valid():
            animal = form.save(commit=False)
            animal.last_modified_by = request.user
            animal.save()
            messages.success(request, "Animal creado correctamente.")
            return redirect("animals:detail", pk=animal.pk)
    else:
        form = AnimalForm()

    return render(request, "animals/animal_form.html", {"form": form, "is_create": True})


@login_required
@require_perm("animals.read")
def animal_detail(request, pk: int):
    """Detalle de un animal.

    Por ahora:
      - Datos básicos del animal.
      - Listas en solo lectura de movimientos, eventos y pesajes.
    """
    animal = get_object_or_404(
        Animal.objects.select_related("potrero"),
        pk=pk,
    )

    movimientos = animal.movimientos.select_related("desde", "hacia").order_by("-fecha")[:10]
    eventos = animal.eventos.order_by("-fecha")[:10]

    ctx = {
        "animal": animal,
        "movimientos": movimientos,
        "eventos": eventos,
    }
    return render(request, "animals/animal_detail.html", ctx)


@login_required
@require_perm("animals.write")  # 🔐 idem create
def animal_update(request, pk: int):
    """Editar datos básicos de un animal."""
    animal = get_object_or_404(Animal, pk=pk)

    if request.method == "POST":
        form = AnimalForm(request.POST, request.FILES, instance=animal)
        if form.is_valid():
            animal = form.save(commit=False)
            animal.last_modified_by = request.user
            animal.save()
            messages.success(request, "Cambios guardados correctamente.")
            return redirect("animals:detail", pk=animal.pk)
    else:
        form = AnimalForm(instance=animal)

    ctx = {
        "form": form,
        "is_create": False,
        "animal": animal,
    }
    return render(request, "animals/animal_form.html", ctx)


@login_required
@require_perm("animals.write")  # Luego esto se integrará con Movimientos (venta/salida)
def animal_baja(request, pk: int):
    """Marcar un animal como INACTIVO (baja lógica).

    Nota de dominio:
      En el modelo definitivo la baja por venta será un Movimiento especial.
      De momento sólo cambiamos el estado a INACTIVO y guardamos el motivo.
    """
    animal = get_object_or_404(Animal, pk=pk)

    if request.method == "POST":
        motivo = request.POST.get("motivo_baja", "").strip()
        animal.estado = Animal.Estado.INACTIVO
        if motivo:
            animal.motivo_baja = motivo
        animal.last_modified_by = request.user
        animal.save()
        messages.success(request, "El animal fue marcado como inactivo (baja lógica).")
        return redirect("animals:detail", pk=animal.pk)

    ctx = {
        "animal": animal,
    }
    return render(request, "animals/animal_baja_confirm.html", ctx)
