# pesajes/urls.py
from django.urls import path

from . import views

app_name = "pesajes"

urlpatterns = [
    path("", views.pesaje_list, name="list"),
    path("new/", views.pesaje_create, name="create"),
    path("<int:pk>/", views.pesaje_detail, name="detail"),
]
