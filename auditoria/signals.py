"""
CU-010: Signal handlers para captura automática de eventos CRUD.

Cada modelo auditado registra:
  - pre_save  → captura el estado anterior (delta para ediciones)
  - post_save → escribe el registro en Bitacora
  - post_delete → registra eliminaciones físicas (solo Movimiento, si aplica)

Modelos y módulos cubiertos:
  Animal         → CU-02
  EventoSanitario → CU-03
  Pesaje         → CU-04
  Potrero        → CU-05
  Transaccion    → CU-06
  Alerta         → CU-08
"""
import json

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.forms.models import model_to_dict


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _snapshot(instance):
    """Convierte una instancia de modelo a dict JSON-serializable."""
    try:
        data = model_to_dict(instance)
        # model_to_dict omite campos auto / no-editables; añadimos pk y timestamps
        data["id"] = instance.pk
        for field in ("created_at", "updated_at", "fecha", "fecha_evento"):
            val = getattr(instance, field, None)
            if val is not None:
                data[field] = str(val)
        # Eliminar objetos no serializables (ImageField, etc.)
        for key, value in list(data.items()):
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                data[key] = str(value)
        return data
    except Exception:
        return {"id": str(instance.pk)}


def _registrar(accion, entidad, entidad_id, modulo, resumen,
                valores_anteriores=None, valores_nuevos=None):
    """Llama al helper central de registro evitando errores silenciosos."""
    try:
        from auditoria.middleware import registrar_bitacora
        from auditoria.models import Bitacora
        registrar_bitacora(
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            modulo_origen=modulo,
            resumen=resumen,
            valores_anteriores=valores_anteriores,
            valores_nuevos=valores_nuevos,
        )
    except Exception:
        # Nunca bloquear la operación original por un fallo de auditoría de señal
        pass


# ─────────────────────────────────────────────────────────────────────────────
# CU-02: Animal
# ─────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender="animals.Animal")
def animal_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._audit_old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._audit_old = None
    else:
        instance._audit_old = None


@receiver(post_save, sender="animals.Animal")
def animal_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_audit_old", None)
    if created:
        _registrar(
            accion="CREAR",
            entidad="Animal",
            entidad_id=instance.pk,
            modulo="CU-02",
            resumen=f"Animal registrado: {instance}",
            valores_nuevos=_snapshot(instance),
        )
    else:
        _registrar(
            accion="EDITAR",
            entidad="Animal",
            entidad_id=instance.pk,
            modulo="CU-02",
            resumen=f"Animal editado: {instance}",
            valores_anteriores=_snapshot(old) if old else None,
            valores_nuevos=_snapshot(instance),
        )


# ─────────────────────────────────────────────────────────────────────────────
# CU-03: EventoSanitario
# ─────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender="eventos.EventoSanitario")
def evento_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._audit_old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._audit_old = None
    else:
        instance._audit_old = None


@receiver(post_save, sender="eventos.EventoSanitario")
def evento_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_audit_old", None)
    accion = "CREAR" if created else "EDITAR"
    _registrar(
        accion=accion,
        entidad="EventoSanitario",
        entidad_id=instance.pk,
        modulo="CU-03",
        resumen=f"Evento sanitario {accion.lower()}: {instance.tipo} — {instance.animal}",
        valores_anteriores=_snapshot(old) if old else None,
        valores_nuevos=_snapshot(instance),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CU-04: Pesaje
# ─────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender="pesajes.Pesaje")
def pesaje_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._audit_old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._audit_old = None
    else:
        instance._audit_old = None


@receiver(post_save, sender="pesajes.Pesaje")
def pesaje_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_audit_old", None)
    accion = "CREAR" if created else "EDITAR"
    _registrar(
        accion=accion,
        entidad="Pesaje",
        entidad_id=instance.pk,
        modulo="CU-04",
        resumen=f"Pesaje {accion.lower()}: {instance.peso_kg} kg — {instance.animal}",
        valores_anteriores=_snapshot(old) if old else None,
        valores_nuevos=_snapshot(instance),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CU-05: Potrero
# ─────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender="potreros.Potrero")
def potrero_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._audit_old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._audit_old = None
    else:
        instance._audit_old = None


@receiver(post_save, sender="potreros.Potrero")
def potrero_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_audit_old", None)
    accion = "CREAR" if created else "EDITAR"
    _registrar(
        accion=accion,
        entidad="Potrero",
        entidad_id=instance.pk,
        modulo="CU-05",
        resumen=f"Potrero {accion.lower()}: {instance.nombre_codigo}",
        valores_anteriores=_snapshot(old) if old else None,
        valores_nuevos=_snapshot(instance),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CU-06: Transaccion
# ─────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender="transacciones.Transaccion")
def transaccion_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._audit_old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._audit_old = None
    else:
        instance._audit_old = None


@receiver(post_save, sender="transacciones.Transaccion")
def transaccion_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_audit_old", None)
    accion = "CREAR" if created else "EDITAR"
    tipo_display = instance.get_tipo_display() if hasattr(instance, "get_tipo_display") else instance.tipo
    _registrar(
        accion=accion,
        entidad="Transaccion",
        entidad_id=instance.pk,
        modulo="CU-06",
        resumen=f"Transacción {accion.lower()}: {tipo_display} — {instance.animal}",
        valores_anteriores=_snapshot(old) if old else None,
        valores_nuevos=_snapshot(instance),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CU-08: Alerta
# ─────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender="alertas.Alerta")
def alerta_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._audit_old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._audit_old = None
    else:
        instance._audit_old = None


@receiver(post_save, sender="alertas.Alerta")
def alerta_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, "_audit_old", None)
    accion = "CREAR" if created else "EDITAR"
    _registrar(
        accion=accion,
        entidad="Alerta",
        entidad_id=instance.pk,
        modulo="CU-08",
        resumen=f"Alerta {accion.lower()}: {instance.tipo} — {instance.mensaje[:80]}",
        valores_anteriores=_snapshot(old) if old else None,
        valores_nuevos=_snapshot(instance),
    )
