from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import ReferenceRequest
from chat.utils import send_candidate_notification

@receiver(pre_save, sender=ReferenceRequest)
def handle_reference_request_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = ReferenceRequest.objects.get(pk=instance.pk)
        # When status changes from pending to something else (accepted/declined/completed)
        # or when a reply_message is added, mark as unread for the candidate.
        if previous.status != instance.status or previous.reply_message != instance.reply_message:
            instance.is_read = False

@receiver(post_save, sender=ReferenceRequest)
def notify_reference_response(sender, instance, created, **kwargs):
    if not created and instance.status in ['completed', 'accepted', 'declined']:
        send_candidate_notification(
            candidate_id=instance.candidate.id,
            notification_type='notification_alert',
            title='Reference Update',
            message=f'Your reference request to {instance.reference_name} has a response.',
            category='reference'
        )
