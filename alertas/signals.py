"""
Señales que disparan la evaluación de alertas en tiempo real
cuando se guardan registros en los demás módulos del sistema.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


def _on_evento_sanitario_saved(sender, instance, **kwargs):
    from alertas.services import evaluar_sanitaria_proxima_vacuna, evaluar_sanitaria_vacuna_vencida
    evaluar_sanitaria_proxima_vacuna(animal_pk=instance.animal_id)
    evaluar_sanitaria_vacuna_vencida(animal_pk=instance.animal_id)


def _on_pesaje_saved(sender, instance, **kwargs):
    from alertas.services import evaluar_productiva_variacion_peso, evaluar_productiva_sin_pesaje
    evaluar_productiva_variacion_peso(animal_pk=instance.animal_id)
    evaluar_productiva_sin_pesaje(animal_pk=instance.animal_id)


def _on_animal_saved(sender, instance, **kwargs):
    from alertas.services import evaluar_inventario_sin_potrero, evaluar_inventario_borrador
    evaluar_inventario_sin_potrero(animal_pk=instance.pk)
    evaluar_inventario_borrador(animal_pk=instance.pk)


def _on_potrero_saved(sender, instance, **kwargs):
    from alertas.services import evaluar_potrero_capacidad
    evaluar_potrero_capacidad(potrero_pk=instance.pk)


def conectar_senales():
    """Conecta todas las señales. Llamado desde AlertasConfig.ready()."""
    from eventos.models import EventoSanitario
    from pesajes.models import Pesaje
    from animals.models import Animal
    from potreros.models import Potrero

    post_save.connect(_on_evento_sanitario_saved, sender=EventoSanitario, weak=False,
                      dispatch_uid="alertas_on_evento_saved")
    post_save.connect(_on_pesaje_saved, sender=Pesaje, weak=False,
                      dispatch_uid="alertas_on_pesaje_saved")
    post_save.connect(_on_animal_saved, sender=Animal, weak=False,
                      dispatch_uid="alertas_on_animal_saved")
    post_save.connect(_on_potrero_saved, sender=Potrero, weak=False,
                      dispatch_uid="alertas_on_potrero_saved")
