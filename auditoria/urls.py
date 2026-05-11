from django.urls import path
from auditoria import views

app_name = "auditoria"

urlpatterns = [
    path("",              views.index,        name="index"),
    path("<int:pk>/",     views.detalle,      name="detalle"),
    path("exportar/csv/", views.exportar_csv, name="exportar_csv"),
]
