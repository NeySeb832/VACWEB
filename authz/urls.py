from django.urls import path
from . import views

app_name = "authz"

urlpatterns = [
    # ── Autenticación ──────────────────────────────────────────────────────
    path("login/",  views.login_view,  name="login"),
    path("logout/", views.logout_view, name="logout"),

    # ── API ────────────────────────────────────────────────────────────────
    path("api/auth/login",  views.api_login,  name="api_login"),
    path("api/auth/logout", views.api_logout, name="api_logout"),
    path("api/auth/me",     views.api_me,     name="api_me"),

    # ── Demo ───────────────────────────────────────────────────────────────
    path("demo/secure", views.demo_secure_view, name="demo_secure"),

    # ── CU-001: Usuarios ───────────────────────────────────────────────────
    path("usuarios/",                         views.user_list,            name="user_list"),
    path("usuarios/nuevo/",                   views.user_create,          name="user_create"),
    path("usuarios/activar/<str:token>/",     views.invitation_activate,  name="invitation_activate"),
    path("usuarios/<int:pk>/editar/",         views.user_edit,            name="user_edit"),
    path("usuarios/<int:pk>/password/",       views.user_password_set,    name="user_password_set"),
    path("usuarios/<int:pk>/toggle/",         views.user_toggle_active,   name="user_toggle_active"),
    path("usuarios/<int:pk>/eliminar/",       views.user_soft_delete,     name="user_soft_delete"),

    # ── CU-001: Roles ──────────────────────────────────────────────────────
    path("roles/",                views.role_list,   name="role_list"),
    path("roles/nuevo/",          views.role_create, name="role_create"),
    path("roles/<int:pk>/editar/", views.role_edit,  name="role_edit"),
]
