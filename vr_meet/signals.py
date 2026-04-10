from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Offer, MeetingRoom
from chat.utils import send_candidate_notification

@receiver(pre_save, sender=Offer)
def handle_offer_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = Offer.objects.get(pk=instance.pk)
        if previous.status != instance.status:
            instance.is_read = False

@receiver(post_save, sender=Offer)
def notify_offer(sender, instance, created, **kwargs):
    # Offer model has candidate as User, need candidate profile id
    try:
        candidate_id = instance.candidate.candidate_profile.id
        if created:
            send_candidate_notification(
                candidate_id=candidate_id,
                notification_type='notification_alert',
                title='New Offer!',
                message=f'You have received a new offer: {instance.title}',
                category='offer'
            )
        else:
            send_candidate_notification(
                candidate_id=candidate_id,
                notification_type='dashboard_update'
            )
    except:
        pass

@receiver(post_save, sender=MeetingRoom)
def notify_meeting_room(sender, instance, created, **kwargs):
    """Notify candidate when a meeting room (interview) is created or updated."""
    try:
        # MeetingRoom has candidate as User
        if instance.candidate:
            candidate_id = instance.candidate.candidate_profile.id
            if created:
                send_candidate_notification(
                    candidate_id=candidate_id,
                    notification_type='notification_alert',
                    title='New Interview Request!',
                    message=f'You have a new interview request: {instance.meeting_title}',
                    category='interview'
                )
            else:
                send_candidate_notification(
                    candidate_id=candidate_id,
                    notification_type='dashboard_update'
                )
    except Exception as e:
        print(f"Error in notify_meeting_room: {str(e)}")

