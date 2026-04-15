# potreros/models.py
"""Modelo de Potrero/Lote — CU-005.

Gestión de potreros y lotes de la finca. Incluye control de capacidad
y ocupación. Baja lógica obligatoria (estado INACTIVO); nunca eliminación física.
"""

from django.conf import settings
from django.db import models


class Potrero(models.Model):
    """CU-005: Potrero/Lote para asignación y control de animales.

    RN-1: nombre_codigo único globalmente.
    RN-2: no se puede desactivar un potrero con animales activos asignados.
    RN-3: toda eliminación es lógica (estado INACTIVO).
    """

    class TipoUso(models.TextChoices):
        CEBA       = "CEBA",       "Ceba"
        LEVANTE    = "LEVANTE",    "Levante"
        MATERNIDAD = "MATERNIDAD", "Maternidad"
        CUARENTENA = "CUARENTENA", "Cuarentena"
        ROTACION   = "ROTACION",   "Rotación"

    class Estado(models.TextChoices):
        ACTIVO   = "ACTIVO",   "Activo"
        INACTIVO = "INACTIVO", "Inactivo"

    nombre_codigo = models.CharField(
        max_length=100,
        verbose_name="Nombre o código",
        unique=True,
    )
    area_ha = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Área (ha)",
    )
    capacidad_maxima = models.IntegerField(
        verbose_name="Capacidad máxima (animales)",
    )
    tipo_uso = models.CharField(
        max_length=20,
        choices=TipoUso.choices,
        verbose_name="Tipo de uso",
    )
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.ACTIVO,
        verbose_name="Estado",
    )
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name="Observaciones",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Creado por",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última modificación")

    class Meta:
        verbose_name = "Potrero"
        verbose_name_plural = "Potreros"
        ordering = ["nombre_codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["nombre_codigo"],
                name="unique_nombre_codigo_potrero",
            )
        ]

    def __str__(self) -> str:
        return self.nombre_codigo

    # --- helpers de ocupación ---------------------------------------------------

    def get_animales_activos_count(self) -> int:
        """Retorna el número de animales en estado ACTIVO asignados a este potrero."""
        return self.animales.filter(estado="ACT").count()

    def get_porcentaje_ocupacion(self) -> float:
        """Retorna el porcentaje de ocupación respecto a la capacidad máxima."""
        if self.capacidad_maxima and self.capacidad_maxima > 0:
            return round((self.get_animales_activos_count() / self.capacidad_maxima) * 100, 1)
        return 0.0
