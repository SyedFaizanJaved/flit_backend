"""Shared auth helpers used by password registration/login and social sign-in."""
import logging
import re

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)


def generate_unique_username(email):
    """Derive an available alphanumeric username from an email address."""
    from accounts.models import User

    base_username = re.sub(r'[^a-zA-Z0-9]', '', email.split('@')[0]) or 'user'
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    return username


def create_role_profile(user):
    """Create the Candidate/Employer row matching the user's role.

    Mirrors registration behavior: failures never block user creation.
    """
    user_role = user.role.name if user.role_id else None
    try:
        if user_role == getattr(settings, 'USER_ROLE_CANDIDATE', 'candidate'):
            # Lazy import to avoid circular deps at import time
            from candidates.models import Candidate
            full_name = f"{user.first_name} {user.last_name}".strip() or user.get_short_name()
            # Title is required at model level (blank not allowed). Use a safe default.
            Candidate.objects.get_or_create(
                user=user,
                defaults={
                    'full_name': full_name or user.email.split('@')[0],
                    'title': 'Candidate',
                }
            )
        elif user_role == getattr(settings, 'USER_ROLE_EMPLOYER', 'employer'):
            from employers.models import Employer
            Employer.objects.get_or_create(
                user=user,
                defaults={
                    'first_name': user.first_name or user.get_short_name(),
                    'last_name': user.last_name or '',
                }
            )
    except Exception:
        # Do not block user creation if profile creation fails
        pass


def build_auth_response(user, **extra):
    """JWTs + user payload + profile_completed/banner_seen — the login response body."""
    from accounts.serializers import UserProfileSerializer
    from candidates.models import Candidate
    from companies.models import Company
    from employers.models import Employer

    refresh = RefreshToken.for_user(user)
    user_role = getattr(getattr(user, 'role', None), 'name', None)
    profile_completed = False
    employer_company_completed = False
    banner_seen = False
    try:
        # Fast path: if employer profile exists and is linked to a company, treat as completed
        if hasattr(user, 'employer_profile') and getattr(user.employer_profile, 'company_id', None):
            employer_company_completed = True
        else:
            # Fallback: check completed companies created by the user
            employer_company_completed = Company.objects.filter(
                created_by=user, is_active=True, is_completed=True
            ).exists()
    except Exception as e:
        logger.exception(e)
        employer_company_completed = Company.objects.filter(
            created_by=user, is_active=True, is_completed=True
        ).exists()

    if user_role == getattr(settings, 'USER_ROLE_EMPLOYER', 'employer') or (user_role is None and employer_company_completed):
        profile_completed = employer_company_completed
        try:
            employer_profile = user.employer_profile
            banner_seen = employer_profile.banner_seen
        except Employer.DoesNotExist:
            logger.error('Employer.DoesNotExist: Employer profile does not exist')
    elif user_role == getattr(settings, 'USER_ROLE_CANDIDATE', 'candidate') or (user_role is None and hasattr(user, 'candidate_profile')):
        try:
            candidate_profile = user.candidate_profile
            profile_completed = candidate_profile.is_profile_complete
            banner_seen = candidate_profile.banner_seen
        except Candidate.DoesNotExist:
            logger.error('Candidate.DoesNotExist: Candidate profile does not exist')
            profile_completed = False

    # Persist the latest computed state on the user for quick access elsewhere
    if user.profile_completed != profile_completed:
        user.profile_completed = profile_completed
        user.save(update_fields=['profile_completed'])

    return {
        'user': UserProfileSerializer(user).data,
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'message': 'Login successful',
        'profile_completed': profile_completed,
        'banner_seen': banner_seen,
        **extra,
    }
