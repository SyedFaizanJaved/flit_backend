from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import JobApplication, ProjectApplication, InterviewRequest

@receiver(pre_save, sender=JobApplication)
def handle_job_application_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = JobApplication.objects.get(pk=instance.pk)
        if (previous.status != instance.status or 
            previous.is_shortlisted != instance.is_shortlisted or 
            previous.is_rejected != instance.is_rejected):
            instance.is_read = False
            instance.is_read_by_candidate = False
            instance.is_read_by_employer = False

@receiver(post_save, sender=JobApplication)
def notify_job_application_update(sender, instance, created, **kwargs):
    # Socket notification removed
    pass

@receiver(pre_save, sender=ProjectApplication)
def handle_project_application_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = ProjectApplication.objects.get(pk=instance.pk)
        if (previous.status != instance.status or 
            previous.is_shortlisted != instance.is_shortlisted or 
            previous.is_rejected != instance.is_rejected):
            instance.is_read = False
            instance.is_read_by_candidate = False
            instance.is_read_by_employer = False

@receiver(post_save, sender=ProjectApplication)
def notify_project_application_update(sender, instance, created, **kwargs):
    # Socket notification removed
    pass

@receiver(pre_save, sender=InterviewRequest)
def handle_interview_request_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = InterviewRequest.objects.get(pk=instance.pk)
        if previous.status != instance.status:
            instance.is_read = False

@receiver(post_save, sender=InterviewRequest)
def notify_interview_request(sender, instance, created, **kwargs):
    # Socket notification removed
    pass


