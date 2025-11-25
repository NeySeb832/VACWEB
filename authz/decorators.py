from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from .utils import has_perm_code

def require_perm(code: str):
    """
    Uso:
    @login_required
    @require_perm("animals.read")
    def vista(request): ...
    """
    def outer(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return HttpResponseForbidden("No autenticado.")
            if not has_perm_code(request.user, code):
                return HttpResponseForbidden("Permiso insuficiente.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return outer
