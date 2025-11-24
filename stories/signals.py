from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from .models import Story, Like, Comment, SavedStory


@receiver(pre_save, sender=Story)
def update_story_updated_at(sender, instance, **kwargs):
    """
    Update the updated_at field when a story is saved
    """
    instance.updated_at = timezone.now()


@receiver(post_save, sender=Like)
def update_story_like_count(sender, instance, created, **kwargs):
    """
    Update the like count for a story when a like is added
    """
    if created:
        # In a real implementation, you might want to update a denormalized like count here
        pass


@receiver(pre_delete, sender=Like)
def remove_like_count(sender, instance, **kwargs):
    """
    Update the like count for a story when a like is removed
    """
    # In a real implementation, you might want to update a denormalized like count here
    pass


@receiver(post_save, sender=Comment)
def send_comment_notification(sender, instance, created, **kwargs):
    """
    Send notification when a new comment is added
    """
    if created:
        # In a real implementation, you would send a notification to the story owner
        pass
