from django.urls import path
from . import views

urlpatterns = [
    # HTML
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # API
    path("api/auth/login", views.api_login, name="api_login"),
    path("api/auth/logout", views.api_logout, name="api_logout"),
    path("api/auth/me", views.api_me, name="api_me"),
    # Demo permiso (para validar decorador)
    path("demo/secure", views.demo_secure_view, name="demo_secure"),
]
