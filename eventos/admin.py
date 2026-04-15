# eventos/admin.py
from django.contrib import admin

from .models import EventoSanitario


@admin.register(EventoSanitario)
class EventoSanitarioAdmin(admin.ModelAdmin):
    """CU-003: Gestión de eventos sanitarios desde /admin.

    RN-3: eventos en estado CANCELADO o REALIZADO son inmutables.
    """

    list_display = (
        "animal",
        "tipo",
        "fecha",
        "responsable",
        "producto",
        "estado",
        "es_correccion",
        "created_at",
    )
    list_filter = ("estado", "tipo", "fecha")
    search_fields = ("animal__rfid", "animal__arete", "tipo", "responsable", "producto", "lote")
    autocomplete_fields = ("animal",)
    readonly_fields = ("created_by", "created_at", "evento_original")

    fieldsets = (
        ("Animal", {"fields": ("animal",)}),
        (
            "Evento",
            {
                "fields": (
                    "tipo",
                    "fecha",
                    "responsable",
                    "producto",
                    "dosis",
                    "lote",
                    "via_aplicacion",
                    "notas",
                )
            },
        ),
        ("Estado", {"fields": ("estado", "evento_original")}),
        ("Auditoría", {"fields": ("created_by", "created_at")}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        # RN-3: bloquear edición si el evento está en estado terminal
        if obj is not None and obj.estado in EventoSanitario.ESTADOS_TERMINALES:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        # Si el evento ya existe y está en estado mutable, el campo estado
        # solo puede tomar valores de transición válidos (se restringe en el form)
        if obj and obj.estado in EventoSanitario.ESTADOS_TERMINALES:
            # Objeto terminal: todo es readonly (has_change_permission ya lo bloquea,
            # pero esto añade protección visual)
            readonly += ["tipo", "fecha", "responsable", "producto", "dosis",
                         "lote", "via_aplicacion", "notas", "estado", "animal"]
        return readonly

    @admin.display(boolean=True, description="Es corrección")
    def es_correccion(self, obj):
        return obj.es_correccion
