from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from .models import AuditLog, Role, Permission, RolePermission, UserRole, UserProfile
from .decorators import require_perm
from .utils import user_permission_codes
from .forms import UserCreateForm, UserEditForm, PasswordSetForm, RoleForm

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
@login_required
@require_perm("animals.read")
def demo_secure_view(request):
    return JsonResponse({"detail": "OK: tienes animals.read"})


# ===========================================================================
# CU-001: Gestión de Usuarios
# ===========================================================================

def _ensure_profile(user):
    """Devuelve (o crea) el UserProfile del usuario."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@login_required
@require_perm("users.read")
def user_list(request):
    """CU-001: Listado de usuarios con filtros."""
    qs = User.objects.select_related("profile").order_by("username")

    q      = request.GET.get("q", "").strip()
    role_f = request.GET.get("role", "").strip()
    activo = request.GET.get("activo", "").strip()
    solo_activos = request.GET.get("excluir_eliminados", "1")

    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q)
            | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if role_f:
        qs = qs.filter(userrole__role_id=role_f)
    if activo == "1":
        qs = qs.filter(is_active=True)
    elif activo == "0":
        qs = qs.filter(is_active=False)
    # Excluir eliminados lógicamente por defecto
    if solo_activos != "0":
        qs = qs.exclude(profile__is_deleted=True)

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj":  page_obj,
        "total":     paginator.count,
        "q":         q,
        "role_f":    role_f,
        "activo":    activo,
        "roles":     Role.objects.all().order_by("name"),
        "puede_escribir": request.user.has_perm("users.write") or _has_code(request.user, "users.write"),
    }
    return render(request, "auth/user_list.html", ctx)


def _has_code(user, code: str) -> bool:
    from .utils import has_perm_code
    return has_perm_code(user, code)


@login_required
@require_perm("users.write")
def user_create(request):
    """CU-001: Crear un nuevo usuario."""
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data["password"])
                user.save()
                # Perfil
                profile = _ensure_profile(user)
                profile.phone = form.cleaned_data.get("phone", "")
                profile.save(update_fields=["phone"])
                # Rol
                role = form.cleaned_data.get("role")
                if role:
                    UserRole.objects.create(user=user, role=role)
                # Auditoría
                AuditLog.objects.create(
                    user=request.user,
                    action="user.create",
                    ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    metadata={"created_user": user.username},
                )
            messages.success(request, f"Usuario «{user.username}» creado correctamente.")
            return redirect("authz:user_list")
    else:
        form = UserCreateForm()
    return render(request, "auth/user_form.html", {"form": form, "is_create": True})


@login_required
@require_perm("users.write")
def user_edit(request, pk: int):
    """CU-001: Editar datos de un usuario existente."""
    edited_user = get_object_or_404(User, pk=pk)
    profile     = _ensure_profile(edited_user)

    # Rol actual
    current_role_qs = UserRole.objects.filter(user=edited_user).select_related("role")
    current_role = current_role_qs.first().role if current_role_qs.exists() else None

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=edited_user)
        form.fields["role"].initial  = current_role
        form.fields["phone"].initial = profile.phone
        if form.is_valid():
            with transaction.atomic():
                user_saved = form.save()
                # Teléfono
                profile.phone = form.cleaned_data.get("phone", "")
                profile.save(update_fields=["phone"])
                # Actualizar rol (reemplaza el anterior)
                new_role = form.cleaned_data.get("role")
                UserRole.objects.filter(user=user_saved).delete()
                if new_role:
                    UserRole.objects.create(user=user_saved, role=new_role)
                # Auditoría
                AuditLog.objects.create(
                    user=request.user,
                    action="user.edit",
                    ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    metadata={"edited_user": user_saved.username},
                )
            messages.success(request, "Datos del usuario actualizados correctamente.")
            return redirect("authz:user_list")
    else:
        form = UserEditForm(instance=edited_user, initial={
            "role":  current_role,
            "phone": profile.phone,
        })

    return render(request, "auth/user_form.html", {
        "form":        form,
        "is_create":   False,
        "edited_user": edited_user,
    })


@login_required
@require_perm("users.write")
def user_password_set(request, pk: int):
    """CU-001: Asignar nueva contraseña a un usuario."""
    edited_user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        form = PasswordSetForm(request.POST)
        if form.is_valid():
            edited_user.set_password(form.cleaned_data["password"])
            edited_user.save(update_fields=["password"])
            AuditLog.objects.create(
                user=request.user,
                action="user.password_set",
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                metadata={"edited_user": edited_user.username},
            )
            messages.success(request, "Contraseña actualizada correctamente.")
            return redirect("authz:user_list")
    else:
        form = PasswordSetForm()

    return render(request, "auth/user_password_form.html", {
        "form": form, "edited_user": edited_user
    })


@login_required
@require_perm("users.write")
@require_POST
def user_toggle_active(request, pk: int):
    """CU-001: Activar / desactivar un usuario."""
    edited_user = get_object_or_404(User, pk=pk)

    # RN-5: no se puede desactivar el último admin activo
    if edited_user.is_active and edited_user.is_superuser:
        otros_admins = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=pk)
        if not otros_admins.exists():
            messages.error(request, "No se puede desactivar el único administrador activo (RN-5).")
            return redirect("authz:user_list")

    edited_user.is_active = not edited_user.is_active
    edited_user.save(update_fields=["is_active"])
    accion = "activado" if edited_user.is_active else "desactivado"
    AuditLog.objects.create(
        user=request.user,
        action="user.toggle_active",
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        metadata={"edited_user": edited_user.username, "is_active": edited_user.is_active},
    )
    messages.success(request, f"Usuario «{edited_user.username}» {accion}.")
    return redirect("authz:user_list")


@login_required
@require_perm("users.delete")
@require_POST
def user_soft_delete(request, pk: int):
    """CU-001 RN-7: Baja lógica de un usuario (nunca física)."""
    edited_user = get_object_or_404(User, pk=pk)

    # No eliminar a uno mismo
    if edited_user.pk == request.user.pk:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
        return redirect("authz:user_list")

    # RN-5: no eliminar el último admin activo
    if edited_user.is_superuser:
        otros_admins = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=pk)
        if not otros_admins.exists():
            messages.error(request, "No se puede eliminar el único administrador activo (RN-5).")
            return redirect("authz:user_list")

    profile = _ensure_profile(edited_user)
    profile.soft_delete(by_user=request.user)
    AuditLog.objects.create(
        user=request.user,
        action="user.soft_delete",
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        metadata={"deleted_user": edited_user.username},
    )
    messages.success(request, f"Usuario «{edited_user.username}» eliminado (baja lógica).")
    return redirect("authz:user_list")


# ===========================================================================
# CU-001: Gestión de Roles
# ===========================================================================

@login_required
@require_perm("roles.read")
def role_list(request):
    """CU-001: Listado de roles con sus permisos."""
    roles = Role.objects.prefetch_related(
        "rolepermission_set__permission"
    ).order_by("name")

    ctx = {
        "roles":          roles,
        "puede_escribir": _has_code(request.user, "roles.write"),
    }
    return render(request, "auth/role_list.html", ctx)


@login_required
@require_perm("roles.write")
def role_create(request):
    """CU-001: Crear un nuevo rol con permisos."""
    if request.method == "POST":
        form = RoleForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                role = form.save()
                # Asignar permisos seleccionados
                perms = form.cleaned_data.get("permissions", [])
                for perm in perms:
                    RolePermission.objects.get_or_create(role=role, permission=perm)
                AuditLog.objects.create(
                    user=request.user,
                    action="role.create",
                    ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    metadata={"role": role.code},
                )
            messages.success(request, f"Rol «{role.name}» creado correctamente.")
            return redirect("authz:role_list")
    else:
        form = RoleForm()

    return render(request, "auth/role_form.html", {"form": form, "is_create": True})


@login_required
@require_perm("roles.write")
def role_edit(request, pk: int):
    """CU-001: Editar un rol y sus permisos."""
    role = get_object_or_404(Role, pk=pk)

    if request.method == "POST":
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            with transaction.atomic():
                role = form.save()
                # Reemplazar permisos completamente
                RolePermission.objects.filter(role=role).delete()
                for perm in form.cleaned_data.get("permissions", []):
                    RolePermission.objects.create(role=role, permission=perm)
                AuditLog.objects.create(
                    user=request.user,
                    action="role.edit",
                    ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    metadata={"role": role.code},
                )
            messages.success(request, f"Rol «{role.name}» actualizado.")
            return redirect("authz:role_list")
    else:
        form = RoleForm(instance=role)

    return render(request, "auth/role_form.html", {
        "form": form, "is_create": False, "role": role
    })
