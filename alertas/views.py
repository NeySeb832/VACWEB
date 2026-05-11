import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from authz.decorators import require_perm
from authz.models import AuditLog
from .forms import AtenderAlertaForm
from .models import Alerta, ReglaAlerta


@login_required
@require_perm("alertas.view_alertas")
def index_view(request):
    qs = Alerta.objects.select_related("atendida_por").all()

    tipo = request.GET.get("tipo", "")
    estado = request.GET.get("estado", "")
    fecha_desde = request.GET.get("fecha_desde", "")
    fecha_hasta = request.GET.get("fecha_hasta", "")
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if fecha_desde:
        qs = qs.filter(fecha_objetivo__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha_objetivo__lte=fecha_hasta)
    if q:
        qs = qs.filter(mensaje__icontains=q)

    qs = qs.annotate(
        orden_estado=Case(
            When(estado="pendiente", then=0),
            default=1,
            output_field=IntegerField(),
        )
    ).order_by("orden_estado", "fecha_objetivo")

    total_pendientes = Alerta.objects.filter(estado="pendiente").count()
    sanitarias = Alerta.objects.filter(estado="pendiente", tipo="sanitaria").count()
    productivas = Alerta.objects.filter(estado="pendiente", tipo="productiva").count()
    potreros_kpi = Alerta.objects.filter(estado="pendiente", tipo="potrero").count()

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj": page_obj,
        "total_pendientes": total_pendientes,
        "sanitarias_pendientes": sanitarias,
        "productivas_pendientes": productivas,
        "potreros_pendientes": potreros_kpi,
        "tipo_filter": tipo,
        "estado_filter": estado,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "q": q,
        "tipos": Alerta.Tipo.choices,
        "estados": Alerta.Estado.choices,
    }
    return render(request, "alertas/index.html", ctx)


@login_required
@require_perm("alertas.view_alertas")
def detalle_view(request, id_alerta):
    alerta = get_object_or_404(Alerta, pk=id_alerta)
    animal = None
    if alerta.tipo_entidad == "animal" and alerta.id_entidad_referencia:
        from animals.models import Animal
        try:
            animal = Animal.objects.get(pk=alerta.id_entidad_referencia)
        except (Animal.DoesNotExist, ValueError):
            pass

    ctx = {
        "alerta": alerta,
        "animal": animal,
        "form": AtenderAlertaForm(),
    }
    return render(request, "alertas/detalle.html", ctx)


@login_required
@require_perm("alertas.atender_alertas")
@require_POST
def atender_view(request, id_alerta):
    alerta = get_object_or_404(Alerta, pk=id_alerta)

    if alerta.estado == Alerta.Estado.ATENDIDA:
        messages.warning(request, "Esta alerta ya fue atendida.")
        return redirect("alertas:detalle", id_alerta=id_alerta)

    form = AtenderAlertaForm(request.POST)
    if form.is_valid():
        observacion = form.cleaned_data.get("observacion", "")
        alerta.atender(request.user, observacion)

        AuditLog.objects.create(
            user=request.user,
            action="alerta_atendida",
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            metadata={"id_alerta": str(id_alerta), "tipo": alerta.tipo},
        )
        messages.success(request, "Alerta marcada como atendida.")
        return redirect("alertas:index")

    messages.error(request, "Error al procesar el formulario.")
    return redirect("alertas:detalle", id_alerta=id_alerta)


@login_required
@require_perm("alertas.configurar_alertas")
def configuracion_view(request):
    reglas = ReglaAlerta.objects.all()

    if request.method == "POST":
        for regla in reglas:
            regla.activa = request.POST.get(f"activa_{regla.pk}") == "on"
            try:
                regla.umbral_valor = float(request.POST.get(f"umbral_valor_{regla.pk}", regla.umbral_valor))
            except (ValueError, TypeError):
                pass
            regla.save()
        messages.success(request, "Configuración guardada correctamente.")
        return redirect("alertas:configuracion")

    ctx = {"reglas": reglas}
    return render(request, "alertas/configuracion.html", ctx)


@login_required
def api_alertas_pendientes(request):
    pendientes = Alerta.objects.filter(estado="pendiente")
    count = pendientes.count()
    ultimas = list(pendientes.order_by("fecha_objetivo")[:5])
    data = {
        "count": count,
        "ultimas": [
            {
                "id": str(a.id_alerta),
                "tipo": a.tipo,
                "mensaje": a.mensaje[:80],
                "fecha_objetivo": a.fecha_objetivo.isoformat() if a.fecha_objetivo else None,
            }
            for a in ultimas
        ],
    }
    return JsonResponse(data)


@login_required
@require_perm("alertas.atender_alertas")
@require_http_methods(["PATCH"])
def api_atender(request, id_alerta):
    alerta = get_object_or_404(Alerta, pk=id_alerta)

    if alerta.estado == Alerta.Estado.ATENDIDA:
        return JsonResponse({"error": "Alerta ya atendida."}, status=400)

    try:
        body = json.loads(request.body)
        observacion = body.get("observacion", "")
    except (json.JSONDecodeError, AttributeError):
        observacion = ""

    alerta.atender(request.user, observacion)
    AuditLog.objects.create(
        user=request.user,
        action="alerta_atendida_api",
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        metadata={"id_alerta": str(id_alerta), "tipo": alerta.tipo},
    )
    return JsonResponse({"status": "ok"})
