# pesajes/models.py
from decimal import Decimal
from datetime import date as _date
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Pesaje(models.Model):
    """CU-004: Registro inmutable de peso de un animal.

    RN-1: peso_kg > 0
    RN-2: animal debe estar ACTIVO
    RN-3: inmutabilidad (no update, solo crear nuevo)
    RN-5: sin eliminaciones físicas
    RN-6: variacion_kg y promedio_diario_g calculados automáticamente
    """

    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.PROTECT,
        related_name="pesajes",
    )
    fecha = models.DateField(default=timezone.now)
    peso_kg = models.DecimalField(max_digits=7, decimal_places=2)
    observaciones = models.TextField(blank=True, null=True)
    foto_bascula = models.ImageField(
        upload_to="pesajes/fotos/",
        blank=True,
        null=True,
    )
    responsable = models.CharField(max_length=64, blank=True, null=True)
    # Calculados automáticamente al guardar (RN-6)
    variacion_kg = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Diferencia respecto al pesaje anterior en kg. Positivo=ganancia, negativo=pérdida.",
    )
    promedio_diario_g = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Promedio de ganancia/pérdida diaria en g/día respecto al pesaje anterior.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-created_at"]

    def __str__(self):
        return f"{self.peso_kg} kg · {self.fecha:%Y-%m-%d}"

    def clean(self):
        errors = {}
        # RN-1: peso > 0
        if self.peso_kg is not None and self.peso_kg <= 0:
            errors["peso_kg"] = "El peso debe ser mayor a cero."
        # RN-2: solo animales ACTIVOS
        if self.animal_id:
            from animals.models import Animal
            try:
                animal = Animal.objects.get(pk=self.animal_id)
            except Animal.DoesNotExist:
                pass
            else:
                if animal.estado != Animal.Estado.ACTIVO:
                    errors["animal"] = "Solo se pueden registrar pesajes en animales con estado Activo."
        # Fecha no futura
        if self.fecha and self.fecha > _date.today():
            errors["fecha"] = "La fecha del pesaje no puede ser posterior a hoy."
        if errors:
            raise ValidationError(errors)
        return super().clean()

    def calcular_variacion(self):
        """RN-6: Calcula variacion_kg y promedio_diario_g respecto al pesaje anterior cronológico.
        Llamado desde save() antes de persistir.
        Si faltan datos mínimos (fecha, animal_id, peso_kg) deja los campos en None sin lanzar excepción.
        """
        if not self.animal_id or not self.fecha or self.peso_kg is None:
            self.variacion_kg = None
            self.promedio_diario_g = None
            return

        try:
            anterior = (
                Pesaje.objects.filter(
                    animal=self.animal_id,
                    fecha__lte=self.fecha,
                )
                .exclude(pk=self.pk)
                .order_by("-fecha", "-created_at")
                .first()
            )
        except Exception:
            # Si la consulta falla (ej. en tests sin migraciones completas), dejar en None
            self.variacion_kg = None
            self.promedio_diario_g = None
            return

        if anterior:
            try:
                self.variacion_kg = self.peso_kg - anterior.peso_kg
                dias = (self.fecha - anterior.fecha).days
                if dias > 0:
                    self.promedio_diario_g = (
                        self.variacion_kg * Decimal("1000") / dias
                    ).quantize(Decimal("0.1"))
                else:
                    self.promedio_diario_g = None
            except (TypeError, ArithmeticError):
                # Valores no comparables (ej. Decimal inválido): dejar variación en None
                self.variacion_kg = None
                self.promedio_diario_g = None
        else:
            self.variacion_kg = None
            self.promedio_diario_g = None

    def save(self, *args, **kwargs):
        # RN-3: inmutabilidad — no permitir updates
        if self.pk:
            raise ValueError(
                "RN-3: Los pesajes son inmutables. Crea un nuevo registro con observación correctiva."
            )
        self.calcular_variacion()
        super().save(*args, **kwargs)
