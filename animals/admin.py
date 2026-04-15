from django.contrib import admin

from .models import Potrero, Animal, Movimiento
from eventos.models import EventoSanitario
from pesajes.models import Pesaje


# Potrero ahora gestionado en potreros/admin.py (CU-005)


class EventoSanitarioInline(admin.TabularInline):
    model = EventoSanitario
    extra = 0


class PesajeInline(admin.TabularInline):
    model = Pesaje
    extra = 0
    readonly_fields = ("fecha", "peso_kg", "variacion_kg", "promedio_diario_g", "responsable", "created_at")
    can_delete = False

    def has_change_permission(self, request, obj=None):
        return False


class MovimientoInline(admin.TabularInline):
    model = Movimiento
    fk_name = "animal"
    extra = 0


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    """CRUD de animales desde /admin."""

    list_display = (
        "__str__",
        "rfid",
        "arete",
        "sexo",
        "etapa",
        "raza",
        "potrero",
        "estado",
        "created_at",
    )
    list_filter = ("estado", "sexo", "etapa", "raza", "potrero")
    search_fields = ("rfid", "arete", "raza")
    autocomplete_fields = ("potrero", "last_modified_by")

    readonly_fields = ("created_at", "updated_at", "last_modified_by")

    fieldsets = (
        ("Identificación", {"fields": ("rfid", "arete", "foto")}),
        ("Características", {"fields": ("sexo", "etapa", "raza", "fecha_nacimiento", "potrero")}),
        ("Estado", {"fields": ("estado", "motivo_baja")}),
        ("Auditoría", {"fields": ("created_at", "updated_at", "last_modified_by")}),
    )

    inlines = [EventoSanitarioInline, PesajeInline, MovimientoInline]

    def save_model(self, request, obj, form, change):
        obj.last_modified_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ("animal", "desde", "hacia", "fecha", "responsable")
    list_filter = ("fecha", "hacia", "desde")
    search_fields = ("animal__rfid", "animal__arete", "responsable")
    autocomplete_fields = ("animal", "desde", "hacia")
