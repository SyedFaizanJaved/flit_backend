from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.conf import settings
from django.utils import timezone


class Employer(models.Model):
    """
    Employer profile model
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employer_profile')
    
    # Company Relation
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='employers', blank=True, null=True)
    
    # Basic Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to='employers/profile_pictures/', 
        blank=True, 
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif'])]
    )
    bio = models.TextField(max_length=500, blank=True, null=True)
    
    
    # Profile Completion Status
    basic_info_completed = models.BooleanField(default=False)
    company_info_completed = models.BooleanField(default=False)
    
    # Profile Visibility
    is_profile_public = models.BooleanField(default=True)
    banner_seen = models.BooleanField(default=True)
    
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
        return self.basic_info_completed and bool(self.company_id)


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


class CandidateAction(models.Model):
    """
    Model to track candidate actions (pass/reject) by employers
    """
    ACTION_CHOICES = [
        ('pass', 'Pass'),
        ('reject', 'Reject'),
    ]
    
    employer = models.ForeignKey(Employer, on_delete=models.CASCADE, related_name='candidate_actions')
    candidate_id = models.CharField(max_length=100)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'candidate_actions'
        verbose_name = 'Candidate Action'
        verbose_name_plural = 'Candidate Actions'
        ordering = ['-created_at']
        unique_together = ('employer', 'candidate_id')
    
    def __str__(self):
        return f"{self.employer} - {self.candidate_id} - {self.action}"
