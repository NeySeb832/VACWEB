from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Animal

@receiver(pre_save, sender=Animal)
def bloquear_identificadores_con_historial(sender, instance: Animal, **kwargs):
    if not instance.pk:
        return
    prev = Animal.objects.get(pk=instance.pk)
    if prev.tiene_historial:
        if prev.rfid != instance.rfid or prev.arete != instance.arete:
            raise ValidationError("RN-1: No se puede modificar RFID/Arete con historial existente.")
