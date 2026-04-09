import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from utils.currency_choices import CURRENCY_CHOICES
from utils.file_validators import (
    image_upload_path,
    resume_upload_path,
    video_upload_path,
    achievement_image_upload_path
)


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

    SENIORITY_LEVEL_CHOICES = [
        ('junior', 'Junior'),
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('mid', 'Mid'),
        ('senior', 'Senior'),
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
    seniority_level = models.CharField(max_length=20, choices=SENIORITY_LEVEL_CHOICES, blank=True, null=True)
    
    
    # Compensation
    min_salary = models.PositiveIntegerField(blank=True, null=True)
    max_salary = models.PositiveIntegerField(blank=True, null=True)
    salary_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    
    # Portfolio & Media
    portfolio_links = models.JSONField(default=list)  # List of dicts: {name, url}
    profile_image = models.FileField(
        upload_to=image_upload_path, 
        blank=True, 
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif'])]
    )
    resume_url = models.FileField(upload_to=resume_upload_path, blank=True, null=True)  # User uploaded resume
    ai_resume_url = models.FileField(upload_to=resume_upload_path, blank=True, null=True)  # AI-generated resume
    video_intro_url = models.FileField(upload_to=video_upload_path, blank=True, null=True)
    intro_video_description = models.JSONField(blank=True, null=True, default=dict)
    # Full raw transcription text returned by ML services
    video_transcription = models.TextField(blank=True, null=True)
    
    # Privacy Settings
    profile_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    video_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    contact_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='limited')
    salary_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='private')
    profile_views = models.PositiveIntegerField(default=0)
    viewers = models.JSONField(default=list)
    
    # Profile Completion Status
    basic_info_completed = models.BooleanField(default=False)
    work_preferences_completed = models.BooleanField(default=False)
    skills_completed = models.BooleanField(default=False)
    portfolio_completed = models.BooleanField(default=False)
    privacy_completed = models.BooleanField(default=False)


    # Ml Endpoints
    candidate_tags = models.JSONField(default=list,blank=True, null=True)  # List of tags for categorization
    candidate_profile_summary = models.TextField(blank=True, null=True)  # AI-generated summary of candidate profile
    search_query = models.JSONField(default=list, blank=True, null=True)
    resume_data = models.JSONField(blank=True, null=True,default=dict)  # Store parsed resume data from ML API
    professional_title = models.CharField(max_length=255, blank=True, null=True)


    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'candidates'
        verbose_name = 'Candidate'
        verbose_name_plural = 'Candidates'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.full_name
    
    @property
    def is_profile_complete(self):
        # If basic info is completed, consider profile as complete
        if getattr(self, 'basic_info_completed', False):
            return True
            
        # Original logic for backward compatibility
        flags = [
            bool(self.basic_info_completed),
            bool(self.work_preferences_completed),
            bool(self.skills_completed),
            bool(self.portfolio_completed),
            bool(self.privacy_completed),
        ]
        return sum(flags) >= 1


class WorkDNAQuestion(models.Model):
    """
    Model to store work DNA questions and responses
    """
    candidate = models.ForeignKey('Candidate', on_delete=models.CASCADE, related_name='work_dna_questions')
    candidate_name = models.CharField(max_length=255)
    questions = models.JSONField()
    answers = models.JSONField(default=dict, blank=True)  # Stores selected answers in format: {"1": "option_text", "2": "option_text"}
    evaluation_result = models.JSONField(null=True, blank=True)  # Stores the evaluation results from ML API
    total_questions = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'candidate_work_dna_questions'
        verbose_name = 'Work DNA Question'
        verbose_name_plural = 'Work DNA Questions'

    def __str__(self):
        return f"Work DNA Questions for {self.candidate_name} ({self.candidate.id})"
        
    def update_answers(self, question_id, selected_option):
        """
        Helper method to update answers
        
        Args:
            question_id: Can be either the question number (as string) or the question text
            selected_option: The selected answer option
        """
        if not self.answers:
            self.answers = {}
            
        # If question_id is a number, update using the actual question text
        if isinstance(question_id, str) and question_id.isdigit() and hasattr(self, 'questions'):
            try:
                question_text = self.questions[int(question_id) - 1].get('question', f'Question {question_id}')
                # Remove any existing answer for this question (by text)
                self.answers = {k: v for k, v in self.answers.items() if k != question_text and k != question_id}
                # Add the new answer with question text as key
                self.answers[question_text] = selected_option
            except (IndexError, TypeError):
                # Fallback to using the question_id as is if we can't get the question text
                self.answers[question_id] = selected_option
        else:
            # If question_id is already the question text, just update it
            self.answers[question_id] = selected_option
            
        self.save()


