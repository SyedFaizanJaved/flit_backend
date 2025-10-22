from django.db import models
from django.conf import settings


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
    
    # Message Details
    message = models.TextField()
    messageType = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text')
    
    # Status
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'chat_messages'
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Message from {self.sender.email} to {self.recipient.email}"


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
