# transacciones/urls.py
from django.urls import path
from . import views

app_name = "transacciones"

urlpatterns = [
    path("",                         views.transaccion_list,             name="list"),
    path("nueva/",                   views.transaccion_create,           name="create"),
    path("<int:pk>/",                views.transaccion_detail,           name="detail"),
    path("<int:pk>/anular/",         views.transaccion_anular,           name="anular"),
    path("animal/<int:animal_pk>/historial/",
                                     views.transaccion_historial_animal, name="historial_animal"),
]
