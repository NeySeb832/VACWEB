from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import (
    PasswordResetView, PasswordResetConfirmView,
)
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from .models import AuditLog, Role, Permission, RolePermission, UserRole, UserProfile, UserInvitation
from .decorators import require_perm
from .utils import user_permission_codes
from .forms import UserCreateForm, UserInviteForm, InvitationSetPasswordForm, UserEditForm, PasswordSetForm, RoleForm

# --- Helper: revocación de sesiones activas (CU-001 CP-12, RN-2)
def _revoke_user_sessions(user):
    """Invalida todas las sesiones activas del usuario. Cumple CP-12."""
    from django.contrib.sessions.models import Session
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    for session in sessions:
        data = session.get_decoded()
        if data.get("_auth_user_id") == str(user.pk):
            session.delete()


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
        identifier = (request.POST.get("username") or "").strip()
        password = request.POST.get("password")

        # Si el identificador parece un email, busca el username real
        if "@" in identifier:
            try:
                username = User.objects.get(email__iexact=identifier).username
            except User.DoesNotExist:
                username = identifier  # fallará en authenticate → mensaje genérico
        else:
            username = identifier

        # Anti-enumeración + RN-1 bloqueo
        if _is_blocked(identifier, ip):
            AuditLog.objects.create(user=None, action="login_blocked", ip=ip, user_agent=ua, metadata={"username": identifier})
            # Mensaje genérico (no revela si existe la cuenta)
            return render(request, "auth/login.html", {"error": "No fue posible iniciar sesión. Intente más tarde."})

        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active:
            login(request, user)
            _clear_counters(identifier, ip)
            AuditLog.objects.create(user=user, action="login_success", ip=ip, user_agent=ua)
            return redirect("animals:list")
        else:
            _register_failed(identifier, ip)
            AuditLog.objects.create(user=None, action="login_failed", ip=ip, user_agent=ua, metadata={"username": identifier})
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
        "now":       timezone.now(),
    }
    return render(request, "auth/user_list.html", ctx)


def _has_code(user, code: str) -> bool:
    from .utils import has_perm_code
    return has_perm_code(user, code)


