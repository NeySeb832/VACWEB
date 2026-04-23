from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render
from authz.views import AuditedPasswordResetView, AuditedPasswordResetConfirmView


# ── Handlers globales de error ─────────────────────────────────────────────
def handler400(request, exception=None):
    return render(request, "400.html", status=400)

def handler403(request, exception=None):
    return render(request, "403.html", {"exception": exception}, status=403)

def handler404(request, exception=None):
    return render(request, "404.html", {"request_path": request.path}, status=404)

def handler500(request):
    return render(request, "500.html", status=500)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("", include("authz.urls", namespace="authz")),

    # Flujo de restablecimiento de contraseña con auditoría (CU-001 CP-05, RN-4)
    path("password_reset/", AuditedPasswordResetView.as_view(), name="password_reset"),
    path("password_reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="auth/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", AuditedPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="auth/password_reset_complete.html"), name="password_reset_complete"),
    path("animals/", include("animals.urls")),
    path("eventos/", include("eventos.urls")),
    path("pesajes/", include("pesajes.urls")),
    path("potreros/", include("potreros.urls")),
    path("transacciones/", include("transacciones.urls", namespace="transacciones")),
    path("reportes/",      include("reportes.urls",      namespace="reportes")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # URLs de demostración de páginas de error (solo en desarrollo)
    urlpatterns += [
        path("demo/error/403/", lambda r: render(r, "403.html", {"exception": "Permiso insuficiente: requieres animals.write"}, status=403)),
        path("demo/error/404/", lambda r: render(r, "404.html", {"request_path": r.path}, status=404)),
        path("demo/error/500/", lambda r: render(r, "500.html", status=500)),
        path("demo/error/400/", lambda r: render(r, "400.html", status=400)),
    ]