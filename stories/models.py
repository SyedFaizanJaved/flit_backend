from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError


def story_media_upload_path(instance, filename):
    """
    Returns the upload path for story media files
    Format: stories/{user_id}/{timestamp}/{filename}
    """
    return f'stories/{instance.user.id}/{int(timezone.now().timestamp())}/{filename}'


class Story(models.Model):
    """
    Model to represent stories shared by users
    """
    CONTENT_TYPE_CHOICES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
    ]
    
    # User who created the story (can be either employer or candidate)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stories')
    user_type = models.CharField(max_length=10, default='candidate', editable=False, help_text="Automatically set to 'employer' or 'candidate' based on user's profile")
    
    # Reference to company, candidate, project, or job
    company = models.ForeignKey('companies.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    candidate = models.ForeignKey('candidates.Candidate', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    project = models.ForeignKey('projects.Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    job = models.ForeignKey('jobs.Job', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    
    # Content type - determines which content field is used
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES, default='text')
    
    # Content fields (only one will be used based on content_type)
    text_content = models.TextField(blank=True, null=True, help_text="Text content for text stories")
    image_content = models.ImageField(
        upload_to=story_media_upload_path,
        null=True, 
        blank=True,
        help_text="Image content for image stories",
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif'])]
    )
    video_content = models.FileField(
        upload_to=story_media_upload_path,
        null=True,
        blank=True,
        help_text="Video content for video stories",
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi'])]
    )
    
    def clean(self):
        """
        Custom validation to ensure only the appropriate content field is used based on content_type
        and that either company or candidate is set based on user_type
        """
        from django.core.exceptions import ValidationError
        
        # Always set user_type based on user's profile first
        if self.user:
            if hasattr(self.user, 'employer_profile'):
                self.user_type = 'employer'
                # Set company if not already set
                if not self.company_id and self.user.employer_profile.company:
                    self.company = self.user.employer_profile.company
            elif hasattr(self.user, 'candidate_profile'):
                self.user_type = 'candidate'
                # Set candidate if not already set
                if not self.candidate_id:
                    self.candidate = self.user.candidate_profile
            else:
                raise ValidationError({
                    'user': 'User must be either an employer or a candidate to create a story.'
                })
        
        # Final validation
        if self.user_type == 'employer' and not self.company_id:
            raise ValidationError({
                'company': 'Company is required for employer stories.'
            })
        elif self.user_type == 'candidate' and not self.candidate_id:
            raise ValidationError({
                'candidate': 'Candidate profile is required for candidate stories.'
            })
        
        # Content validation
        if self.content_type == 'text':
            if not self.text_content:
                raise ValidationError({
                    'text_content': 'Text content is required for text stories'
                })
            if self.image_content or self.video_content:
                raise ValidationError({
                    'content_type': 'Only text content should be provided for text stories'
                })
        
        # Image content validation
        elif self.content_type == 'image':
            if not self.image_content:
                raise ValidationError({
                    'image_content': 'Image file is required for image stories'
                })
            if self.text_content or self.video_content:
                raise ValidationError({
                    'content_type': 'Only image content should be provided for image stories'
                })
        
        # Video content validation
        elif self.content_type == 'video':
            if not self.video_content:
                raise ValidationError({
                    'video_content': 'Video file is required for video stories'
                })
            if self.text_content or self.image_content:
                raise ValidationError({
                    'media_file': 'Please upload a valid video file (MP4, MOV, AVI).'
                })
    
    # Status and timestamps
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Relationships
    company = models.ForeignKey('companies.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    candidate = models.ForeignKey('candidates.Candidate', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    
    # Social interactions
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked_stories', blank=True)
    comments = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Comment', related_name='commented_stories')
    saved_by = models.ManyToManyField(settings.AUTH_USER_MODEL, through='SavedStory', related_name='saved_stories', blank=True)
    
    class Meta:
        verbose_name_plural = 'Stories'
        ordering = ['-created_at']
    
    def __str__(self):
        user_identifier = f"Employer {self.company.name}" if self.user_type == 'employer' and self.company else f"Candidate {self.candidate.user.email if self.candidate and hasattr(self.candidate, 'user') else 'Unknown'}"
        return f"Story by {user_identifier} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    def clean(self):
        # Validate that either company or candidate is set based on user_type
        if self.user_type == 'employer' and not self.company:
            raise ValidationError("Company is required for employer stories")
        if self.user_type == 'candidate' and not self.candidate:
            raise ValidationError("Candidate is required for candidate stories")
    
    def save(self, *args, **kwargs):
        # Ensure user_type is set before any validation
        if not self.user_type and self.user:
            if hasattr(self.user, 'employer_profile'):
                self.user_type = 'employer'
            elif hasattr(self.user, 'candidate_profile'):
                self.user_type = 'candidate'
        
        # Run full validation
        self.full_clean()
        
        # Ensure we have a valid user_type before saving
        if not self.user_type:
            raise ValueError("Could not determine user_type. User must be either an employer or a candidate.")
            
        super().save(*args, **kwargs)


class Like(models.Model):
    """
    Model to track likes on companies, projects, or jobs
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Specific ID fields - only one of these should be set
    company_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    project_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    job_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    candidate_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'company_id'],
                name='unique_user_company_like',
                condition=models.Q(company_id__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['user', 'project_id'],
                name='unique_user_project_like',
                condition=models.Q(project_id__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['user', 'job_id'],
                name='unique_user_job_like',
                condition=models.Q(job_id__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['user', 'candidate_id'],
                name='unique_user_candidate_like',
                condition=models.Q(candidate_id__isnull=False)
            ),
        ]
    
    def clean(self):
        # Ensure only one of the ID fields is set
        id_fields = [self.company_id, self.project_id, self.job_id, self.candidate_id]
        if sum(1 for field in id_fields if field is not None) != 1:
            raise ValidationError('Exactly one of company_id, project_id, job_id, or candidate_id must be set')
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.company_id:
            return f"{self.user.email} likes company {self.company_id}"
        elif self.project_id:
            return f"{self.user.email} likes project {self.project_id}"
        elif self.job_id:
            return f"{self.user.email} likes job {self.job_id}"
        return f"{self.user.email} likes candidate {self.candidate_id}"


class Comment(models.Model):
    """
    Model to store comments on stories and other entities
    """
    story = models.ForeignKey('Story', on_delete=models.CASCADE, related_name='story_comments', null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_comments')
    candidate = models.ForeignKey('candidates.Candidate', on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        if self.story:
            return f"{self.user.email} commented on story {self.story.id}"
        elif self.candidate:
            return f"{self.user.email} commented on candidate {self.candidate.id}"
        return f"{self.user.email} comment"


class SavedItem(models.Model):
    """
    Model to track saved items (companies, projects, jobs) by users
    """
    SAVED_ITEM_TYPES = [
        ('company', 'Company'),
        ('project', 'Project'),
        ('job', 'Job'),
        ('candidate', 'Candidate'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_items')
    item_type = models.CharField(max_length=10, choices=SAVED_ITEM_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Specific ID fields - only one of these should be set
    company_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    project_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    job_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    candidate_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    
    class Meta:
        verbose_name = 'Saved Item'
        verbose_name_plural = 'Saved Items'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'company_id'],
                name='unique_user_company_save',
                condition=models.Q(company_id__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['user', 'project_id'],
                name='unique_user_project_save',
                condition=models.Q(project_id__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['user', 'job_id'],
                name='unique_user_job_save',
                condition=models.Q(job_id__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['user', 'candidate_id'],
                name='unique_user_candidate_save',
                condition=models.Q(candidate_id__isnull=False)
            ),
        ]
    
    def clean(self):
        # Ensure item_type matches the ID field that's set
        if self.item_type == 'company' and not self.company_id:
            raise ValidationError('company_id must be set when item_type is company')
        elif self.item_type == 'project' and not self.project_id:
            raise ValidationError('project_id must be set when item_type is project')
        elif self.item_type == 'job' and not self.job_id:
            raise ValidationError('job_id must be set when item_type is job')
        elif self.item_type == 'candidate' and not self.candidate_id:
            raise ValidationError('candidate_id must be set when item_type is candidate')
        
        # Ensure only one ID field is set
        id_fields = [self.company_id, self.project_id, self.job_id, self.candidate_id]
        if sum(1 for field in id_fields if field is not None) != 1:
            raise ValidationError('Exactly one of company_id, project_id, job_id, or candidate_id must be set')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.company_id:
            return f"{self.user.email} saved company {self.company_id}"
        elif self.project_id:
            return f"{self.user.email} saved project {self.project_id}"
        elif self.job_id:
            return f"{self.user.email} saved job {self.job_id}"
        else:
            return f"{self.user.email} saved candidate {self.candidate_id}"


class SavedStory(models.Model):
    """
    Model to track saved stories by users
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_story_items')
    story = models.ForeignKey('Story', on_delete=models.CASCADE, related_name='saved_by_users')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Saved Story'
        verbose_name_plural = 'Saved Stories'
        ordering = ['-created_at']
        unique_together = ['user', 'story']
    
    def __str__(self):
        return f"{self.user.email} saved story {self.story.id}"
