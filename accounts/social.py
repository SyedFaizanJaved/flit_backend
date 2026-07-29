"""Social sign-in: Google, Microsoft, GitHub, LinkedIn.

One endpoint (POST /api/auth/social/<provider>/) with two request shapes:
  {code, role?}            — exchange OAuth code; role only when known (register page)
  {pending_token, role}    — finish signup after the role picker
"""
import logging
from datetime import datetime, timedelta, timezone

import jwt
import requests
from django.conf import settings
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from accounts.models import Role, User
from accounts.services import build_auth_response, create_role_profile, generate_unique_username
from accounts.throttles import LoginRateThrottle

logger = logging.getLogger(__name__)

PROVIDERS = ('google', 'microsoft', 'github', 'linkedin')
PENDING_TOKEN_LIFETIME = timedelta(minutes=15)
REQUEST_TIMEOUT = 10


class SocialAuthError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _oauth_config(provider):
    cfg = settings.SOCIAL_OAUTH.get(provider, {})
    if not cfg.get('client_id') or not cfg.get('client_secret'):
        raise SocialAuthError('provider_not_configured', f'{provider} sign-in is not configured')
    return cfg


def _redirect_uri(provider):
    # Must exactly match the URI the SPA used on the authorize redirect.
    return f"{settings.FLIT_REQUEST_URL.rstrip('/')}/auth/callback/{provider}"


def _split_name(name, fallback_email):
    name = (name or '').strip() or fallback_email.split('@')[0]
    first, _, last = name.partition(' ')
    return first, last


