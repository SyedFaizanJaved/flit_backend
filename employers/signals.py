from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import CandidateAction
from chat.utils import send_candidate_notification

print("DEBUG: employers/signals.py IMPORTED")

@receiver(pre_save, sender=CandidateAction)
def handle_candidate_action_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = CandidateAction.objects.get(pk=instance.pk)
        if previous.action != instance.action:
            instance.is_read = False

@receiver(post_save, sender=CandidateAction)
def notify_candidate_action(sender, instance, created, **kwargs):
    print(f"DEBUG: notify_candidate_action triggered for action={instance.action}, candidate_id={instance.candidate_id}")
    if instance.action == 'pass':
        print(f"DEBUG: Action is 'pass', calling send_candidate_notification")
        # Send real-time notification
        send_candidate_notification(
            candidate_id=instance.candidate_id,
            notification_type='notification_alert',
            title='New Flit!',
            message='A company has flitted you! Check your Flit List.',
            category='flit'
        )
