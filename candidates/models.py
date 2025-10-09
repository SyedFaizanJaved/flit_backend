from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Candidate(models.Model):
    """
    Candidate profile model with comprehensive information
    """
    WORK_STYLE_CHOICES = [
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('in-person', 'In-Person'),
    ]
    
    AVAILABILITY_TYPE_CHOICES = [
        ('full-time', 'Full-time'),
        ('part-time', 'Part-time'),
        ('contract', 'Contract'),
        ('limited', 'Limited'),
    ]
    
    PROFILE_VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('limited', 'Limited'),
        ('private', 'Private'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='candidate_profile')
    
    # Basic Information
    full_name = models.CharField(max_length=200)
    title = models.CharField(max_length=200)  # Professional Title
    bio = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    time_zone = models.CharField(max_length=100, blank=True, null=True)
    
    # Work Preferences
    is_remote = models.BooleanField(default=True)
    work_style = models.CharField(max_length=20, choices=WORK_STYLE_CHOICES, default='remote')
    is_available = models.BooleanField(default=True)
    availability_type = models.CharField(max_length=20, choices=AVAILABILITY_TYPE_CHOICES, blank=True, null=True)
    
    # Skills & Experience
    skills = models.JSONField(default=list)  # List of skills
    superpowers = models.JSONField(default=list)  # List of career superpowers (max 5)
    preferred_roles = models.JSONField(default=list)  # List of preferred role types
    passion_projects = models.TextField(blank=True, null=True)
    
    # Compensation
    min_salary = models.PositiveIntegerField(blank=True, null=True)
    max_salary = models.PositiveIntegerField(blank=True, null=True)
    salary_currency = models.CharField(max_length=3, default='USD')
    
    # Portfolio & Media
    portfolio_links = models.JSONField(default=list)  # List of dicts: {name, url}
    profile_image = models.ImageField(upload_to='candidates/profile_images/', blank=True, null=True)
    resume_url = models.URLField(blank=True, null=True)
    video_intro_url = models.URLField(blank=True, null=True)
    intro_video_description = models.TextField(blank=True, null=True)
    
    # Privacy Settings
    profile_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    video_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    contact_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='limited')
    salary_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='private')
    
    # Profile Completion Status
    basic_info_completed = models.BooleanField(default=False)
    work_preferences_completed = models.BooleanField(default=False)
    skills_completed = models.BooleanField(default=False)
    portfolio_completed = models.BooleanField(default=False)
    privacy_completed = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidates'
        verbose_name = 'Candidate'
        verbose_name_plural = 'Candidates'
    
    def __str__(self):
        return self.full_name
    
    @property
    def is_profile_complete(self):
        flags = [
            bool(self.basic_info_completed),
            bool(self.work_preferences_completed),
            bool(self.skills_completed),
            bool(self.portfolio_completed),
            bool(self.privacy_completed),
        ]
        return sum(flags) >= 2


class WorkDNA(models.Model):
    """
    Work DNA assessment for candidates
    """
    COMMUNICATION_STYLE_CHOICES = [
        ('direct', 'Direct'),
        ('diplomatic', 'Diplomatic'),
        ('analytical', 'Analytical'),
        ('expressive', 'Expressive'),
    ]
    
    WORKING_STYLE_CHOICES = [
        ('independent', 'Independent'),
        ('collaborative', 'Collaborative'),
        ('structured', 'Structured'),
        ('flexible', 'Flexible'),
    ]
    
    PROBLEM_SOLVING_CHOICES = [
        ('analytical', 'Analytical'),
        ('creative', 'Creative'),
        ('systematic', 'Systematic'),
        ('intuitive', 'Intuitive'),
    ]
    
    TEAM_DYNAMICS_CHOICES = [
        ('leader', 'Leader'),
        ('supporter', 'Supporter'),
        ('facilitator', 'Facilitator'),
        ('specialist', 'Specialist'),
    ]
    
    WORK_ENVIRONMENT_CHOICES = [
        ('quiet', 'Quiet'),
        ('energetic', 'Energetic'),
        ('creative', 'Creative'),
        ('structured', 'Structured'),
    ]
    
    LEADERSHIP_STYLE_CHOICES = [
        ('autocratic', 'Autocratic'),
        ('democratic', 'Democratic'),
        ('laissez-faire', 'Laissez-faire'),
        ('transformational', 'Transformational'),
    ]
    
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='work_dna')
    communication_style = models.CharField(max_length=20, choices=COMMUNICATION_STYLE_CHOICES, blank=True, null=True)
    working_style = models.CharField(max_length=20, choices=WORKING_STYLE_CHOICES, blank=True, null=True)
    problem_solving_approach = models.CharField(max_length=20, choices=PROBLEM_SOLVING_CHOICES, blank=True, null=True)
    team_dynamics = models.CharField(max_length=20, choices=TEAM_DYNAMICS_CHOICES, blank=True, null=True)
    work_environment_preference = models.CharField(max_length=20, choices=WORK_ENVIRONMENT_CHOICES, blank=True, null=True)
    leadership_style = models.CharField(max_length=20, choices=LEADERSHIP_STYLE_CHOICES, blank=True, null=True)
    values = models.JSONField(default=list)  # List of core values
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_work_dna'
        verbose_name = 'Work DNA'
        verbose_name_plural = 'Work DNA Records'
    
    def __str__(self):
        return f"Work DNA for {self.candidate.full_name}"


