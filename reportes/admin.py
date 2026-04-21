from django.contrib import admin
from .models import LogReporte


@admin.register(LogReporte)
class LogReporteAdmin(admin.ModelAdmin):
    list_display = ["tipo_reporte", "usuario", "formato_exportacion", "fecha_ejecucion", "ip"]
    list_filter  = ["tipo_reporte", "formato_exportacion"]
    readonly_fields = [
        "tipo_reporte", "usuario", "filtros_aplicados",
        "formato_exportacion", "fecha_ejecucion", "ip",
    ]
    ordering = ["-fecha_ejecucion"]