def _google_profile(code):
    cfg = _oauth_config('google')
    resp = requests.post('https://oauth2.googleapis.com/token', data={
        'code': code,
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'redirect_uri': _redirect_uri('google'),
        'grant_type': 'authorization_code',
    }, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        logger.error('Google code exchange failed (%s): %s', resp.status_code, resp.text[:500])
        raise SocialAuthError('exchange_failed', 'Google code exchange failed')
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
    try:
        claims = google_id_token.verify_oauth2_token(
            resp.json()['id_token'], google_requests.Request(), cfg['client_id'])
    except Exception:
        raise SocialAuthError('exchange_failed', 'Google token verification failed')
    if not claims.get('email') or not claims.get('email_verified'):
        raise SocialAuthError('no_verified_email', 'Google account has no verified email')
    return {
        'email': claims['email'],
        'name': claims.get('name', ''),
        'avatar_url': claims.get('picture', ''),
    }


def _microsoft_profile(code):
    cfg = _oauth_config('microsoft')
    resp = requests.post('https://login.microsoftonline.com/common/oauth2/v2.0/token', data={
        'code': code,
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'redirect_uri': _redirect_uri('microsoft'),
        'grant_type': 'authorization_code',
        'scope': 'openid email profile',
    }, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        logger.error('Microsoft code exchange failed (%s): %s', resp.status_code, resp.text[:500])
        raise SocialAuthError('exchange_failed', 'Microsoft code exchange failed')
    tokens = resp.json()
    # id_token claims: signature already validated by Microsoft issuing it to our
    # client_secret over TLS; decode without verify like the codebase does elsewhere.
    claims = jwt.decode(tokens['id_token'], options={'verify_signature': False})
    email = claims.get('email')
    preferred = claims.get('preferred_username', '')
    # nOAuth hardening: hostile Entra tenants can set arbitrary `email` claims.
    # Accept only when the domain-owner-verified flag is set or email == login identifier.
    if not email or not (claims.get('xms_edov') or email.lower() == preferred.lower()):
        raise SocialAuthError('no_verified_email', 'Microsoft account has no verified email')
    return {
        'email': email,
        'name': claims.get('name', ''),
        'avatar_url': '',  # Graph photo needs an extra binary call; skipped in v1
    }


def _github_profile(code):
    cfg = _oauth_config('github')
    resp = requests.post('https://github.com/login/oauth/access_token', data={
        'code': code,
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'redirect_uri': _redirect_uri('github'),
    }, headers={'Accept': 'application/json'}, timeout=REQUEST_TIMEOUT)
    token = resp.json().get('access_token') if resp.status_code == 200 else None
    if not token:
        logger.error('GitHub code exchange failed (%s): %s', resp.status_code, resp.text[:500])
        raise SocialAuthError('exchange_failed', 'GitHub code exchange failed')
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    user = requests.get('https://api.github.com/user', headers=headers, timeout=REQUEST_TIMEOUT).json()
    emails = requests.get('https://api.github.com/user/emails', headers=headers, timeout=REQUEST_TIMEOUT).json()
    email = next((e['email'] for e in emails if isinstance(e, dict) and e.get('primary') and e.get('verified')), None)
    if not email:
        raise SocialAuthError('no_verified_email', 'GitHub account has no verified primary email')
    return {
        'email': email,
        'name': user.get('name') or user.get('login', ''),
        'avatar_url': user.get('avatar_url', ''),
        'bio': user.get('bio') or '',
        'location': user.get('location') or '',
        'website': user.get('blog') or '',
        'github_url': user.get('html_url', ''),
    }


def _linkedin_profile(code):
    cfg = _oauth_config('linkedin')
    resp = requests.post('https://www.linkedin.com/oauth/v2/accessToken', data={
        'code': code,
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'redirect_uri': _redirect_uri('linkedin'),
        'grant_type': 'authorization_code',
    }, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=REQUEST_TIMEOUT)
    token = resp.json().get('access_token') if resp.status_code == 200 else None
    if not token:
        logger.error('LinkedIn code exchange failed (%s): %s', resp.status_code, resp.text[:500])
        raise SocialAuthError('exchange_failed', 'LinkedIn code exchange failed')
    info = requests.get('https://api.linkedin.com/v2/userinfo',
                        headers={'Authorization': f'Bearer {token}'}, timeout=REQUEST_TIMEOUT).json()
    if not info.get('email') or not info.get('email_verified', True):
        raise SocialAuthError('no_verified_email', 'LinkedIn account has no verified email')
    return {
        'email': info['email'],
        'name': info.get('name', ''),
        'avatar_url': info.get('picture', ''),
        # OIDC userinfo exposes no public profile URL; linkedin_url stays empty in v1
    }


_PROFILE_FETCHERS = {
    'google': _google_profile,
    'microsoft': _microsoft_profile,
    'github': _github_profile,
    'linkedin': _linkedin_profile,
}


def _social_profile(profile):
    """Normalized prefill payload sent to the frontend."""
    return {
        'name': profile.get('name', ''),
        'email': profile['email'],
        'avatar_url': profile.get('avatar_url', ''),
        'bio': profile.get('bio', ''),
        'location': profile.get('location', ''),
        'website': profile.get('website', ''),
        'github_url': profile.get('github_url', ''),
        'linkedin_url': profile.get('linkedin_url', ''),
    }


def _make_pending_token(profile):
    return jwt.encode({
        'purpose': 'social_signup',
        'profile': profile,
        'exp': datetime.now(timezone.utc) + PENDING_TOKEN_LIFETIME,
    }, settings.SECRET_KEY, algorithm='HS256')


def _decode_pending_token(token):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    except jwt.PyJWTError:
        raise SocialAuthError('invalid_pending_token', 'Signup session expired, please sign in again')
    if payload.get('purpose') != 'social_signup':
        raise SocialAuthError('invalid_pending_token', 'Invalid signup token')
    return payload['profile']


def _create_social_user(profile, role_name):
    if role_name not in (getattr(settings, 'USER_ROLE_CANDIDATE', 'candidate'),
                         getattr(settings, 'USER_ROLE_EMPLOYER', 'employer')):
        raise SocialAuthError('invalid_role', 'Role must be candidate or employer')
    role, _ = Role.objects.get_or_create(name=role_name)
    first_name, last_name = _split_name(profile.get('name'), profile['email'])
    user = User.objects.create_user(
        email=profile['email'],
        username=generate_unique_username(profile['email']),
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_verified=True,  # the provider verified the email
    )
    user.set_unusable_password()
    user.save(update_fields=['password'])
    create_role_profile(user)
    return user


def _login_existing(user, social_profile):
    if not user.is_active:
        raise SocialAuthError('user_disabled', 'This account has been disabled')
    if not user.is_verified:
        # Provider attests the email; lift the pending email-verification gate.
        user.is_verified = True
        user.save(update_fields=['is_verified'])
    return build_auth_response(user, is_new_user=False, social_profile=social_profile)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def social_providers(request):
    """Public client IDs per provider (never secrets) — lets the SPA build
    authorize URLs without needing its own env configuration."""
    return Response({
        p: {'client_id': settings.SOCIAL_OAUTH[p]['client_id']}
        for p in PROVIDERS if settings.SOCIAL_OAUTH[p]['client_id']
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([LoginRateThrottle])
def social_auth(request, provider):
    if provider not in PROVIDERS:
        return Response({'detail': 'Unknown provider', 'code': 'invalid_provider'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        pending_token = request.data.get('pending_token')
        role_name = request.data.get('role')

        if pending_token:
            profile = _decode_pending_token(pending_token)
            existing = User.objects.filter(email__iexact=profile['email']).first()
            if existing:
                # Account appeared during the role-picker window — just log it in.
                return Response(_login_existing(existing, _social_profile(profile)))
            user = _create_social_user(profile, role_name)
            return Response(build_auth_response(user, is_new_user=True,
                                                social_profile=_social_profile(profile)))

        code = request.data.get('code')
        if not code:
            return Response({'detail': 'code is required', 'code': 'exchange_failed'},
                            status=status.HTTP_400_BAD_REQUEST)
        profile = _PROFILE_FETCHERS[provider](code)
        social_profile = _social_profile(profile)

        existing = User.objects.filter(email__iexact=profile['email']).first()
        if existing:
            return Response(_login_existing(existing, social_profile))
        if role_name:
            user = _create_social_user(profile, role_name)
            return Response(build_auth_response(user, is_new_user=True,
                                                social_profile=social_profile))
        return Response({
            'needs_role': True,
            'pending_token': _make_pending_token(profile),
            'social_profile': social_profile,
        })
    except SocialAuthError as e:
        return Response({'detail': e.detail, 'code': e.code}, status=status.HTTP_400_BAD_REQUEST)
    except requests.RequestException:
        logger.exception('Social auth provider request failed (%s)', provider)
        return Response({'detail': 'Provider request failed', 'code': 'exchange_failed'},
                        status=status.HTTP_400_BAD_REQUEST)
