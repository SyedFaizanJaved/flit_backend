from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings


class Employer(models.Model):
    """
    Employer profile model
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employer_profile')
    
    # Basic Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='employers/profile_pictures/', blank=True, null=True)
    bio = models.TextField(max_length=500, blank=True, null=True)
    
    # Company Information (from EmployerProfileFields)
    companyName = models.CharField(max_length=200, blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    size = models.CharField(max_length=20, blank=True, null=True, choices=[
        ('startup', 'Startup'),
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('enterprise', 'Enterprise'),
    ])
    values = models.JSONField(default=list)  # List of company values
    logoImage = models.ImageField(upload_to='employers/company_logos/', blank=True, null=True)
    
    # Profile Completion Status
    basic_info_completed = models.BooleanField(default=False)
    company_info_completed = models.BooleanField(default=False)
    
    # Profile Visibility
    is_profile_public = models.BooleanField(default=True)
    
    # Statistics
    total_jobs_posted = models.PositiveIntegerField(default=0)
    total_projects_posted = models.PositiveIntegerField(default=0)
    total_applications_received = models.PositiveIntegerField(default=0)
    total_hires = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'employers'
        verbose_name = 'Employer'
        verbose_name_plural = 'Employers'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_profile_complete(self):
        return self.basic_info_completed and self.company_info_completed


class EmployerPreference(models.Model):
    """
    Preferences and settings for employers
    """
    employer = models.OneToOneField(Employer, on_delete=models.CASCADE, related_name='preferences')
    
    # Notification Settings
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    
    # Auto Matching Settings
    auto_matching = models.BooleanField(default=True)
    skill_match_threshold = models.PositiveIntegerField(default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])
    experience_required = models.BooleanField(default=True)
    location_preference = models.CharField(
        max_length=20,
        choices=[
            ('any', 'Any'),
            ('local', 'Local'),
            ('remote', 'Remote'),
            ('hybrid', 'Hybrid'),
        ],
        default='any'
    )
    
    class Meta:
        db_table = 'employer_preferences'
        verbose_name = 'Employer Preference'
        verbose_name_plural = 'Employer Preferences'
    
    def __str__(self):
        return f"Preferences for {self.employer.full_name}"


class EmployerCompliance(models.Model):
    """
    Compliance information for employers
    """
    employer = models.OneToOneField(Employer, on_delete=models.CASCADE, related_name='compliance')
    companySize = models.PositiveIntegerField(blank=True, null=True)
    isFederalContractor = models.BooleanField(default=False)
    primaryState = models.CharField(max_length=100, blank=True, null=True)
    additionalStates = models.JSONField(default=list)  # List of additional states
    eeoStatement = models.TextField(blank=True, null=True)
    autoScanEnabled = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'employer_compliance'
        verbose_name = 'Employer Compliance'
        verbose_name_plural = 'Employer Compliance Records'
    
    def __str__(self):
        return f"Compliance for {self.employer.full_name}"