class Reference(models.Model):
    """
    Reference system for candidates
    """
    RELATIONSHIP_TYPE_CHOICES = [
        ('colleague', 'Colleague'),
        ('manager', 'Manager'),
        ('client', 'Client'),
        ('mentor', 'Mentor'),
        ('friend', 'Friend'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='references')
    relationship_type = models.CharField(max_length=20, choices=RELATIONSHIP_TYPE_CHOICES)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    worked_together = models.BooleanField(default=False)
    work_duration = models.CharField(max_length=100, blank=True, null=True)
    overall_rating = models.PositiveIntegerField(blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    skill_ratings = models.JSONField(default=dict)  # Dict of skill ratings
    superpowers = models.JSONField(default=list)  # List of superpowers
    headline = models.CharField(max_length=200, blank=True, null=True)
    testimonial = models.TextField(blank=True, null=True)
    specific_achievements = models.JSONField(default=list)  # List of achievements
    referral_reason = models.TextField(blank=True, null=True)
    is_public = models.BooleanField(default=True)
    
    # Reference contact info
    reference_name = models.CharField(max_length=200)
    reference_email = models.EmailField()
    reference_phone = models.CharField(max_length=20, blank=True, null=True)
    reference_position = models.CharField(max_length=200, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_references'
        verbose_name = 'Reference'
        verbose_name_plural = 'References'
    
    def __str__(self):
        return f"Reference from {self.reference_name} for {self.candidate.full_name}"


class ReferenceRequest(models.Model):
    """
    Reference requests sent by candidates
    """
    RELATIONSHIP_TYPE_CHOICES = [
        ('colleague', 'Colleague'),
        ('manager', 'Manager'),
        ('client', 'Client'),
        ('mentor', 'Mentor'),
        ('friend', 'Friend'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('completed', 'Completed'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='reference_requests')
    reference_email = models.EmailField()
    reference_name = models.CharField(max_length=200)
    suggested_relationship = models.CharField(max_length=20, choices=RELATIONSHIP_TYPE_CHOICES, blank=True, null=True)
    suggested_company = models.CharField(max_length=200, blank=True, null=True)
    request_message = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_reference_requests'
        verbose_name = 'Reference Request'
        verbose_name_plural = 'Reference Requests'
    
    def __str__(self):
        return f"Reference request to {self.reference_name} from {self.candidate.full_name}"


class Education(models.Model):
    """
    Education history for candidates
    """
    DEGREE_CHOICES = [
        ('high_school', 'High School'),
        ('associate', 'Associate'),
        ('bachelor', 'Bachelor'),
        ('master', 'Master'),
        ('phd', 'PhD'),
        ('certificate', 'Certificate'),
        ('diploma', 'Diploma'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='education')
    institution = models.CharField(max_length=200)
    degree = models.CharField(max_length=20, choices=DEGREE_CHOICES)
    field_of_study = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_education'
        verbose_name = 'Education'
        verbose_name_plural = 'Education Records'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.degree} in {self.field_of_study} from {self.institution}"


class Experience(models.Model):
    """
    Work experience for candidates
    """
    EMPLOYMENT_TYPE_CHOICES = [
        ('full-time', 'Full-time'),
        ('part-time', 'Part-time'),
        ('contract', 'Contract'),
        ('freelance', 'Freelance'),
        ('internship', 'Internship'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='experience')
    company_name = models.CharField(max_length=200)
    position = models.CharField(max_length=200)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    location = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField()
    achievements = models.JSONField(default=list)  # List of achievements
    skills_used = models.JSONField(default=list)  # List of skills used
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_experience'
        verbose_name = 'Experience'
        verbose_name_plural = 'Experience Records'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.position} at {self.company_name}"


class Achievement(models.Model):
    """
    Achievements and accomplishments for candidates
    """
    ACHIEVEMENT_TYPE_CHOICES = [
        ('award', 'Award'),
        ('certification', 'Certification'),
        ('project', 'Project'),
        ('publication', 'Publication'),
        ('other', 'Other'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='achievements')
    title = models.CharField(max_length=200)
    achievement_type = models.CharField(max_length=20, choices=ACHIEVEMENT_TYPE_CHOICES)
    description = models.TextField()
    date_achieved = models.DateField()
    issuer = models.CharField(max_length=200, blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_achievements'
        verbose_name = 'Achievement'
        verbose_name_plural = 'Achievements'
        ordering = ['-date_achieved']
    
    def __str__(self):
        return f"{self.title} - {self.candidate.full_name}"


class MediaFile(models.Model):
    """
    Media files (video/audio) for candidates
    """
    MEDIA_TYPE_CHOICES = [
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('image', 'Image'),
        ('document', 'Document'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='media_files')
    title = models.CharField(max_length=200)
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPE_CHOICES)
    file_url = models.URLField()
    description = models.TextField(blank=True, null=True)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)
    file_size_mb = models.PositiveIntegerField(blank=True, null=True)
    is_public = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_media_files'
        verbose_name = 'Media File'
        verbose_name_plural = 'Media Files'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.media_type}) - {self.candidate.full_name}"


class CandidatePreference(models.Model):
    """
    Preferences and settings for candidates
    """
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='preferences')
    
    # Notification Settings
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    
    # Job Search Preferences
    job_alert_frequency = models.CharField(max_length=20, choices=[
        ('immediate', 'Immediate'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], default='daily')
    
    # Privacy Settings
    profile_visibility = models.CharField(max_length=20, choices=[
        ('public', 'Public'),
        ('limited', 'Limited'),
        ('private', 'Private'),
    ], default='public')
    
    # Matching Preferences
    auto_matching = models.BooleanField(default=True)
    skill_match_threshold = models.PositiveIntegerField(default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidate_preferences'
        verbose_name = 'Candidate Preference'
        verbose_name_plural = 'Candidate Preferences'
    
    def __str__(self):
        return f"Preferences for {self.candidate.full_name}"
