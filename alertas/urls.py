from django.urls import path
from . import views

app_name = "alertas"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("detalle/<uuid:id_alerta>/", views.detalle_view, name="detalle"),
    path("atender/<uuid:id_alerta>/", views.atender_view, name="atender"),
    path("configuracion/", views.configuracion_view, name="configuracion"),
    path("api/pendientes/", views.api_alertas_pendientes, name="api_pendientes"),
    path("api/atender/<uuid:id_alerta>/", views.api_atender, name="api_atender"),
]
