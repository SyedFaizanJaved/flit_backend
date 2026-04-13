from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Offer, MeetingRoom

@receiver(pre_save, sender=Offer)
def handle_offer_unread(sender, instance, **kwargs):
    if instance.pk:
        previous = Offer.objects.get(pk=instance.pk)
        if previous.status != instance.status:
            # If status changed, it's a new event that needs reading
            instance.is_read = False
            instance.is_read_by_employer = False
            instance.is_read_by_candidate = False

@receiver(post_save, sender=Offer)
def notify_offer(sender, instance, created, **kwargs):
    # Socket notification removed
    pass

@receiver(post_save, sender=MeetingRoom)
def notify_meeting_room(sender, instance, created, **kwargs):
    """Socket notification removed. Logic preserved for other potential uses."""
    pass


