from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.conf import settings


class IsEmployer(BasePermission):
    """
    Allows access only to users with employer role for unsafe methods.
    Safe methods (GET, HEAD, OPTIONS) are allowed for any authenticated user.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        role_name = getattr(getattr(user, 'role', None), 'name', None)
        is_employer = role_name == getattr(settings, 'USER_ROLE_EMPLOYER', 'employer')
        is_admin = getattr(user, 'is_staff', False) or role_name == getattr(settings, 'USER_ROLE_ADMIN', 'admin')
        has_employer_profile = hasattr(user, 'employer_profile')
        return bool(is_employer or is_admin or has_employer_profile)


