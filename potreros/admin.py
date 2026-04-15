# potreros/admin.py
from django.contrib import admin

from .models import Potrero


@admin.register(Potrero)
class PotreroAdmin(admin.ModelAdmin):
    list_display  = ["nombre_codigo", "tipo_uso", "estado", "capacidad_maxima", "area_ha", "created_at"]
    list_filter   = ["estado", "tipo_uso"]
    search_fields = ["nombre_codigo"]
    readonly_fields = ["created_at", "updated_at", "created_by"]
    list_per_page = 25
    ordering      = ["nombre_codigo"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
