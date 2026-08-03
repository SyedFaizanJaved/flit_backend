from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from accounts.social import _make_pending_token
from candidates.models import Candidate

FAKE_PROFILE = {
    'email': 'social@example.com',
    'name': 'Social User',
    'avatar_url': 'https://example.com/a.png',
    'bio': 'bio',
    'location': 'Lahore',
    'website': 'https://me.dev',
    'github_url': 'https://github.com/social',
}


def fake_fetcher(profile=FAKE_PROFILE):
    return lambda code: dict(profile)


class SocialAuthTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # reset LoginRateThrottle counters between tests

    def url(self, provider='github'):
        return reverse('social-auth', kwargs={'provider': provider})

    def post(self, body, provider='github'):
        return self.client.post(self.url(provider), body, content_type='application/json')

    def test_invalid_provider(self):
        res = self.post({'code': 'x'}, provider='myspace')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['code'], 'invalid_provider')

    def test_missing_code(self):
        res = self.post({})
        self.assertEqual(res.json()['code'], 'exchange_failed')

    @patch.dict('accounts.social._PROFILE_FETCHERS', {'github': fake_fetcher()})
    def test_new_user_without_role_gets_pending_token(self):
        res = self.post({'code': 'ok'})
        data = res.json()
        self.assertTrue(data['needs_role'])
        self.assertIn('pending_token', data)
        self.assertEqual(data['social_profile']['email'], FAKE_PROFILE['email'])
        self.assertFalse(User.objects.filter(email=FAKE_PROFILE['email']).exists())

    @patch.dict('accounts.social._PROFILE_FETCHERS', {'github': fake_fetcher()})
    def test_new_user_with_role_created_verified_no_password(self):
        res = self.post({'code': 'ok', 'role': 'candidate'})
        data = res.json()
        self.assertTrue(data['is_new_user'])
        self.assertIn('access', data)
        user = User.objects.get(email=FAKE_PROFILE['email'])
        self.assertTrue(user.is_verified)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.role.name, 'candidate')
        self.assertTrue(Candidate.objects.filter(user=user).exists())

    def test_pending_token_completes_signup(self):
        token = _make_pending_token(FAKE_PROFILE)
        res = self.post({'pending_token': token, 'role': 'employer'})
        data = res.json()
        self.assertTrue(data['is_new_user'])
        user = User.objects.get(email=FAKE_PROFILE['email'])
        self.assertEqual(user.role.name, 'employer')

    def test_pending_token_invalid_role(self):
        token = _make_pending_token(FAKE_PROFILE)
        res = self.post({'pending_token': token, 'role': 'admin'})
        self.assertEqual(res.json()['code'], 'invalid_role')

    def test_expired_pending_token(self):
        token = jwt.encode({
            'purpose': 'social_signup', 'profile': FAKE_PROFILE,
            'exp': datetime.now(timezone.utc) - timedelta(minutes=1),
        }, settings.SECRET_KEY, algorithm='HS256')
        res = self.post({'pending_token': token, 'role': 'candidate'})
        self.assertEqual(res.json()['code'], 'invalid_pending_token')

    @patch.dict('accounts.social._PROFILE_FETCHERS', {'github': fake_fetcher()})
    def test_existing_user_logs_in_no_duplicate(self):
        role, _ = Role.objects.get_or_create(name='candidate')
        user = User.objects.create_user(
            email=FAKE_PROFILE['email'], username='existing',
            password='Str0ng!pass', role=role, is_verified=False)
        res = self.post({'code': 'ok'})
        data = res.json()
        self.assertFalse(data['is_new_user'])
        self.assertIn('access', data)
        self.assertEqual(User.objects.filter(email__iexact=FAKE_PROFILE['email']).count(), 1)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)  # auto-verified: provider attests the email
        self.assertTrue(user.has_usable_password())  # password login still works

    @patch.dict('accounts.social._PROFILE_FETCHERS', {'github': fake_fetcher()})
    def test_disabled_user_rejected(self):
        User.objects.create_user(
            email=FAKE_PROFILE['email'], username='disabled',
            password='Str0ng!pass', is_active=False)
        res = self.post({'code': 'ok'})
        self.assertEqual(res.json()['code'], 'user_disabled')

    def test_pending_token_race_logs_in_existing(self):
        token = _make_pending_token(FAKE_PROFILE)
        User.objects.create_user(email=FAKE_PROFILE['email'], username='raced', password='Str0ng!pass')
        res = self.post({'pending_token': token, 'role': 'candidate'})
        data = res.json()
        self.assertFalse(data['is_new_user'])
        self.assertEqual(User.objects.filter(email__iexact=FAKE_PROFILE['email']).count(), 1)


class RefactorRegressionTests(TestCase):
    """Password register/login must behave identically after the services.py extraction."""

    def test_register_creates_candidate_profile(self):
        Role.objects.get_or_create(name='candidate')  # seeded by ops in real envs
        res = self.client.post(reverse('user-register'), {
            'email': 'reg@example.com', 'first_name': 'Reg', 'last_name': 'User',
            'password': 'Str0ng!pass123', 'password_confirm': 'Str0ng!pass123',
            'role': 'candidate',
        }, content_type='application/json')
        self.assertEqual(res.status_code, 201, res.content)
        user = User.objects.get(email='reg@example.com')
        self.assertTrue(Candidate.objects.filter(user=user).exists())
        self.assertFalse(user.is_verified)

    def test_login_response_shape(self):
        role, _ = Role.objects.get_or_create(name='candidate')
        user = User.objects.create_user(
            email='login@example.com', username='loginuser',
            password='Str0ng!pass123', role=role, is_verified=True)
        Candidate.objects.get_or_create(user=user, defaults={'full_name': 'L U', 'title': 'Dev'})
        res = self.client.post(reverse('user-login'), {
            'email': 'login@example.com', 'password': 'Str0ng!pass123',
        }, content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        for key in ('user', 'access', 'refresh', 'message', 'profile_completed', 'banner_seen'):
            self.assertIn(key, data)
        self.assertEqual(data['user']['email'], 'login@example.com')
