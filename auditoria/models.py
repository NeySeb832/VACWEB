"""
CU-010: Auditoría / Bitácora de Operaciones
Entidad central inmutable. No se permiten UPDATE ni DELETE sobre esta tabla.
Campos basados en el diseño físico del documento CU-010 (Sección 3).
"""
from django.conf import settings
from django.db import models


class Bitacora(models.Model):
    """Registro inmutable de una acción realizada en cualquier módulo del sistema."""

    class Accion(models.TextChoices):
        CREAR      = "CREAR",      "Crear"
        EDITAR     = "EDITAR",     "Editar"
        ELIMINAR   = "ELIMINAR",   "Eliminar"
        ACCEDER    = "ACCEDER",    "Acceder"
        ANULAR     = "ANULAR",     "Anular"
        CONFIGURAR = "CONFIGURAR", "Configurar"

    # ── Autoría ──────────────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="bitacora_entries",
        verbose_name="Usuario",
    )
    usuario_nombre = models.CharField(
        max_length=150, blank=True,
        verbose_name="Nombre del usuario",
        help_text="Snapshot del nombre en el momento del evento (RN-2 inmutabilidad).",
    )

    # ── Qué / Dónde ──────────────────────────────────────────────────────────
    accion = models.CharField(
        max_length=20, choices=Accion.choices,
        db_index=True,
        verbose_name="Acción",
    )
    entidad = models.CharField(
        max_length=100, db_index=True,
        verbose_name="Entidad afectada",
        help_text="Nombre del modelo: Animal, Potrero, Pesaje, etc.",
    )
    entidad_id = models.CharField(
        max_length=100, blank=True,
        verbose_name="ID de la entidad",
        help_text="PK polimórfica del registro afectado.",
    )
    modulo_origen = models.CharField(
        max_length=20, blank=True,
        verbose_name="Módulo origen",
        help_text="CU-02, CU-03 … CU-09",
    )
    resumen = models.TextField(
        blank=True,
        verbose_name="Resumen",
        help_text="Descripción corta legible por humanos.",
    )

    # ── Delta (RN-4) ─────────────────────────────────────────────────────────
    valores_anteriores = models.JSONField(
        null=True, blank=True,
        verbose_name="Valores anteriores",
    )
    valores_nuevos = models.JSONField(
        null=True, blank=True,
        verbose_name="Valores nuevos",
    )

    # ── Cuándo / Desde dónde ─────────────────────────────────────────────────
    fecha = models.DateTimeField(
        auto_now_add=True, db_index=True,
        verbose_name="Fecha y hora",
    )
    ip_origen = models.GenericIPAddressField(
        null=True, blank=True,
        protocol="both", unpack_ipv4=True,
        verbose_name="IP de origen",
    )
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="User-Agent")

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Registro de bitácora"
        verbose_name_plural = "Registros de bitácora"
        indexes = [
            models.Index(fields=["user", "-fecha"]),
            models.Index(fields=["entidad", "-fecha"]),
            models.Index(fields=["accion", "-fecha"]),
        ]

    def __str__(self):
        return f"{self.fecha} | {self.accion} | {self.entidad}({self.entidad_id}) | {self.usuario_nombre}"

    # ── Inmutabilidad (RN-2) ─────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        """Bloquea actualizaciones: los registros de auditoría son de solo escritura."""
        if self.pk is not None:
            raise ValueError(
                "CU-010 RN-2: Los registros de auditoría son inmutables y no pueden modificarse."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Bloquea eliminaciones: los registros de auditoría son permanentes."""
        raise ValueError(
            "CU-010 RN-2: Los registros de auditoría son permanentes y no pueden eliminarse."
        )
