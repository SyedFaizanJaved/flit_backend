from django.db import models
from django.conf import settings
from django.db.models import Count, Q


class ChatMessage(models.Model):
    """
    Chat message model
    """
    MESSAGE_TYPE_CHOICES = [
        ('text', 'Text'),
        ('interview_request', 'Interview Request'),
        ('quick_question', 'Quick Question'),
    ]
    
    # Basic Information
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    
    # Unread message count (cached count of unread messages per sender-recipient pair)
    unread_count = models.PositiveIntegerField(default=0, editable=False, null=False, blank=True, help_text='Number of unread messages')
    
    # Message Details
    message = models.TextField()
    messageType = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text')
    
    # Status
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    
    # Total unique candidates who messaged this employer
    total_candidates = models.PositiveIntegerField(default=0, 
        help_text='Total unique candidates who messaged this employer')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        # Ensure total_candidates has a default value
        if self.total_candidates is None:
            self.total_candidates = 0
            
        # Check if this is a new message
        is_new = self.pk is None
        
        # For new messages from candidate to employer
        if is_new and hasattr(self.sender, 'user_type') and hasattr(self.recipient, 'user_type') and \
           self.sender.user_type == 'candidate' and self.recipient.user_type == 'employer':
            
            # First, save the message with default total_candidates=0
            if self.total_candidates == 0:
                super().save(*args, **kwargs)
            
            # Get count of unique candidates who messaged this employer
            # including the current sender
            unique_candidates = ChatMessage.objects.filter(
                recipient=self.recipient,
                sender__user_type='candidate'
            ).values('sender').distinct().count()
            
            # If this is a new candidate, increment the count
            is_new_candidate = not ChatMessage.objects.filter(
                recipient=self.recipient,
                sender=self.sender,
                sender__user_type='candidate'
            ).exclude(pk=getattr(self, 'pk', None)).exists()
            
            if is_new_candidate:
                self.total_candidates = unique_candidates
                
                # Update all messages to this employer with the new count
                ChatMessage.objects.filter(
                    recipient=self.recipient
                ).update(
                    total_candidates=unique_candidates
                )
            
            # Save again with updated total_candidates
            super().save(force_update=True)
        else:
            # For non-candidate messages or updates, just save normally
            super().save(*args, **kwargs)
    
    class Meta:
        db_table = 'chat_messages'
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Message from {self.sender.email} to {self.recipient.email}"
        
    @classmethod
    def get_candidate_count_for_employer(cls, employer_id):
        """
        Returns the count of unique candidates who have messaged this employer
        """
        return cls.objects.filter(
            recipient_id=employer_id,
            sender__user_type='candidate'
        ).values('sender').distinct().count()


class ChatRoom(models.Model):
    """
    Chat room model for group conversations
    """
    ROOM_TYPE_CHOICES = [
        ('direct', 'Direct Message'),
        ('group', 'Group Chat'),
        ('interview', 'Interview Chat'),
        ('project', 'Project Chat'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200, blank=True, null=True)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES, default='direct')
    description = models.TextField(blank=True, null=True)
    
    # Participants
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='chat_rooms')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_chat_rooms')
    
    # Settings
    is_active = models.BooleanField(default=True)
    is_private = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'chat_rooms'
        verbose_name = 'Chat Room'
        verbose_name_plural = 'Chat Rooms'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name or f"Chat Room {self.id}"


class ChatRoomMessage(models.Model):
    """
    Messages in chat rooms
    """
    MESSAGE_TYPE_CHOICES = [
        ('text', 'Text'),
        ('file', 'File'),
        ('image', 'Image'),
        ('system', 'System'),
    ]
    
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='room_messages')
    
    # Message Details
    message = models.TextField()
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text')
    file_url = models.URLField(blank=True, null=True)
    
    # Status
    is_deleted = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'chat_room_messages'
        verbose_name = 'Chat Room Message'
        verbose_name_plural = 'Chat Room Messages'
        ordering = ['created_at']
    
    def __str__(self):
        return f"Message in {self.room.name} from {self.sender.email}"
