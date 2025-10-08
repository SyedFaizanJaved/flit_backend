from django.db import models
from django.conf import settings


class Company(models.Model):
    """
    Company model for employers
    """
    SIZE_CHOICES = [
        ('startup', 'Startup'),
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('enterprise', 'Enterprise'),
    ]
    
    WORK_STYLE_CHOICES = [
        ('remote', 'Remote'),
        ('office', 'Office'),
        ('hybrid', 'Hybrid'),
    ]
    
    WORK_LIFE_BALANCE_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('average', 'Average'),
        ('poor', 'Poor'),
    ]
    
    # Basic Information
    company_name = models.CharField(max_length=200)
    description = models.TextField(max_length=1000, blank=True, null=True)
    industry = models.CharField(max_length=100)
    size = models.CharField(max_length=20, choices=SIZE_CHOICES)
    founded = models.PositiveIntegerField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='companies/logos/', blank=True, null=True)
    
    # Contact Information
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    address_street = models.CharField(max_length=200, blank=True, null=True)
    address_city = models.CharField(max_length=100, blank=True, null=True)
    address_state = models.CharField(max_length=100, blank=True, null=True)
    address_country = models.CharField(max_length=100, blank=True, null=True)
    address_zip_code = models.CharField(max_length=20, blank=True, null=True)
    
    # Social Media
    linkedin_url = models.URLField(blank=True, null=True)
    twitter_url = models.URLField(blank=True, null=True)
    facebook_url = models.URLField(blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)
    
    # Company Details
    mission = models.TextField(max_length=500, blank=True, null=True)
    vision = models.TextField(max_length=500, blank=True, null=True)
    values = models.JSONField(default=list)  # List of company values
    
    # Company Culture
    work_style = models.CharField(max_length=20, choices=WORK_STYLE_CHOICES, default='office')
    benefits = models.JSONField(default=list)  # List of benefits
    perks = models.JSONField(default=list)  # List of perks
    work_life_balance = models.CharField(max_length=20, choices=WORK_LIFE_BALANCE_CHOICES, default='good')
    
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
        address_parts = [
            self.address_street,
            self.address_city,
            self.address_state,
            self.address_country,
            self.address_zip_code
        ]
        return ', '.join(filter(None, address_parts))

    # Backward compatibility for old attribute access
    @property
    def name(self):
        return self.company_name

    def save(self, *args, **kwargs):
        # Defensive: ensure is_completed is never NULL at DB level
        if self.is_completed is None:
            # If a company is being created and flag wasn't provided, assume completed
            self.is_completed = True
        super().save(*args, **kwargs)
