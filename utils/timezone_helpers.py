"""
Timezone conversion utilities for converting datetime fields to user's timezone.
Uses the `timezone` field from the User model (default: America/New_York).
"""
import zoneinfo
from django.utils import timezone as dj_timezone


def convert_to_user_timezone(dt, user):
    """
    Convert a datetime object to the user's preferred timezone.
    
    Args:
        dt: A datetime object (timezone-aware or naive).
        user: A User model instance that has a `timezone` field.
    
    Returns:
        A timezone-aware datetime localized to the user's timezone,
        or None if dt is None.
    """
    if dt is None:
        return None
    
    user_tz = get_user_timezone(user)
    
    # If the datetime is naive, assume it's in UTC
    if dj_timezone.is_naive(dt):
        dt = dj_timezone.make_aware(dt, zoneinfo.ZoneInfo('UTC'))
    
    return dt.astimezone(user_tz)


def get_user_timezone(user):
    """
    Get the user's timezone as a ZoneInfo object.
    Falls back to America/New_York if not set.
    
    Args:
        user: A User model instance.
    
    Returns:
        A ZoneInfo timezone object.
    """
    if user and hasattr(user, 'user_timezone') and user.user_timezone:
        # django-timezone-field stores as ZoneInfo already
        return user.user_timezone
    return zoneinfo.ZoneInfo('America/New_York')


def format_datetime_for_user(dt, user, fmt=None):
    """
    Convert and format a datetime for the user's timezone.
    
    Args:
        dt: A datetime object.
        user: A User model instance.
        fmt: Optional strftime format string. If None, returns ISO format.
    
    Returns:
        A formatted datetime string in the user's timezone.
    """
    if dt is None:
        return None
    
    localized_dt = convert_to_user_timezone(dt, user)
    
    if fmt:
        return localized_dt.strftime(fmt)
    return localized_dt.isoformat()
