from django.contrib import admin
from .models import Transaccion


@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display   = ["id", "tipo", "animal", "fecha", "valor_cop", "estado", "created_by"]
    list_filter    = ["tipo", "estado", "fecha"]
    search_fields  = ["animal__rfid", "animal__arete", "origen_destino"]
    readonly_fields = ["created_at", "fecha_anulacion", "anulado_por"]
