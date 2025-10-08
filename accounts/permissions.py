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
        return getattr(request.user, 'userType', None) == settings.USER_ROLE_EMPLOYER


