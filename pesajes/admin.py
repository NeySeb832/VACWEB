# pesajes/admin.py
from django.contrib import admin

from .models import Pesaje


@admin.register(Pesaje)
class PesajeAdmin(admin.ModelAdmin):
    """CU-004: Gestión de pesajes desde /admin.
    RN-3: los pesajes son inmutables, por lo que no se permite edición.
    """

    list_display = (
        "animal",
        "fecha",
        "peso_kg",
        "variacion_kg",
        "promedio_diario_g",
        "responsable",
        "created_at",
    )
    list_filter = ("fecha",)
    search_fields = ("animal__rfid", "animal__arete", "responsable")
    autocomplete_fields = ("animal",)
    readonly_fields = (
        "variacion_kg",
        "promedio_diario_g",
        "created_by",
        "created_at",
    )

    fieldsets = (
        ("Animal", {"fields": ("animal",)}),
        (
            "Pesaje",
            {
                "fields": (
                    "fecha",
                    "peso_kg",
                    "responsable",
                    "observaciones",
                    "foto_bascula",
                )
            },
        ),
        (
            "Calculados (RN-6)",
            {
                "fields": ("variacion_kg", "promedio_diario_g"),
                "description": "Valores calculados automáticamente al guardar.",
            },
        ),
        ("Auditoría", {"fields": ("created_by", "created_at")}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        # RN-3: inmutabilidad — no se permite editar pesajes existentes
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # RN-5: sin eliminaciones físicas
        return False
