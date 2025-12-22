from django.db import models
from django.conf import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError


class CustomURLValidator(URLValidator):
    def __call__(self, value):
        if not value:
            return
            
        # Add https:// if no protocol is specified
        if not (value.startswith('http://') or value.startswith('https://')):
            value = 'https://' + value
            
        # Ensure www. is present for non-localhost URLs
        parsed_url = value.split('://')
        if len(parsed_url) > 1 and not parsed_url[1].startswith('www.') and not parsed_url[1].startswith('localhost'):
            value = f"{parsed_url[0]}://www.{parsed_url[1]}"
            
        try:
            super().__call__(value)
        except ValidationError:
            raise ValidationError('Enter a valid URL (e.g., https://example.com or www.example.com)')


class Company(models.Model):
    """
    Company model for employers
    """
    SIZE_CHOICES = [
        ('1-10', '1-10'),
        ('11-50', '11-50'),
        ('51-200', '51-200'),
        ('201-500', '201-500'),
        ('501-1000', '501-1000'),
    ]
    
    # Basic Information
    company_name = models.CharField(max_length=200, blank=False)
    description = models.TextField(max_length=2000, blank=False)
    industry = models.CharField(max_length=100, blank=False)
    size = models.CharField(max_length=30, choices=SIZE_CHOICES, blank=False)
    # founded = models.PositiveIntegerField(blank=True, null=True)
    website = models.CharField(max_length=200, blank=True, null=True, validators=[CustomURLValidator()])
    logo = models.ImageField(upload_to='companies/logos/', blank=True, null=True)
    location = models.CharField(max_length=500, blank=False)
    values = models.JSONField(default=list) 
    
    # Ownership and Status
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_companies')
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Completion flag to indicate whether employer finished registering company
    is_completed = models.BooleanField(default=False)
    
    # Statistics
    total_jobs = models.PositiveIntegerField(default=0)
    total_projects = models.PositiveIntegerField(default=0)
    total_hires = models.PositiveIntegerField(default=0)
    total_employees = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'companies'
        verbose_name = 'Company'
        verbose_name_plural = 'Companies'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.company_name
    
    @property
    def full_address(self):
        return self.location 

    @property
    def name(self):
        return self.company_name