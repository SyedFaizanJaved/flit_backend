from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta
from timezone_field import TimeZoneField
from utils.currency_choices import CURRENCY_CHOICES


def get_default_deadline():
    return timezone.now().date() + timedelta(days=30)


class ProjectQuerySet(models.QuerySet):
    """Single definition of whether a project is still accepting applications.

    A project is OPEN when it is active and its deadline day has not yet ended.
    The deadline day is inclusive and evaluated against the current UTC date, so a
    project with a 10 Aug deadline stays open for all of 10 Aug and closes at
    00:00 UTC on 11 Aug.

    `deadline` is the field the UI labels "Application Deadline"; the separate
    `application_deadline` column is unused by the product. `deadline` is a
    DateField with a default, so it is never null -- unlike Job.applicationDeadline.

    `open()` and `expired()` are exact complements within status='active', and
    everything reads through them so the live filter and the stored status can
    never disagree.
    """

    def open(self):
        return self.filter(status='active').exclude(
            deadline__lt=timezone.now().date()
        )

    def expired(self):
        return self.filter(status='active', deadline__lt=timezone.now().date())


class Project(models.Model):
    """
    Project posting model
    """
    PROJECT_TYPE_CHOICES = [
        ('fixed', 'Fixed Price'),
        ('hourly', 'Hourly'),
    ]
    
    COMPLEXITY_CHOICES = [
        ('simple', 'Simple'),
        ('moderate', 'Moderate'),
        ('complex', 'Complex'),
        ('expert', 'Expert'),
    ]
    
    WORK_STYLE_CHOICES = [
        ('remote', 'Remote'),
        ('in-person', 'In-Person'),
        ('hybrid', 'Hybrid'),
    ]
    
    COLLABORATION_CHOICES = [
        ('independent', 'Independent'),
        ('team', 'Team'),
        ('client-involved', 'Client Involved'),
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
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('closed', 'Closed'),
        ('in-progress', 'In Progress'),
        ('completed', 'Completed')
    ]
    
    # Basic Information
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=2000, default='')
    # Nullable: see the matching note on Job.company.
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='projects', blank=True, null=True)
    employer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posted_projects')
    project_timezone = TimeZoneField(default='America/New_York', help_text="Timezone for this project posting")
    
    # Project Details (matching ProjectFields)
    category = models.CharField(max_length=100, choices=[
        ('engineering', 'Engineering'),
        ('design', 'Design'),
        ('marketing', 'Marketing'),
        ('sales', 'Sales'),
        ('operations', 'Operations'),
        ('writing', 'Writing'),
        ('technology/Digital', 'Technology/Digital'),
        ('creative/media', 'Creative/Media'),
        ('business/finance', 'Business/Finance'),
        ('trades/labour', 'Trades/Labour'),
        ('healthcare & welness', 'Healthcare & Wellness'),
        ('education & training', 'Education & Training'),
        ('hospitality & services', 'Hospitality & Services'),
        ('nonprofit/community work', 'Nonprofit/Community Work'),
        ('other', 'Other'),
    ])
    skills = models.JSONField(default=list)  # List of required skills
    paymentType = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES)
    paymentAmount = models.PositiveIntegerField()
    payment_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    estimatedHours = models.CharField(max_length=100)  # As text field as per schema
    hasTemporaryOption = models.BooleanField(default=False)
    temporaryDuration = models.CharField(max_length=100, blank=True, null=True)
    
    # Additional Project Details
    complexity = models.CharField(max_length=20, choices=COMPLEXITY_CHOICES, default='moderate')
    
    # Budget and Timeline
    budget_min = models.PositiveIntegerField(blank=True, null=True)
    budget_max = models.PositiveIntegerField(blank=True, null=True)
    budget_currency = models.CharField(max_length=3, default='USD')
    is_budget_negotiable = models.BooleanField(default=True)
    
    # Timeline
    duration_days = models.PositiveIntegerField(blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    deadline = models.DateField(default=get_default_deadline)
    is_timeline_flexible = models.BooleanField(default=False)
    
    # Requirements
    experience_min_years = models.PositiveIntegerField(default=0)
    experience_max_years = models.PositiveIntegerField(blank=True, null=True)
    education_level = models.CharField(max_length=20, choices=EDUCATION_LEVEL_CHOICES, default='bachelor')
    education_fields = models.JSONField(default=list)  # List of preferred education fields
    
    # Project Scope
    deliverables = models.JSONField(default=list)  # List of deliverables
    tools = models.JSONField(default=list)  # List of required tools
    technologies = models.JSONField(default=list)  # List of required technologies
    
    # Work Arrangement
    work_style = models.CharField(max_length=20, choices=WORK_STYLE_CHOICES, default='remote')
    collaboration = models.CharField(max_length=20, choices=COLLABORATION_CHOICES, default='independent')
    
    # Application Process
    application_deadline = models.DateTimeField(blank=True, null=True)
    max_applicants = models.PositiveIntegerField(default=50)
    is_urgent = models.BooleanField(default=False)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Matching Criteria
    skill_match_threshold = models.PositiveIntegerField(default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])
    experience_weight = models.PositiveIntegerField(default=30, validators=[MinValueValidator(0), MaxValueValidator(100)])
    education_weight = models.PositiveIntegerField(default=20, validators=[MinValueValidator(0), MaxValueValidator(100)])
    portfolio_weight = models.PositiveIntegerField(default=25, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Tags for search
    tags = models.JSONField(default=list)  # List of tags


    project_tags = models.JSONField(default=list,blank=True,null=True)  # List of tags for categorization
    project_profile_summary = models.TextField(blank=True, null=True)  # AI-generated summary of candidate profile
    search_query = models.JSONField(default=list, blank=True, null=True)
    professional_title = models.CharField(max_length=255, blank=True, null=True)


    
    # SEO
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    
    # Statistics
    views_count = models.PositiveIntegerField(default=0)
    applications_count = models.PositiveIntegerField(default=0)
    shortlisted_count = models.PositiveIntegerField(default=0)
    hired_count = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProjectQuerySet.as_manager()

    @property
    def is_expired(self) -> bool:
        """Deadline day has ended. Mirrors ProjectQuerySet.open()/expired()."""
        if not self.deadline:
            return False
        return self.deadline < timezone.now().date()

    @property
    def effective_status(self) -> str:
        """Status as users should see it, without waiting for close_expired_projects."""
        if self.status == 'active' and self.is_expired:
            return 'closed'
        return self.status

    class Meta:
        db_table = 'projects'
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['category', 'complexity']),
        ]
    
    def __str__(self):
        return f"{self.title} at {self.company.company_name}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(f"{self.title}-{self.company.company_name if self.company else 'anonymous'}")
        super().save(*args, **kwargs)


class ProjectSkill(models.Model):
    """
    Required skills for projects
    """
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='required_skills')
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=20, choices=Project.SKILL_LEVEL_CHOICES, default='intermediate')
    is_required = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'project_skills'
        verbose_name = 'Project Skill'
        verbose_name_plural = 'Project Skills'
        unique_together = ['project', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.level}) for {self.project.title}"


class ProjectMilestone(models.Model):
    """
    Project milestones for milestone-based projects
    """
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True, default='')
    due_date = models.DateField()
    payment_amount = models.PositiveIntegerField()
    
    class Meta:
        db_table = 'project_milestones'
        verbose_name = 'Project Milestone'
        verbose_name_plural = 'Project Milestones'
        ordering = ['due_date']
    
    def __str__(self):
        return f"{self.title} - {self.project.title}"