class ReferenceRequest(models.Model):
    """
    Reference requests sent by candidates.
    Includes idempotent email sending and automatic 7-day expiry.
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
        ('expired', 'Expired'),          # auto-set when request passes 7-day expiry
    ]

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='reference_requests')
    reference_email = models.EmailField()
    reference_name = models.CharField(max_length=200)
    suggested_relationship = models.CharField(max_length=20, choices=RELATIONSHIP_TYPE_CHOICES, blank=True, null=True)
    suggested_company = models.CharField(max_length=200, blank=True, null=True)
    request_message = models.TextField(blank=True, null=True)
    reply_message = models.TextField(blank=True, null=True, verbose_name='Reference Response')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_read = models.BooleanField(default=True) # Default True because candidate created it pending.
    token = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )
    expires_at = models.DateTimeField(blank=True, null=True)

    # Duplicate-email prevention: set once the first email is successfully
    # sent; checked before every subsequent send attempt.
    email_sent_at = models.DateTimeField(
        blank=True, null=True,
        help_text='Timestamp when the reference email was successfully sent.'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Ensure token is set and unique
        if not self.token:
            self.token = uuid.uuid4()
            while ReferenceRequest.objects.filter(token=self.token).exists():
                self.token = uuid.uuid4()

        # Set expiry to 7 days from creation if not already set
        if not self.expires_at and not self.pk:
            from django.utils import timezone
            from datetime import timedelta
            self.expires_at = timezone.now() + timedelta(days=7)

        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        """Check if this request has passed its expiry date."""
        from django.utils import timezone
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    def mark_expired(self):
        """
        Transition status to 'expired' if still pending and past expiry.
        Returns True if status was changed.
        """
        if self.status == 'pending' and self.is_expired:
            self.status = 'expired'
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    def mark_email_sent(self):
        """Record that the notification email was successfully delivered."""
        from django.utils import timezone
        if not self.email_sent_at:
            self.email_sent_at = timezone.now()
            self.save(update_fields=['email_sent_at', 'updated_at'])

    class Meta:
        db_table = 'candidate_reference_requests'
        verbose_name = 'Reference Request'
        verbose_name_plural = 'Reference Requests'

    def __str__(self):
        return f"Ref Request #{self.pk} → {self.reference_name} ({self.status})"

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
    
    GRADING_SYSTEM_CHOICES = [
        ('gpa', 'GPA'),
        ('gpr', 'GPR'),
        ('grade', 'Grade'),
        ('marks', 'Marks'),
    ]
    
    GRADE_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
        ('E', 'E'),
        ('F', 'F'),
    ]
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='education')
    institution = models.CharField(max_length=200)
    degree = models.CharField(max_length=20, choices=DEGREE_CHOICES)
    field_of_study = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    
    # Grading System
    grading_system = models.CharField(max_length=10, choices=GRADING_SYSTEM_CHOICES, blank=True, null=True)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True, help_text="For GPA/GPR system")
    grade = models.CharField(max_length=1, choices=GRADE_CHOICES, blank=True, null=True, help_text="For Grade system (A-F)")
    total_marks = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="For Marks system")
    obtained_marks = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="For Marks system")
    
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
    description = models.TextField(blank=True, null=True)
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
    description = models.TextField(blank=True, null=True)
    date_achieved = models.DateField()
    issuer = models.CharField(max_length=200, blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    image = models.FileField(
        upload_to=achievement_image_upload_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif'])]
    )
    
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
