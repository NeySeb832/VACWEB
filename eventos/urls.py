from django.urls import path

from . import views

app_name = "eventos"

urlpatterns = [
    path("", views.evento_list, name="list"),
    path("new/", views.evento_create, name="create"),
    path("<int:pk>/", views.evento_detail, name="detail"),
    path("<int:pk>/correccion/", views.evento_correccion, name="correccion"),
    path("<int:pk>/cancelar/", views.evento_cancelar, name="cancelar"),
    path("<int:pk>/realizar/", views.evento_realizar, name="realizar"),
]
