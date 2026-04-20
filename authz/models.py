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
