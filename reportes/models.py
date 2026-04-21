# reportes/models.py
"""Modelo de auditoría para el módulo de Reportes y Analítica (CU-007)."""

from django.conf import settings
from django.db import models


class LogReporte(models.Model):
    """Registro inmutable de cada generación o exportación de reporte (CU-007, RN-5)."""

    TIPO_CHOICES = [
        ("inventario", "Inventario de Animales"),
        ("historial",  "Historial por Animal"),
        ("sanitario",  "Calendario Sanitario"),
        ("ventas",     "Reporte de Ventas"),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    tipo_reporte = models.CharField(max_length=20, choices=TIPO_CHOICES)
    filtros_aplicados = models.JSONField(default=dict, blank=True)
    formato_exportacion = models.CharField(max_length=10, blank=True)
    fecha_ejecucion = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_ejecucion"]
        verbose_name = "Log de reporte"
        verbose_name_plural = "Logs de reportes"

    def __str__(self) -> str:
        who = self.usuario.username if self.usuario else "anon"
        return f"{self.tipo_reporte} por {who} — {self.fecha_ejecucion:%Y-%m-%d %H:%M}"
