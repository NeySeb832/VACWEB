# animals/views.py
"""Vistas del módulo de Animales (CU-002).
CRUD básico de animales: lista, detalle, creación, edición y baja lógica.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from authz.decorators import require_perm
from authz.utils import has_perm_code
from .models import Animal, Potrero, Movimiento
from .forms import AnimalForm
from pesajes.models import Pesaje
from potreros.models import Potrero as PotreroModel


@login_required
@require_perm("animals.read")
def animal_list(request):
    """CU-002: Lista de animales.

    Pre:
        - Usuario autenticado.
        - Permiso "animals.read".

    Comportamiento:
        - Busca por RFID / nombre / raza (?q=).
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
            | Q(nombre__icontains=q)
            | Q(raza__icontains=q)
        )

    if estado:
        qs = qs.filter(estado=estado)

    if lote:
        qs = qs.filter(potrero_id=lote)

    # Columna derivada: nº de eventos CONFIRMADOS pendientes (alertas reales)
    qs = qs.annotate(
        num_alertas=Count("eventos", filter=Q(eventos__estado="CON")),
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
        "lotes": Potrero.objects.filter(estado="ACTIVO").order_by("nombre_codigo"),
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
    eventos_alertas = animal.eventos.filter(estado="CON")

    pesajes_qs = list(Pesaje.objects.filter(animal=animal).order_by("fecha"))
    num_pesajes = len(pesajes_qs)
    pesaje_inicial = pesajes_qs[0] if num_pesajes else None
    pesaje_actual = pesajes_qs[-1] if num_pesajes else None
    pesajes = list(reversed(pesajes_qs))[:10]

    # CU-006: Últimas transacciones del animal (importación local para evitar circular import)
    from transacciones.models import Transaccion
    ultimas_transacciones = (
        Transaccion.objects
        .filter(animal=animal)
        .select_related("created_by")
        .order_by("-fecha", "-created_at")[:5]
    )
    puede_leer_transacciones   = has_perm_code(request.user, "transacciones.read")
    puede_escribir_transacciones = has_perm_code(request.user, "transacciones.write")

    puede_editar = has_perm_code(request.user, "animals.write")

    ctx = {
        "animal": animal,
        "movimientos": movimientos,
        "eventos": eventos,
        "eventos_alertas": eventos_alertas,
        "pesajes": pesajes,
        "pesaje_inicial": pesaje_inicial,
        "pesaje_actual": pesaje_actual,
        "num_pesajes": num_pesajes,
        "potreros_activos": PotreroModel.objects.filter(estado="ACTIVO").order_by("nombre_codigo"),
        "ultimas_transacciones":      ultimas_transacciones,
        "puede_leer_transacciones":   puede_leer_transacciones,
        "puede_escribir_transacciones": puede_escribir_transacciones,
        "puede_editar":               puede_editar,
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
        # CU-002 E1: no se puede dar de baja con transacciones CONFIRMADAS pendientes
        from transacciones.models import Transaccion
        tiene_tx = Transaccion.objects.filter(
            animal=animal, estado=Transaccion.Estado.CONFIRMADO
        ).exists()
        if tiene_tx:
            messages.error(
                request,
                "No se puede dar de baja este animal: tiene transacciones comerciales "
                "confirmadas. Anúlalas primero si corresponde."
            )
            return redirect("animals:detail", pk=animal.pk)

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


@login_required
@require_perm("animals.read")
def rfid_lookup(request):
    """API JSON: busca un animal por código RFID.

    GET ?code=<rfid>
    Respuesta: { found: bool, animal: {...} | null, rfid: str }
    """
    code = request.GET.get("code", "").strip()
    if not code:
        return JsonResponse({"found": False, "error": "Código vacío", "rfid": ""})

    try:
        animal = Animal.objects.select_related("potrero").get(rfid=code)
        puede_pesaje = has_perm_code(request.user, "animals.write")
        puede_evento = has_perm_code(request.user, "eventos.write")
        puede_tx     = has_perm_code(request.user, "transacciones.write")
        return JsonResponse({
            "found": True,
            "rfid": code,
            "animal": {
                "pk":             animal.pk,
                "rfid":           animal.rfid or "",
                "nombre":         animal.nombre or "",
                "display":        animal.nombre or animal.rfid or "Sin ID",
                "raza":           animal.raza or "",
                "sexo":           animal.get_sexo_display() if animal.sexo else "",
                "etapa":          animal.get_etapa_display() if animal.etapa else "",
                "estado":         animal.estado,
                "estado_display": animal.get_estado_display(),
                "potrero":        str(animal.potrero) if animal.potrero else "Sin lote",
                "url_detalle":    reverse("animals:detail", args=[animal.pk]),
                "url_pesaje":     (reverse("pesajes:create") + f"?animal={animal.pk}") if puede_pesaje else "",
                "url_evento":     (reverse("eventos:create") + f"?animal={animal.pk}") if puede_evento else "",
                "url_transaccion":(reverse("transacciones:create") + f"?animal={animal.pk}") if puede_tx and animal.estado == "ACT" else "",
            },
        })
    except Animal.DoesNotExist:
        return JsonResponse({"found": False, "rfid": code})


@login_required
@require_perm("animals.read")
def rfid_scan(request):
    """Página dedicada de escaneo RFID.

    Modo autónomo: el usuario escanea y el sistema busca el animal.
    Soporta:
      - Lectores USB HID (emulación de teclado, el lector envía Enter al final)
      - Web Serial API (lectores serie RS-232 / USB-CDC)
      - Web NFC (Android Chrome con tags NFC)
    """
    return render(request, "animals/rfid_scan.html", {
        "lookup_url": reverse("animals:rfid_lookup"),
        "create_url": reverse("animals:create"),
        "puede_crear": has_perm_code(request.user, "animals.write"),
    })


@login_required
@require_perm("animals.write")
@require_POST
def animal_foto(request, pk: int):
    """Actualizar o eliminar la foto de un animal (POST únicamente).

    Campos POST:
      - accion = "subir"    → request.FILES["foto"] reemplaza la foto actual.
      - accion = "eliminar" → borra el archivo y pone foto=None.
    """
    animal = get_object_or_404(Animal, pk=pk)

    accion = request.POST.get("accion", "subir").strip()

    if accion == "eliminar":
        if animal.foto:
            animal.foto.delete(save=False)   # borra el archivo físico
            animal.foto = None
            animal.last_modified_by = request.user
            animal.save(update_fields=["foto", "last_modified_by", "updated_at"])
            messages.success(request, "Foto eliminada correctamente.")
        else:
            messages.warning(request, "El animal no tiene foto para eliminar.")

    else:  # subir / reemplazar
        foto = request.FILES.get("foto")
        if not foto:
            messages.error(request, "No se recibió ningún archivo de imagen.")
            return redirect("animals:detail", pk=pk)

        # Validación básica de tipo MIME en el servidor
        allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if foto.content_type not in allowed_types:
            messages.error(request, "Formato no soportado. Usa JPG, PNG, WEBP o GIF.")
            return redirect("animals:detail", pk=pk)

        # Limitar tamaño: 5 MB
        max_bytes = 5 * 1024 * 1024
        if foto.size > max_bytes:
            messages.error(request, "La imagen no puede superar los 5 MB.")
            return redirect("animals:detail", pk=pk)

        # Borrar la foto anterior si existe
        if animal.foto:
            animal.foto.delete(save=False)

        animal.foto = foto
        animal.last_modified_by = request.user
        animal.save(update_fields=["foto", "last_modified_by", "updated_at"])
        messages.success(request, "Foto actualizada correctamente.")

    return redirect("animals:detail", pk=pk)


@login_required
@require_perm("animals.write")
@require_POST
def animal_assign_potrero(request, pk: int):
    """Cambia únicamente el potrero asignado a un animal (POST)."""
    animal = get_object_or_404(Animal, pk=pk)
    potrero_id = request.POST.get("potrero_id", "").strip()

    if potrero_id:
        potrero = get_object_or_404(PotreroModel, pk=potrero_id, estado="ACTIVO")
        animal.potrero = potrero
    else:
        animal.potrero = None

    animal.last_modified_by = request.user
    animal.save(update_fields=["potrero", "last_modified_by", "updated_at"])
    messages.success(request, "Potrero actualizado correctamente.")
    return redirect("animals:detail", pk=animal.pk)
