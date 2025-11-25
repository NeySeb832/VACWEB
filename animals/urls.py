# animals/urls.py
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

app_name = "animals"   # ← necesario para usar {% url 'animals:list' %}

urlpatterns = [
    # Lista de animales (tabla principal)
    path("", views.animal_list, name="list"),

    # Crear nuevo animal
    path("new/", views.animal_create, name="create"),

    # Detalle de un animal (ficha con datos + historial, que haremos luego)
    path("<int:pk>/", views.animal_detail, name="detail"),

    # Editar datos básicos del animal
    path("<int:pk>/edit/", views.animal_update, name="update"),

    # Baja lógica / cambio de estado (ej. ACT → INA) – opcionalmente con motivo
    path("<int:pk>/baja/", views.animal_baja, name="baja"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)