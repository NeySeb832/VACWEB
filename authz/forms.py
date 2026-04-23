# authz/forms.py
"""Formularios del módulo de gestión de usuarios y roles (CU-001)."""

import re

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import Permission, Role, UserProfile

_TEXTO  = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_CHECK  = {"class": "form-check-input"}


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

class UserCreateForm(forms.ModelForm):
    """CU-001: Crear un nuevo usuario con asignación de rol y contraseña."""

    password = forms.CharField(
        label="Contraseña",
        min_length=8,
        widget=forms.PasswordInput(attrs={**_TEXTO, "autocomplete": "new-password"}),
        help_text="Mínimo 8 caracteres, al menos 1 mayúscula y 1 número (RN-5).",
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={**_TEXTO, "autocomplete": "new-password"}),
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.all().order_by("name"),
        required=False,
        label="Rol",
        empty_label="Sin rol asignado",
        widget=forms.Select(attrs=_SELECT),
    )
    phone = forms.CharField(
        required=False,
        label="Teléfono",
        max_length=32,
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Opcional"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs={**_TEXTO, "placeholder": "Nombres"}),
            "last_name":  forms.TextInput(attrs={**_TEXTO, "placeholder": "Apellidos"}),
            "username":   forms.TextInput(attrs={**_TEXTO, "placeholder": "usuario"}),
            "email":      forms.EmailInput(attrs={**_TEXTO, "placeholder": "correo@ejemplo.com"}),
            "is_active":  forms.CheckboxInput(attrs=_CHECK),
        }

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        # CU-001 RN-1
        if not re.match(r'^[\w\-]{3,30}$', username):
            raise forms.ValidationError(
                "El nombre de usuario debe tener entre 3 y 30 caracteres "
                "(letras, dígitos, guiones y guiones bajos)."
            )
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya está en uso.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("Este correo electrónico ya está registrado.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")
        return cleaned


class UserEditForm(forms.ModelForm):
    """CU-001: Editar datos de un usuario existente (sin cambio de contraseña)."""

    role = forms.ModelChoiceField(
        queryset=Role.objects.all().order_by("name"),
        required=False,
        label="Rol",
        empty_label="Sin rol asignado",
        widget=forms.Select(attrs=_SELECT),
    )
    phone = forms.CharField(
        required=False,
        label="Teléfono",
        max_length=32,
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Opcional"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs=_TEXTO),
            "last_name":  forms.TextInput(attrs=_TEXTO),
            "username":   forms.TextInput(attrs=_TEXTO),
            "email":      forms.EmailInput(attrs=_TEXTO),
            "is_active":  forms.CheckboxInput(attrs=_CHECK),
        }

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not re.match(r'^[\w\-]{3,30}$', username):
            raise forms.ValidationError(
                "El nombre de usuario debe tener entre 3 y 30 caracteres "
                "(letras, dígitos, guiones y guiones bajos)."
            )
        qs = User.objects.filter(username=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Este nombre de usuario ya está en uso.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email:
            qs = User.objects.filter(email=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Este correo ya está registrado en otro usuario.")
        return email


class PasswordSetForm(forms.Form):
    """CU-001: Asignar una nueva contraseña a un usuario."""

    password = forms.CharField(
        label="Nueva contraseña",
        min_length=8,
        widget=forms.PasswordInput(attrs={**_TEXTO, "autocomplete": "new-password"}),
        help_text="Mínimo 8 caracteres, al menos 1 mayúscula y 1 número.",
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={**_TEXTO, "autocomplete": "new-password"}),
    )

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")
        return cleaned


class UserInviteForm(forms.ModelForm):
    """CU-001 CP-08: Crear usuario por invitación (sin contraseña; el usuario la define al activar)."""

    role = forms.ModelChoiceField(
        queryset=Role.objects.all().order_by("name"),
        required=False,
        label="Rol",
        empty_label="Sin rol asignado",
        widget=forms.Select(attrs=_SELECT),
    )
    phone = forms.CharField(
        required=False,
        label="Teléfono",
        max_length=32,
        widget=forms.TextInput(attrs={**_TEXTO, "placeholder": "Opcional"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={**_TEXTO, "placeholder": "Nombres"}),
            "last_name":  forms.TextInput(attrs={**_TEXTO, "placeholder": "Apellidos"}),
            "username":   forms.TextInput(attrs={**_TEXTO, "placeholder": "usuario"}),
            "email":      forms.EmailInput(attrs={**_TEXTO, "placeholder": "correo@ejemplo.com"}),
        }

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not re.match(r'^[\w\-]{3,30}$', username):
            raise forms.ValidationError(
                "El nombre de usuario debe tener entre 3 y 30 caracteres "
                "(letras, dígitos, guiones y guiones bajos)."
            )
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya está en uso.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if not email:
            raise forms.ValidationError("El correo es obligatorio para enviar la invitación.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este correo electrónico ya está registrado.")
        return email


class InvitationSetPasswordForm(forms.Form):
    """CU-001 CP-09: El usuario define su contraseña al activar la cuenta por invitación."""

    password = forms.CharField(
        label="Contraseña",
        min_length=8,
        widget=forms.PasswordInput(attrs={**_TEXTO, "autocomplete": "new-password"}),
        help_text="Mínimo 8 caracteres (RN-5).",
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={**_TEXTO, "autocomplete": "new-password"}),
    )

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")
        return cleaned


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

class RoleForm(forms.ModelForm):
    """CU-001: Crear o editar un rol y asignar sus permisos."""

    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all().order_by("code"),
        required=False,
        label="Permisos asignados",
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = Role
        fields = ["name", "code"]
        widgets = {
            "name": forms.TextInput(attrs={**_TEXTO, "placeholder": "Ej: Veterinario"}),
            "code": forms.TextInput(
                attrs={**_TEXTO, "placeholder": "Ej: veterinario (sin espacios)"}
            ),
        }
        help_texts = {
            "code": "Identificador único del rol (minúsculas, sin espacios).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Precargar permisos actuales si estamos editando
        if self.instance.pk:
            self.fields["permissions"].initial = Permission.objects.filter(
                rolepermission__role=self.instance
            )

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().lower()
        qs = Role.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un rol con ese código.")
        return code
