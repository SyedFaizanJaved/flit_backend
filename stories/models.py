from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.validators import FileExtensionValidator


def story_media_upload_path(instance, filename):
    """
    Returns the upload path for story media files
    Format: stories/{user_id}/{timestamp}/{filename}
    """
    return f'stories/{instance.user.id}/{int(timezone.now().timestamp())}/{filename}'


class Story(models.Model):
    """
    Story model to represent user stories with relationships to Company, Project, and Job
    """
    CONTENT_TYPE_CHOICES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stories')
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES, default='text')
    title = models.CharField(max_length=200, blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    media_file = models.FileField(
        upload_to=story_media_upload_path,
        null=True, 
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'mp4', 'mov', 'avi'])
        ]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Relationships
    company = models.ForeignKey('companies.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    project = models.ForeignKey('projects.Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    job = models.ForeignKey('jobs.Job', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')
    
    # For generic relationships with other models
    target_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True, related_name='story_targets')
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey('target_content_type', 'target_object_id')
    
    # Add related names for likes, comments, and saved items
    likes = GenericRelation('Like', related_query_name='story')
    comments = GenericRelation('Comment', related_query_name='story')
    saved_by = GenericRelation('SavedItem', related_query_name='story')
    
    class Meta:
        verbose_name_plural = 'Stories'
        ordering = ['-created_at']
    
    def __str__(self):
        target_str = f" - {self.target}" if self.target else ""
        return f"Story by {self.user.email}{target_str} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


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
        id_fields = [self.company_id, self.project_id, self.job_id]
        if sum(1 for field in id_fields if field is not None) != 1:
            raise ValidationError('Exactly one of company_id, project_id, or job_id must be set')
    
    def save(self, *args, **kwargs):
        self.clean()
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
    Model to store comments on companies, projects, or jobs
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Specific ID fields - only one of these should be set
    company_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    project_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    job_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    candidate_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def clean(self):
        # Ensure only one of the ID fields is set
        id_fields = [self.company_id, self.project_id, self.job_id]
        if sum(1 for field in id_fields if field is not None) != 1:
            raise ValidationError('Exactly one of company_id, project_id, or job_id must be set')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.company_id:
            return f"{self.user.email} commented on company {self.company_id}"
        elif self.project_id:
            return f"{self.user.email} commented on project {self.project_id}"
        elif self.job_id:
            return f"{self.user.email} commented on job {self.job_id}"
        else:
            return f"{self.user.email} commented on candidate {self.candidate_id}"


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
