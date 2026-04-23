import secrets

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Permission(models.Model):
    code = models.CharField(max_length=150, unique=True)  # p. ej. "animals.read"
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.code

class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("role", "permission")

class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "role")

class UserProfile(models.Model):
    """CU-001 RN-7: Perfil extendido con baja lógica. Nunca se elimina físicamente."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=32, blank=True)
    # Baja lógica
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deleted_profiles"
    )

    def __str__(self):
        return f"Perfil de {self.user.username}"

    def soft_delete(self, by_user):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = by_user
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])
        # También desactivar el User de Django
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])


class UserInvitation(models.Model):
    """CU-001 RN-9: Token de invitación con expiración para activación de cuenta."""
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name="invitation")
    token      = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used       = models.BooleanField(default=False)
    used_at    = models.DateTimeField(null=True, blank=True)

    def is_valid(self) -> bool:
        return not self.used and timezone.now() < self.expires_at

    @classmethod
    def create_for_user(cls, user, hours: int = 24):
        """Genera (o reemplaza) el token de invitación para el usuario."""
        token = secrets.token_urlsafe(32)
        expires = timezone.now() + timezone.timedelta(hours=hours)
        # Si ya existía uno previo (reenvío), se elimina
        cls.objects.filter(user=user).delete()
        return cls.objects.create(user=user, token=token, expires_at=expires)

    def __str__(self):
        return f"Invitation for {self.user.username} (valid={self.is_valid()})"


class AuditLog(models.Model):
    # CU-001: RN-4 Auditoría obligatoria
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)  # login_success, login_failed, login_blocked, logout, forbidden_403
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        who = self.user.username if self.user else "anon"
        return f"{self.action} by {who} at {self.created_at}"
