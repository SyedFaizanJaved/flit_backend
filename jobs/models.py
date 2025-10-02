from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Job(models.Model):
    """
    Job posting model
    """
    JOB_TYPE_CHOICES = [
        ('full-time', 'Full-time'),
        ('part-time', 'Part-time'),
        ('contract', 'Contract'),
        ('freelance', 'Freelance'),
        ('internship', 'Internship'),
    ]
    
    WORK_STYLE_CHOICES = [
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('in-person', 'In-Person'),
    ]
    
    EDUCATION_LEVEL_CHOICES = [
        ('high-school', 'High School'),
        ('associate', 'Associate'),
        ('bachelor', 'Bachelor'),
        ('master', 'Master'),
        ('phd', 'PhD'),
        ('none', 'None'),
    ]
    
    SKILL_LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]
    
    SALARY_PERIOD_CHOICES = [
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('closed', 'Closed'),
        ('filled', 'Filled'),
    ]
    
    EXPERIENCE_LEVEL_CHOICES = [
        ('entry', 'Entry'),
        ('mid', 'Mid'),
        ('senior', 'Senior'),
        ('lead', 'Lead'),
        ('executive', 'Executive'),
    ]
    
    # Basic Information
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=2000)
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='jobs')
    employer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posted_jobs')
    
    # Job Details (matching JobPostingFields)
    location = models.CharField(max_length=200, blank=True, null=True)
    workStyle = models.CharField(max_length=20, choices=WORK_STYLE_CHOICES, default='remote')
    category = models.CharField(max_length=100, choices=[
        ('engineering', 'Engineering'),
        ('design', 'Design'),
        ('marketing', 'Marketing'),
        ('sales', 'Sales'),
        ('operations', 'Operations'),
        ('other', 'Other'),
    ])
    skills = models.JSONField(default=list)  # List of required skills
    experienceLevel = models.CharField(max_length=20, choices=EXPERIENCE_LEVEL_CHOICES)
    employmentType = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES)
    hasTemporaryOption = models.BooleanField(default=False)
    temporaryDuration = models.CharField(max_length=100, blank=True, null=True)
    
    # Salary Information
    salaryRangeMin = models.PositiveIntegerField(blank=True, null=True)
    salaryRangeMax = models.PositiveIntegerField(blank=True, null=True)
    salary_currency = models.CharField(max_length=3, default='USD')
    salary_period = models.CharField(max_length=20, choices=SALARY_PERIOD_CHOICES, default='yearly')
    is_salary_negotiable = models.BooleanField(default=True)
    
    # Benefits and Perks
    benefits = models.JSONField(default=list)  # List of benefits

 
    # Application Process
    applicationDeadline = models.DateTimeField(blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    is_urgent = models.BooleanField(default=False)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Matching Criteria
    skill_match_threshold = models.PositiveIntegerField(default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])
    experience_weight = models.PositiveIntegerField(default=30, validators=[MinValueValidator(0), MaxValueValidator(100)])
    education_weight = models.PositiveIntegerField(default=20, validators=[MinValueValidator(0), MaxValueValidator(100)])
    location_weight = models.PositiveIntegerField(default=10, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Tags for search
    tags = models.JSONField(default=list)  # List of tags
    
    # SEO
    slug = models.SlugField(unique=True, blank=True)
    
    # Statistics
    views_count = models.PositiveIntegerField(default=0)
    applications_count = models.PositiveIntegerField(default=0)
    shortlisted_count = models.PositiveIntegerField(default=0)
    hired_count = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'jobs'
        verbose_name = 'Job'
        verbose_name_plural = 'Jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['location', 'workStyle']),
        ]
    
    def __str__(self):
        return f"{self.title} at {self.company.company_name}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(f"{self.title}-{self.company.company_name}")
        super().save(*args, **kwargs)


class JobSkill(models.Model):
    """
    Required skills for jobs
    """
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='required_skills')
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=20, choices=Job.SKILL_LEVEL_CHOICES, default='intermediate')
    is_required = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'job_skills'
        verbose_name = 'Job Skill'
        verbose_name_plural = 'Job Skills'
        unique_together = ['job', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.level}) for {self.job.title}"


class JobLanguage(models.Model):
    """
    Required languages for jobs
    """
    LANGUAGE_PROFICIENCY_CHOICES = [
        ('basic', 'Basic'),
        ('conversational', 'Conversational'),
        ('fluent', 'Fluent'),
        ('native', 'Native'),
    ]
    
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='required_languages')
    name = models.CharField(max_length=100)
    proficiency = models.CharField(max_length=20, choices=LANGUAGE_PROFICIENCY_CHOICES, default='conversational')
    
    class Meta:
        db_table = 'job_languages'
        verbose_name = 'Job Language'
        verbose_name_plural = 'Job Languages'
        unique_together = ['job', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.proficiency}) for {self.job.title}"
