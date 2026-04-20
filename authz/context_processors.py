# authz/context_processors.py
from .utils import user_permission_codes


def user_perms(request):
    """Inyecta el conjunto de códigos de permiso del usuario en todos los templates."""
    if request.user.is_authenticated:
        return {"user_perms": user_permission_codes(request.user)}
    return {"user_perms": set()}
