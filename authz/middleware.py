from .models import AuditLog

class Log403Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resp = self.get_response(request)
        if resp.status_code == 403:
            ip = request.META.get("REMOTE_ADDR")
            ua = request.META.get("HTTP_USER_AGENT", "")[:255]
            user = getattr(request, "user", None)
            AuditLog.objects.create(
                user=user if (user and user.is_authenticated) else None,
                action="forbidden_403",
                ip=ip,
                user_agent=ua,
                metadata={"path": request.path},
            )
        return resp
