"""
Lógica de evaluación de alertas.
Usada tanto por el comando `generar_alertas` (batch) como por las señales (tiempo real).
"""
from datetime import timedelta

from django.utils import timezone


# ── helpers internos ───────────────────────────────────────────────────────────

def _label_animal(animal):
    return animal.nombre or animal.rfid or f"ID:{animal.pk}"


def _existe_pendiente(tipo, subtipo_tag, id_entidad=None):
    """Deduplicación para alertas sin entidad directa (productiva, potrero, inventario)."""
    from .models import Alerta
    qs = Alerta.objects.filter(tipo=tipo, estado="pendiente", origen__contains="job_automatico")
    if id_entidad is not None:
        qs = qs.filter(id_entidad_referencia=str(id_entidad), mensaje__icontains=subtipo_tag)
    else:
        qs = qs.filter(mensaje__icontains=subtipo_tag)
    return qs.exists()


def _existe_pendiente_para_evento(evento_sanitario_pk):
    """Deduplicación precisa para alertas vinculadas a un EventoSanitario."""
    from .models import Alerta
    return Alerta.objects.filter(
        tipo="sanitaria",
        estado="pendiente",
        evento_sanitario_id=evento_sanitario_pk,
    ).exists()


def _crear_alerta(tipo, mensaje, id_entidad=None, tipo_entidad=None,
                  fecha_objetivo=None, evento_sanitario=None):
    from .models import Alerta
    Alerta.objects.create(
        tipo=tipo,
        mensaje=mensaje,
        origen="job_automatico",
        id_entidad_referencia=str(id_entidad) if id_entidad is not None else None,
        tipo_entidad=tipo_entidad,
        fecha_objetivo=fecha_objetivo,
        evento_sanitario=evento_sanitario,
    )


# ── evaluadores ────────────────────────────────────────────────────────────────

def evaluar_sanitaria_proxima_vacuna(animal_pk=None):
    """CP-01: eventos programados que vencen en los próximos N días."""
    from eventos.models import EventoSanitario
    from .models import ReglaAlerta

    regla = ReglaAlerta.objects.filter(tipo="sanitaria", subtipo="proxima_vacuna", activa=True).first()
    if not regla:
        return 0

    hoy = timezone.now().date()
    limite = hoy + timedelta(days=int(regla.umbral_valor))
    count = 0

    qs = EventoSanitario.objects.filter(
        fecha__gte=hoy,
        fecha__lte=limite,
        estado__in=["CON", "APL"],
    ).select_related("animal")

    if animal_pk is not None:
        qs = qs.filter(animal_id=animal_pk)

    for ev in qs:
        animal = ev.animal
        if not _existe_pendiente_para_evento(ev.pk):
            _crear_alerta(
                tipo="sanitaria",
                mensaje=f"Próxima vacuna: {_label_animal(animal)} — {ev.tipo} programado el {ev.fecha}.",
                id_entidad=animal.pk,
                tipo_entidad="animal",
                fecha_objetivo=ev.fecha,
                evento_sanitario=ev,
            )
            count += 1
    return count


def evaluar_sanitaria_vacuna_vencida(animal_pk=None):
    """CP-02: eventos confirmados/aplazados con fecha pasada."""
    from eventos.models import EventoSanitario
    from .models import ReglaAlerta

    regla = ReglaAlerta.objects.filter(tipo="sanitaria", subtipo="vacuna_vencida", activa=True).first()
    if not regla:
        return 0

    hoy = timezone.now().date()
    count = 0

    qs = EventoSanitario.objects.filter(
        fecha__lt=hoy,
        estado__in=["CON", "APL"],
    ).select_related("animal")

    if animal_pk is not None:
        qs = qs.filter(animal_id=animal_pk)

    for ev in qs:
        animal = ev.animal
        if not _existe_pendiente_para_evento(ev.pk):
            _crear_alerta(
                tipo="sanitaria",
                mensaje=f"Vacuna vencida: {_label_animal(animal)} — {ev.tipo} no realizado (vencía {ev.fecha}).",
                id_entidad=animal.pk,
                tipo_entidad="animal",
                fecha_objetivo=ev.fecha,
                evento_sanitario=ev,
            )
            count += 1
    return count


def evaluar_productiva_variacion_peso(animal_pk=None):
    """CP-04: animales con variación de peso mayor al umbral%."""
    from pesajes.models import Pesaje
    from animals.models import Animal
    from .models import ReglaAlerta

    regla = ReglaAlerta.objects.filter(tipo="productiva", subtipo="variacion_peso", activa=True).first()
    if not regla:
        return 0

    umbral = regla.umbral_valor / 100.0
    count = 0

    animales = Animal.objects.filter(estado="ACT", pk=animal_pk) if animal_pk else Animal.objects.filter(estado="ACT")

    for animal in animales:
        pesajes = list(Pesaje.objects.filter(animal=animal).order_by("-fecha")[:2])
        if len(pesajes) < 2 or not pesajes[1].peso_kg:
            continue
        ultimo, anterior = pesajes[0], pesajes[1]
        variacion = abs((float(ultimo.peso_kg) - float(anterior.peso_kg)) / float(anterior.peso_kg))
        if variacion > umbral:
            tag = f"variación peso [{animal.pk}]"
            if not _existe_pendiente("productiva", tag, animal.pk):
                _crear_alerta(
                    tipo="productiva",
                    mensaje=(
                        f"Variación de peso significativa: {_label_animal(animal)} "
                        f"cambió {variacion * 100:.1f}% (de {anterior.peso_kg} a {ultimo.peso_kg} kg). {tag}"
                    ),
                    id_entidad=animal.pk,
                    tipo_entidad="animal",
                    fecha_objetivo=ultimo.fecha,
                )
                count += 1
    return count


