from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import ReferenceRequest

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
    # Socket notification removed
    pass

