from django.urls import path
from . import views

app_name = "reportes"

urlpatterns = [
    path("",            views.reporte_index,           name="index"),
    path("inventario/", views.reporte_inventario,      name="inventario"),
    path("historial/",  views.reporte_historial_animal, name="historial"),
    path("sanitario/",  views.reporte_sanitario,       name="sanitario"),
    path("ventas/",     views.reporte_ventas,          name="ventas"),
]