def evaluar_productiva_sin_pesaje(animal_pk=None):
    """CP-04: animales activos sin pesaje en los últimos N días."""
    from pesajes.models import Pesaje
    from animals.models import Animal
    from .models import ReglaAlerta

    regla = ReglaAlerta.objects.filter(tipo="productiva", subtipo="sin_pesaje", activa=True).first()
    if not regla:
        return 0

    hoy = timezone.now().date()
    limite = hoy - timedelta(days=int(regla.umbral_valor))
    count = 0

    animales = Animal.objects.filter(estado="ACT", pk=animal_pk) if animal_pk else Animal.objects.filter(estado="ACT")

    for animal in animales:
        ultimo = Pesaje.objects.filter(animal=animal).order_by("-fecha").first()
        if ultimo is None or ultimo.fecha < limite:
            tag = f"sin pesaje [{animal.pk}]"
            if not _existe_pendiente("productiva", tag, animal.pk):
                dias = int(regla.umbral_valor)
                _crear_alerta(
                    tipo="productiva",
                    mensaje=f"Sin pesaje: {_label_animal(animal)} no tiene registro en los últimos {dias} días. {tag}",
                    id_entidad=animal.pk,
                    tipo_entidad="animal",
                )
                count += 1
    return count


def evaluar_potrero_capacidad(potrero_pk=None):
    """CP-05: potreros con ocupación >= umbral%."""
    from potreros.models import Potrero
    from .models import ReglaAlerta

    regla = ReglaAlerta.objects.filter(tipo="potrero", subtipo="capacidad", activa=True).first()
    if not regla:
        return 0

    umbral = regla.umbral_valor / 100.0
    count = 0

    potreros = Potrero.objects.filter(estado="ACTIVO", pk=potrero_pk) if potrero_pk else Potrero.objects.filter(estado="ACTIVO")

    for potrero in potreros:
        if not potrero.capacidad_maxima:
            continue
        ocupacion = potrero.get_animales_activos_count()
        pct = ocupacion / potrero.capacidad_maxima
        if pct >= umbral:
            tag = f"capacidad potrero [{potrero.pk}]"
            if not _existe_pendiente("potrero", tag, potrero.pk):
                _crear_alerta(
                    tipo="potrero",
                    mensaje=(
                        f"Capacidad: potrero {potrero.nombre_codigo} al {pct * 100:.0f}% "
                        f"({ocupacion}/{potrero.capacidad_maxima} animales). {tag}"
                    ),
                    id_entidad=potrero.pk,
                    tipo_entidad="potrero",
                )
                count += 1
    return count


def evaluar_inventario_sin_potrero(animal_pk=None):
    """Animales activos sin potrero asignado."""
    from animals.models import Animal
    from .models import ReglaAlerta

    regla = ReglaAlerta.objects.filter(tipo="inventario", subtipo="sin_potrero", activa=True).first()
    if not regla:
        return 0

    count = 0
    qs = Animal.objects.filter(estado="ACT", potrero__isnull=True)
    if animal_pk is not None:
        qs = qs.filter(pk=animal_pk)

    for animal in qs:
        tag = f"sin potrero [{animal.pk}]"
        if not _existe_pendiente("inventario", tag, animal.pk):
            _crear_alerta(
                tipo="inventario",
                mensaje=f"Sin potrero: {_label_animal(animal)} está activo sin potrero asignado. {tag}",
                id_entidad=animal.pk,
                tipo_entidad="animal",
            )
            count += 1
    return count


def evaluar_inventario_borrador(animal_pk=None):
    """Animales en estado BORRADOR por más de N días."""
    from animals.models import Animal
    from .models import ReglaAlerta

    regla = ReglaAlerta.objects.filter(tipo="inventario", subtipo="borrador", activa=True).first()
    if not regla:
        return 0

    limite_dt = timezone.now() - timedelta(days=int(regla.umbral_valor))
    count = 0

    qs = Animal.objects.filter(estado="BOR", created_at__lte=limite_dt)
    if animal_pk is not None:
        qs = qs.filter(pk=animal_pk)

    for animal in qs:
        tag = f"estado borrador [{animal.pk}]"
        if not _existe_pendiente("inventario", tag, animal.pk):
            dias = int(regla.umbral_valor)
            _crear_alerta(
                tipo="inventario",
                mensaje=f"Borrador prolongado: {_label_animal(animal)} lleva más de {dias} días en estado borrador. {tag}",
                id_entidad=animal.pk,
                tipo_entidad="animal",
            )
            count += 1
    return count
