from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
from utils.file_validators import company_logo_upload_path, company_gallery_upload_path


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

    WORK_MODE_CHOICES = [
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('onsite', 'On-site'),
    ]
    
    # Basic Information
    company_name = models.CharField(max_length=200, blank=False)
    description = models.TextField(max_length=2000, blank=False)
    industry = models.CharField(max_length=100, blank=False)
    size = models.CharField(max_length=30, choices=SIZE_CHOICES, blank=False)
    website = models.URLField(blank=True, null=True)
    logo = models.ImageField(
        upload_to=company_logo_upload_path, 
        blank=True, 
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif'])]
    )
    location = models.CharField(max_length=500, blank=False)
    values = models.JSONField(default=list) 
    
    # Enhanced Branding Fields
    founded_year = models.DateField(blank=True, null=True)
    culture = models.TextField(blank=True, help_text="Describe the company culture")
    benefits = models.TextField(blank=True, help_text="List key benefits and perks")
    social_links = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="{'linkedin': 'url', 'twitter': 'url', ...}"
    )
    work_mode = models.CharField(
        max_length=20, 
        choices=WORK_MODE_CHOICES, 
        default='onsite',
        blank=True
    )
    
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


class CompanyImage(models.Model):
    """
    Gallery images for company (office, team, etc.)
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to=company_gallery_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])]
    )
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_images'
        ordering = ['order', '-created_at']
        verbose_name = 'Company Image'
        verbose_name_plural = 'Company Images'

    def __str__(self):
        return f"Image for {self.company.company_name}"


class CompanyMilestone(models.Model):
    """
    Company history milestones
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='milestones')
    year = models.DateField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_milestones'
        ordering = ['-year']
        verbose_name = 'Company Milestone'
        verbose_name_plural = 'Company Milestones'

    def __str__(self):
        return f"{self.year} - {self.title} ({self.company.company_name})"