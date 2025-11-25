from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.conf import settings
from django.views.decorators.csrf import csrf_protect
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from .models import AuditLog
from .decorators import require_perm
from .utils import user_permission_codes

# --- Helpers de bloqueo por intentos (RN-1)
def _login_keys(username: str, ip: str):
    base = f"{(username or '').lower()}:{ip or '0.0.0.0'}"
    return (f"authz:login:attempts:{base}", f"authz:login:block:{base}")

def _is_blocked(username: str, ip: str) -> bool:
    _, k_block = _login_keys(username, ip)
    return cache.get(k_block) is not None

def _register_failed(username: str, ip: str):
    k_attempts, k_block = _login_keys(username, ip)
    attempts = cache.get(k_attempts, 0) + 1
    cache.set(k_attempts, attempts, timeout=60 * settings.AUTHZ_LOGIN_BLOCK_MINUTES)
    if attempts >= settings.AUTHZ_LOGIN_MAX_ATTEMPTS:
        cache.set(k_block, 1, timeout=60 * settings.AUTHZ_LOGIN_BLOCK_MINUTES)

def _clear_counters(username: str, ip: str):
    k_attempts, k_block = _login_keys(username, ip)
    cache.delete(k_attempts)
    cache.delete(k_block)

class LoginAnonThrottle(AnonRateThrottle):
    scope = "anon"

@csrf_protect
def login_view(request):
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password")

        # Anti-enumeración + RN-1 bloqueo
        if _is_blocked(username, ip):
            AuditLog.objects.create(user=None, action="login_blocked", ip=ip, user_agent=ua, metadata={"username": username})
            # Mensaje genérico (no revela si existe la cuenta)
            return render(request, "auth/login.html", {"error": "No fue posible iniciar sesión. Intente más tarde."})

        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            login(request, user)
            _clear_counters(username, ip)
            AuditLog.objects.create(user=user, action="login_success", ip=ip, user_agent=ua)
            return redirect("animals:list")
        else:
            _register_failed(username, ip)
            AuditLog.objects.create(user=None, action="login_failed", ip=ip, user_agent=ua, metadata={"username": username})
            # Mensaje genérico para evitar enumeración
            return render(request, "auth/login.html", {"error": "Credenciales inválidas o acceso temporalmente restringido."})

    return render(request, "auth/login.html", {})

@login_required
def logout_view(request):
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    AuditLog.objects.create(user=request.user, action="logout", ip=ip, user_agent=ua)
    logout(request)
    return redirect("/login/")

# --- API (útil para SPA/PWA en fases posteriores)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginAnonThrottle])
def api_login(request):
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password")

    if _is_blocked(username, ip):
        AuditLog.objects.create(user=None, action="login_blocked", ip=ip, user_agent=ua, metadata={"username": username, "api": True})
        return Response({"detail": "No fue posible iniciar sesión. Intente más tarde."}, status=429)

    user = authenticate(request, username=username, password=password)
    if user is not None and user.is_active:
        login(request, user)
        _clear_counters(username, ip)
        AuditLog.objects.create(user=user, action="login_success", ip=ip, user_agent=ua, metadata={"api": True})
        return Response({"detail": "ok"})
    else:
        _register_failed(username, ip)
        AuditLog.objects.create(user=None, action="login_failed", ip=ip, user_agent=ua, metadata={"username": username, "api": True})
        return Response({"detail": "Credenciales inválidas o acceso temporalmente restringido."}, status=401)

@api_view(["POST"])
def api_logout(request):
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    AuditLog.objects.create(user=request.user, action="logout", ip=ip, user_agent=ua, metadata={"api": True})
    logout(request)
    return Response({"detail": "ok"})

@api_view(["GET"])
def api_me(request):
    user = request.user
    return Response({
        "username": user.username,
        "email": user.email,
        "roles": [ur.role.code for ur in user.userrole_set.select_related("role")],
        "permissions": sorted(list(user_permission_codes(user))),
    })

# Vista demo para validar permisos CU/acción (deny by default)
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
@require_perm("animals.read")
def demo_secure_view(request):
    return JsonResponse({"detail": "OK: tienes animals.read"})
