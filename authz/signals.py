from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from .models import AuditLog

def _client_meta(request):
    if request is None:
        return None, ""
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    return ip, ua

@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    ip, ua = _client_meta(request)
    AuditLog.objects.create(user=user, action="login_success", ip=ip, user_agent=ua, metadata={"signal": True})

@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    ip, ua = _client_meta(request)
    AuditLog.objects.create(user=user, action="logout", ip=ip, user_agent=ua, metadata={"signal": True})

@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    ip, ua = _client_meta(request)
    AuditLog.objects.create(user=None, action="login_failed", ip=ip, user_agent=ua, metadata={"username": credentials.get("username"), "signal": True})