@login_required
@require_perm("users.write")
def user_create(request):
    """CU-001 CP-08: Crear usuario y enviar invitación por email (RN-9)."""
    if request.method == "POST":
        form = UserInviteForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_unusable_password()   # El usuario define su contraseña al activar
                user.is_active = False          # Pendiente activación
                user.save()
                # Perfil
                profile = _ensure_profile(user)
                profile.phone = form.cleaned_data.get("phone", "")
                profile.save(update_fields=["phone"])
                # Rol
                role = form.cleaned_data.get("role")
                if role:
                    UserRole.objects.create(user=user, role=role)
                # Generar token de invitación (RN-9)
                expiry_hours = getattr(settings, "AUTHZ_INVITE_EXPIRY_HOURS", 24)
                invitation = UserInvitation.create_for_user(user, hours=expiry_hours)
                activate_url = request.build_absolute_uri(
                    reverse("authz:invitation_activate", args=[invitation.token])
                )
                # Enviar email (en dev queda en consola)
                if user.email:
                    send_mail(
                        subject="Invitación a GanaderoPro — Activa tu cuenta",
                        message=(
                            f"Hola {user.get_full_name() or user.username},\n\n"
                            f"Fuiste invitado al sistema GanaderoPro.\n"
                            f"Activa tu cuenta aquí:\n{activate_url}\n\n"
                            f"El enlace expira en {expiry_hours} horas.\n"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                # Auditoría
                AuditLog.objects.create(
                    user=request.user,
                    action="user.invite_sent",
                    ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    metadata={
                        "invited_user": user.username,
                        "email": user.email,
                        "expires_at": invitation.expires_at.isoformat(),
                    },
                )
            messages.success(
                request,
                f"Invitación enviada a «{user.username}». "
                f"El enlace expira en {getattr(settings, 'AUTHZ_INVITE_EXPIRY_HOURS', 24)} horas."
            )
            return redirect("authz:user_list")
    else:
        form = UserInviteForm()
    return render(request, "auth/user_form.html", {
        "form": form,
        "is_create": True,
        "invite_hours": getattr(settings, "AUTHZ_INVITE_EXPIRY_HOURS", 24),
    })


def invitation_activate(request, token: str):
    """CU-001 CP-09/CP-10: Activación de cuenta por enlace de invitación."""
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]

    try:
        invitation = UserInvitation.objects.select_related("user").get(token=token)
    except UserInvitation.DoesNotExist:
        return render(request, "auth/invitation_activate.html", {
            "error": "El enlace no es válido o ya no existe."
        })

    # CP-10: enlace expirado o ya usado
    if not invitation.is_valid():
        return render(request, "auth/invitation_activate.html", {
            "error": "Este enlace ha expirado o ya fue utilizado.",
            "expired": True,
        })

    if request.method == "POST":
        form = InvitationSetPasswordForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = invitation.user
                user.set_password(form.cleaned_data["password"])
                user.is_active = True
                user.save(update_fields=["password", "is_active"])
                invitation.used = True
                invitation.used_at = timezone.now()
                invitation.save(update_fields=["used", "used_at"])
                AuditLog.objects.create(
                    user=user,
                    action="user.activated",
                    ip=ip,
                    user_agent=ua,
                    metadata={"via": "invitation"},
                )
            return render(request, "auth/invitation_activate.html", {
                "success": True,
                "username": invitation.user.username,
            })
    else:
        form = InvitationSetPasswordForm()

    return render(request, "auth/invitation_activate.html", {
        "form": form,
        "invitation": invitation,
    })


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
                # Actualizar rol (reemplaza el anterior) — RN-8
                new_role = form.cleaned_data.get("role")
                UserRole.objects.filter(user=user_saved).delete()
                if new_role:
                    UserRole.objects.create(user=user_saved, role=new_role)
                # Auditoría con delta de rol (RN-4)
                AuditLog.objects.create(
                    user=request.user,
                    action="user.edit",
                    ip=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                    metadata={
                        "edited_user": user_saved.username,
                        "rol_anterior": current_role.code if current_role else None,
                        "rol_nuevo": new_role.code if new_role else None,
                    },
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

    desactivando = edited_user.is_active  # True si lo estamos desactivando
    edited_user.is_active = not edited_user.is_active
    edited_user.save(update_fields=["is_active"])
    accion = "activado" if edited_user.is_active else "desactivado"

    # CP-12: revocar sesiones activas si se desactivó el usuario
    if desactivando:
        _revoke_user_sessions(edited_user)

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
    # CP-12: revocar todas las sesiones activas del usuario eliminado
    _revoke_user_sessions(edited_user)
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


# ===========================================================================
# CU-001 CP-05: Recuperación de contraseña con auditoría (RN-4)
# ===========================================================================

class AuditedPasswordResetView(PasswordResetView):
    """Extiende la vista de Django para auditar solicitudes de recuperación."""
    template_name = "auth/password_reset_form.html"

    def form_valid(self, form):
        email = form.cleaned_data.get("email", "")
        ip = self.request.META.get("REMOTE_ADDR")
        ua = self.request.META.get("HTTP_USER_AGENT", "")[:255]
        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            user = None  # Anti-enumeración: se responde igual aunque no exista
        AuditLog.objects.create(
            user=user,
            action="password_reset.requested",
            ip=ip,
            user_agent=ua,
            metadata={"email": email},
        )
        return super().form_valid(form)


class AuditedPasswordResetConfirmView(PasswordResetConfirmView):
    """Extiende la vista de Django para auditar el cambio de contraseña."""
    template_name = "auth/password_reset_confirm.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        ip = self.request.META.get("REMOTE_ADDR")
        ua = self.request.META.get("HTTP_USER_AGENT", "")[:255]
        AuditLog.objects.create(
            user=user,
            action="password_reset.completed",
            ip=ip,
            user_agent=ua,
        )
        return response
