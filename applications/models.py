from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class JobApplication(models.Model):
    """
    Job application model
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewing', 'Reviewing'),
        ('shortlisted', 'Shortlisted'),
        ('interviewed', 'Interviewed'),
        ('offered', 'Offered'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]
    
    # Basic Information
    candidate = models.ForeignKey('candidates.Candidate', on_delete=models.CASCADE, related_name='job_applications')
    job = models.ForeignKey('jobs.Job', on_delete=models.CASCADE, related_name='applications')
    employer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_job_applications')
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='job_applications')
    
    # Application Details (matching JobApplicationFields)
    coverLetter = models.TextField(blank=True, null=True)
    resumeUrl = models.URLField(blank=True, null=True)
    interestedInTemp = models.BooleanField(default=False)
    
    # Application Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_read = models.BooleanField(default=False)
    is_read_by_candidate = models.BooleanField(default=False)
    is_read_by_employer = models.BooleanField(default=False)
    
    # Matching Scores
    overall_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    skills_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    experience_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    education_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    location_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    salary_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Employer Actions
    is_shortlisted = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Offer Details
    offer_salary = models.PositiveIntegerField(blank=True, null=True)
    offer_start_date = models.DateField(blank=True, null=True)
    offer_terms = models.TextField(blank=True, null=True)
    
    # Flags
    is_withdrawn = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    
    # Timestamps
    applied_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'job_applications'
        verbose_name = 'Job Application'
        verbose_name_plural = 'Job Applications'
        ordering = ['-applied_at']
        unique_together = ['candidate', 'job']
    
    def __str__(self):
        return f"Application for {self.job.title} by {self.candidate.full_name}"


class ProjectApplication(models.Model):
    """
    Project application model
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewing', 'Reviewing'),
        ('shortlisted', 'Shortlisted'),
        ('interviewed', 'Interviewed'),
        ('offered', 'Offered'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]
    
    # Basic Information
    candidate = models.ForeignKey('candidates.Candidate', on_delete=models.CASCADE, related_name='project_applications')
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='applications')
    employer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_project_applications')
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='project_applications')
    
    # Application Details (matching ProjectApplicationFields)
    coverLetter = models.TextField(blank=True, null=True)
    
    # Application Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_read = models.BooleanField(default=False)
    is_read_by_candidate = models.BooleanField(default=False)
    is_read_by_employer = models.BooleanField(default=False)
    
    # Matching Scores
    overall_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    skills_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    experience_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    education_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    portfolio_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    budget_match_score = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    
    # Employer Actions
    is_shortlisted = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Offer Details
    offer_amount = models.PositiveIntegerField(blank=True, null=True)
    offer_start_date = models.DateField(blank=True, null=True)
    offer_terms = models.TextField(blank=True, null=True)
    
    # Flags
    is_withdrawn = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    
    # Timestamps
    applied_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'project_applications'
        verbose_name = 'Project Application'
        verbose_name_plural = 'Project Applications'
        ordering = ['-applied_at']
        unique_together = ['candidate', 'project']
    
    def __str__(self):
        return f"Application for {self.project.title} by {self.candidate.full_name}"


class Interview(models.Model):
    """
    Interview scheduling and management
    """
    INTERVIEW_TYPE_CHOICES = [
        ('phone', 'Phone'),
        ('video', 'Video'),
        ('in-person', 'In-Person'),
        ('technical', 'Technical'),
        ('final', 'Final'),
    ]
    
    INTERVIEW_STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled'),
    ]
    
    # Generic foreign key to either job or project application
    job_application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='interviews', blank=True, null=True)
    project_application = models.ForeignKey(ProjectApplication, on_delete=models.CASCADE, related_name='interviews', blank=True, null=True)
    
    interview_type = models.CharField(max_length=20, choices=INTERVIEW_TYPE_CHOICES)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    interviewer = models.CharField(max_length=200)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=INTERVIEW_STATUS_CHOICES, default='scheduled')
    
    # Interview Feedback
    rating = models.PositiveIntegerField(blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    feedback_comments = models.TextField(blank=True, null=True)
    strengths = models.JSONField(default=list)  # List of strengths
    areas_for_improvement = models.JSONField(default=list)  # List of areas for improvement
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'interviews'
        verbose_name = 'Interview'
        verbose_name_plural = 'Interviews'
        ordering = ['scheduled_at']
    
    def __str__(self):
        if self.job_application:
            return f"{self.interview_type} interview for {self.job_application.job.title}"
        elif self.project_application:
            return f"{self.interview_type} interview for {self.project_application.project.title}"
        return f"{self.interview_type} interview"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.job_application and not self.project_application:
            raise ValidationError('Interview must be for either a job or project application.')
        if self.job_application and self.project_application:
            raise ValidationError('Interview cannot be for both job and project application.')


class ApplicationMessage(models.Model):
    """
    Communication between candidates and employers
    """
    SENDER_CHOICES = [
        ('candidate', 'Candidate'),
        ('employer', 'Employer'),
    ]
    
    # Generic foreign key to either job or project application
    job_application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='messages', blank=True, null=True)
    project_application = models.ForeignKey(ProjectApplication, on_delete=models.CASCADE, related_name='messages', blank=True, null=True)
    
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'application_messages'
        verbose_name = 'Application Message'
        verbose_name_plural = 'Application Messages'
        ordering = ['created_at']
    
    def __str__(self):
        if self.job_application:
            return f"Message from {self.sender} for {self.job_application.job.title}"
        elif self.project_application:
            return f"Message from {self.sender} for {self.project_application.project.title}"
        return f"Message from {self.sender}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.job_application and not self.project_application:
            raise ValidationError('Message must be for either a job or project application.')
        if self.job_application and self.project_application:
            raise ValidationError('Message cannot be for both job and project application.')


class InterviewRequest(models.Model):
    """
    Interview request model
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('completed', 'Completed'),
    ]
    
    # Generic foreign key to either job or project application
    job_application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='interview_requests', blank=True, null=True)
    project_application = models.ForeignKey(ProjectApplication, on_delete=models.CASCADE, related_name='interview_requests', blank=True, null=True)
    
    proposedTime = models.DateTimeField(blank=True, null=True)
    meetLink = models.URLField(blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_read = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'interview_requests'
        verbose_name = 'Interview Request'
        verbose_name_plural = 'Interview Requests'
    
    def __str__(self):
        if self.job_application:
            return f"Interview request for {self.job_application.job.title}"
        elif self.project_application:
            return f"Interview request for {self.project_application.project.title}"
        return "Interview request"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.job_application and not self.project_application:
            raise ValidationError('Interview request must be for either a job or project application.')
        if self.job_application and self.project_application:
            raise ValidationError('Interview request cannot be for both job and project application.')
