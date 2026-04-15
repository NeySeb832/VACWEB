# potreros/urls.py
from django.urls import path
from . import views

app_name = "potreros"

urlpatterns = [
    path("",                    views.potreros_list,     name="list"),
    path("nuevo/",              views.potrero_create,    name="create"),
    path("<int:pk>/",           views.potrero_detail,    name="detail"),
    path("<int:pk>/editar/",    views.potrero_edit,      name="edit"),
    path("<int:pk>/desactivar/", views.potrero_deactivate, name="deactivate"),
]
