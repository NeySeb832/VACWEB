import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Alerta(models.Model):
    class Tipo(models.TextChoices):
        SANITARIA = "sanitaria", "Sanitaria"
        PRODUCTIVA = "productiva", "Productiva"
        POTRERO = "potrero", "Potrero"
        INVENTARIO = "inventario", "Inventario"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ATENDIDA = "atendida", "Atendida"

    id_alerta = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    mensaje = models.TextField()
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    fecha_objetivo = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    # Referencia polimórfica (Animal pk o Potrero pk almacenado como string)
    id_entidad_referencia = models.CharField(max_length=50, null=True, blank=True)
    tipo_entidad = models.CharField(max_length=20, null=True, blank=True)  # 'animal' | 'potrero'
    origen = models.CharField(max_length=50)
    atendida_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="alertas_atendidas"
    )
    fecha_atencion = models.DateTimeField(null=True, blank=True)
    observacion_atencion = models.TextField(blank=True)
    evento_sanitario = models.ForeignKey(
        "eventos.EventoSanitario",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="alertas",
    )

    class Meta:
        ordering = ["-fecha_generacion"]
        verbose_name = "Alerta"
        verbose_name_plural = "Alertas"
        permissions = [
            ("view_alertas", "Puede ver alertas"),
            ("atender_alertas", "Puede atender alertas"),
            ("configurar_alertas", "Puede configurar reglas de alertas"),
        ]

    def __str__(self):
        return f"[{self.tipo}] {self.mensaje[:60]}"

    def clean(self):
        # RN-4: estado unidireccional — no revertir de atendida a pendiente
        if self.pk:
            try:
                original = Alerta.objects.get(pk=self.pk)
            except Alerta.DoesNotExist:
                pass
            else:
                if original.estado == self.Estado.ATENDIDA and self.estado == self.Estado.PENDIENTE:
                    raise ValidationError("No se puede revertir una alerta atendida a pendiente.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def atender(self, usuario, observacion=""):
        self.estado = self.Estado.ATENDIDA
        self.atendida_por = usuario
        self.fecha_atencion = timezone.now()
        self.observacion_atencion = observacion
        self.save()
        # Si la alerta está vinculada a un evento sanitario mutable, marcarlo como REALIZADO
        if self.evento_sanitario_id:
            from eventos.models import EventoSanitario
            try:
                ev = EventoSanitario.objects.get(pk=self.evento_sanitario_id)
                if ev.estado in ev.ESTADOS_MUTABLES:
                    ev.estado = EventoSanitario.Estado.REALIZADO
                    ev.save()
            except EventoSanitario.DoesNotExist:
                pass


class ReglaAlerta(models.Model):
    class Tipo(models.TextChoices):
        SANITARIA = "sanitaria", "Sanitaria"
        PRODUCTIVA = "productiva", "Productiva"
        POTRERO = "potrero", "Potrero"
        INVENTARIO = "inventario", "Inventario"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    subtipo = models.CharField(max_length=50)
    activa = models.BooleanField(default=True)
    umbral_valor = models.FloatField()
    umbral_unidad = models.CharField(max_length=20)  # 'dias', 'porcentaje'
    descripcion = models.TextField()

    class Meta:
        unique_together = ["tipo", "subtipo"]
        verbose_name = "Regla de Alerta"
        verbose_name_plural = "Reglas de Alerta"
        ordering = ["tipo", "subtipo"]

    def __str__(self):
        return f"{self.get_tipo_display()} / {self.subtipo} ({self.umbral_valor} {self.umbral_unidad})"
