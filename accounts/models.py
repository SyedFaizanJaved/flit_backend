from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.crypto import get_random_string


class User(AbstractUser):
    """
    Custom User model with role-based access control
    """
    ROLE_CHOICES = [
        (settings.USER_ROLE_CANDIDATE, 'Candidate'),
        (settings.USER_ROLE_EMPLOYER, 'Employer'),
    ]
    
    email = models.EmailField(unique=True)
    userType = models.CharField(max_length=20, choices=ROLE_CHOICES, db_column='role')
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    profile_completed = models.BooleanField(default=False)
    last_login = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'userType']
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"({self.email} - {self.userType})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]
    
    @property
    def role(self):
        """Backward compatibility"""
        return self.userType


class PasswordReset(models.Model):
    """
    Stores password reset requests with a short-lived token.
    """
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='password_resets')
    email = models.EmailField()
    reset_token = models.TextField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'password_resets'
        indexes = [
            models.Index(fields=['reset_token']),
            models.Index(fields=['email']),
        ]

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=['used_at'])

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @staticmethod
    def generate_token():
        return get_random_string(48)