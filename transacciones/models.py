# transacciones/models.py
from datetime import date as _date
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Transaccion(models.Model):
    """CU-006: Registro de transacciones comerciales (Compras, Ventas, Sacrificios).

    RN-1: tipo obligatorio ∈ {COM, VEN, SAC}
    RN-2: valor_cop > 0
    RN-3: fecha <= today  (usa date.today(), no timezone.now().date())
    RN-4: compatibilidad estado animal / tipo
    RN-5: atomicidad en la vista con transaction.atomic()
    RN-6: baja lógica únicamente (estado ANULADO con motivo obligatorio)
    """

    class Tipo(models.TextChoices):
        COMPRA     = "COM", "Compra"
        VENTA      = "VEN", "Venta"
        SACRIFICIO = "SAC", "Sacrificio"

    class Estado(models.TextChoices):
        CONFIRMADO = "CON", "Confirmado"
        ANULADO    = "ANU", "Anulado"

    tipo = models.CharField(max_length=3, choices=Tipo.choices)
    fecha = models.DateField()
    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.PROTECT,
        related_name="transacciones",
    )
    peso_final_kg = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    origen_destino = models.CharField(max_length=200)
    valor_cop = models.DecimalField(max_digits=12, decimal_places=2)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(
        max_length=3, choices=Estado.choices, default=Estado.CONFIRMADO
    )
    motivo_anulacion = models.TextField(blank=True, null=True)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        related_name="transacciones_anuladas",
        on_delete=models.SET_NULL,
    )
    fecha_anulacion = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transacciones_creadas",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-created_at"]
        indexes = [
            models.Index(fields=["tipo"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["fecha"]),
            models.Index(fields=["animal"]),
        ]

    def __str__(self):
        identificador = self.animal.rfid or self.animal.nombre or "SIN-ID"
        return f"{self.get_tipo_display()} · {identificador} · {self.fecha:%Y-%m-%d}"

    def clean(self):
        errors = {}

        # RN-2: valor_cop > 0
        if self.valor_cop is not None and self.valor_cop <= 0:
            errors["valor_cop"] = "El valor debe ser mayor a cero."

        # RN-3: fecha <= today (date.today(), no timezone.now().date())
        if self.fecha and self.fecha > _date.today():
            errors["fecha"] = "La fecha no puede ser posterior a hoy."

        # RN-4: compatibilidad estado animal / tipo
        if self.animal_id:
            from animals.models import Animal
            try:
                animal = Animal.objects.get(pk=self.animal_id)
            except Animal.DoesNotExist:
                pass
            else:
                if self.tipo in (self.Tipo.VENTA, self.Tipo.SACRIFICIO):
                    if animal.estado != Animal.Estado.ACTIVO:
                        errors["animal"] = (
                            f"Solo se pueden registrar ventas o sacrificios sobre animales "
                            f"en estado Activo. Estado actual: {animal.get_estado_display()}."
                        )
                elif self.tipo == self.Tipo.COMPRA:
                    if animal.estado == Animal.Estado.INACTIVO:
                        errors["animal"] = (
                            "No se puede registrar una compra sobre un animal en estado Inactivo."
                        )

        if errors:
            raise ValidationError(errors)
        return super().clean()

    @property
    def es_anulable(self):
        return self.estado == self.Estado.CONFIRMADO

    @property
    def es_anulada(self):
        return self.estado == self.Estado.ANULADO

    def aplicar_impacto_inventario(self):
        """RN-5: Aplica el cambio de estado al animal. Debe llamarse dentro de transaction.atomic() en la vista."""
        from animals.models import Animal
        animal = self.animal
        if self.tipo == self.Tipo.COMPRA:
            animal.estado = Animal.Estado.ACTIVO
        elif self.tipo in (self.Tipo.VENTA, self.Tipo.SACRIFICIO):
            animal.estado = Animal.Estado.INACTIVO
        animal.save(update_fields=["estado", "updated_at"])

    def revertir_impacto_inventario(self, estado_previo_animal):
        """Restaura animal.estado al valor recibido. Debe llamarse dentro de transaction.atomic() en la vista."""
        animal = self.animal
        animal.estado = estado_previo_animal
        animal.save(update_fields=["estado", "updated_at"])
