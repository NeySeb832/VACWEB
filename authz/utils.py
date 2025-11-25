from .models import RolePermission

def user_permission_codes(user):
    if not user.is_authenticated:
        return set()
    perms = set()
    for ur in user.userrole_set.select_related("role"):
        for rp in RolePermission.objects.filter(role=ur.role).select_related("permission"):
            perms.add(rp.permission.code)
    return perms

def has_perm_code(user, code: str) -> bool:
    return code in user_permission_codes(user)
