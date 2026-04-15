# eventos/models.py
"""Modelos del módulo de Eventos Sanitarios (CU-003).
Registro de vacunas, desparasitaciones y tratamientos veterinarios.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class EventoSanitario(models.Model):
    """CU-003: Registro de vacunas y tratamientos de un animal.

    Reglas de negocio:
      - RN-1: fecha, tipo, responsable y producto son obligatorios.
      - RN-2: no se puede registrar un evento en un animal INACTIVO.
      - RN-3: un evento en estado CANCELADO o REALIZADO es inmutable;
              no puede modificarse una vez alcanzado ese estado.
      - RN-4: solo se puede pasar a CANCELADO o REALIZADO desde
              CONFIRMADO o APLAZADO.
      - RN-5: evento_original apunta al evento que se corrige; permite
              rastrear la cadena de correcciones.
    """

    class Estado(models.TextChoices):
        CONFIRMADO = "CON", "Confirmado"
        APLAZADO = "APL", "Aplazado"
        CANCELADO = "CAN", "Cancelado"
        REALIZADO = "REA", "Realizado"

    # Estados en los que el evento aún puede editarse
    ESTADOS_MUTABLES = frozenset({Estado.CONFIRMADO, Estado.APLAZADO})
    # Estados terminales: el evento queda bloqueado
    ESTADOS_TERMINALES = frozenset({Estado.CANCELADO, Estado.REALIZADO})

    animal = models.ForeignKey(
        "animals.Animal",
        on_delete=models.PROTECT,
        related_name="eventos",
    )
    tipo = models.CharField(max_length=64)
    fecha = models.DateField(default=timezone.now)
    responsable = models.CharField(max_length=64)
    producto = models.CharField(max_length=128)
    dosis = models.CharField(max_length=32, blank=True, null=True)
    lote = models.CharField(max_length=64, blank=True, null=True)
    via_aplicacion = models.CharField(max_length=32, blank=True, null=True)
    notas = models.TextField(blank=True, null=True)
    estado = models.CharField(
        max_length=3,
        choices=Estado.choices,
        default=Estado.CONFIRMADO,
    )
    evento_original = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="correcciones",
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

    def __str__(self) -> str:
        return f"{self.tipo} · {self.fecha:%Y-%m-%d}"

    def clean(self):
        # RN-1: campos obligatorios
        errors = {}
        if not self.fecha:
            errors["fecha"] = "La fecha es obligatoria."
        if not self.tipo:
            errors["tipo"] = "El tipo es obligatorio."
        if not self.responsable:
            errors["responsable"] = "El responsable es obligatorio."
        if not self.producto:
            errors["producto"] = "El producto es obligatorio."
        if errors:
            raise ValidationError(errors)

        # RN-2: animal no puede estar INACTIVO
        if self.animal_id:
            from animals.models import Animal
            try:
                animal = Animal.objects.get(pk=self.animal_id)
            except Animal.DoesNotExist:
                pass
            else:
                if animal.estado == Animal.Estado.INACTIVO:
                    raise ValidationError(
                        {"animal": "No se pueden registrar eventos en un animal inactivo."}
                    )

        # RN-3: inmutabilidad — si ya existe y está en estado terminal, no se puede editar
        if self.pk:
            try:
                actual = EventoSanitario.objects.get(pk=self.pk)
            except EventoSanitario.DoesNotExist:
                pass
            else:
                if actual.estado in self.ESTADOS_TERMINALES:
                    raise ValidationError(
                        "Este evento ya está finalizado ("
                        f"{actual.get_estado_display()}) y no puede modificarse."
                    )

        # RN-4: nuevos eventos solo pueden crearse en estado CONFIRMADO o APLAZADO
        if not self.pk and self.estado in self.ESTADOS_TERMINALES:
            raise ValidationError(
                {"estado": "Un nuevo evento debe crearse en estado Confirmado o Aplazado."}
            )

        return super().clean()

    @property
    def puede_modificarse(self) -> bool:
        """True si el estado actual permite editar el evento."""
        return self.estado in self.ESTADOS_MUTABLES

    @property
    def es_correccion(self) -> bool:
        """True si este evento es una corrección de otro anterior."""
        return self.evento_original_id is not None
