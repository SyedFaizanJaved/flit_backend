from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import JobApplication, ProjectApplication, InterviewRequest
from chat.utils import send_candidate_notification

@receiver(pre_save, sender=JobApplication)
def handle_job_application_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = JobApplication.objects.get(pk=instance.pk)
        if (previous.status != instance.status or 
            previous.is_shortlisted != instance.is_shortlisted or 
            previous.is_rejected != instance.is_rejected):
            instance.is_read = False

@receiver(post_save, sender=JobApplication)
def notify_job_application_update(sender, instance, created, **kwargs):
    if not created:
        send_candidate_notification(
            candidate_id=instance.candidate.id,
            notification_type='notification_alert',
            title='Application Update',
            message=f'Your application for {instance.job.title} has been updated.',
            category='application'
        )

@receiver(pre_save, sender=ProjectApplication)
def handle_project_application_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = ProjectApplication.objects.get(pk=instance.pk)
        if (previous.status != instance.status or 
            previous.is_shortlisted != instance.is_shortlisted or 
            previous.is_rejected != instance.is_rejected):
            instance.is_read = False

@receiver(post_save, sender=ProjectApplication)
def notify_project_application_update(sender, instance, created, **kwargs):
    if not created:
        send_candidate_notification(
            candidate_id=instance.candidate.id,
            notification_type='notification_alert',
            title='Project Update',
            message=f'Your application for {instance.project.title} has been updated.',
            category='application'
        )

@receiver(pre_save, sender=InterviewRequest)
def handle_interview_request_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = InterviewRequest.objects.get(pk=instance.pk)
        if previous.status != instance.status:
            instance.is_read = False

@receiver(post_save, sender=InterviewRequest)
def notify_interview_request(sender, instance, created, **kwargs):
    candidate_id = None
    title = ""
    if instance.job_application:
        candidate_id = instance.job_application.candidate.id
        title = instance.job_application.job.title
    elif instance.project_application:
        candidate_id = instance.project_application.candidate.id
        title = instance.project_application.project.title

    if candidate_id:
        if created:
            send_candidate_notification(
                candidate_id=candidate_id,
                notification_type='notification_alert',
                title='Interview Request',
                message=f'You have a new interview request for {title}.',
                category='interview'
            )
        else:
            send_candidate_notification(candidate_id=candidate_id) # Just update dashboard

