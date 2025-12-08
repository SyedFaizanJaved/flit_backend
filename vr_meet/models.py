from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.conf import settings
import random
import string

#----------------------------
#  unique room code generator
#----------------------------
def generate_room_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
def unique_room_code():
    while True:
        code = generate_room_code()
        if not MeetingRoom.objects.filter(room_code=code).exists():
            return code

class MeetingRoom(models.Model):
    ROOM_TYPE_CHOICES = [
        ("interview", "Interview"),
        ("networking", "Networking"),
        ("casual", "Casual")
    ]

    PURPOSE_CHOICES = [
        ("interview", "Interview"),
        ("casual_call", "Casual Call"),
        ("discussion", "Discussion")
    ]

    ENVIRONMENT_CHOICES =[
        ("office", "Office"),
        ("cafe", "Cafe"),
        ("natural", "Natural")
    ]

    PRIVACY_CHOICES =[
        ("private", "Private"),
        ("public", "Public")
    ]

    STATUS_CHOICES =[
        ("pending", "Pending"),
        ("active", "Active"),
        ("ended", "Ended"),
        ("cancelled", "Cancelled"),
    ]

    employer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employer_meeting")
    host_email = models.JSONField(default=list, blank=True)

    candidate = models.ForeignKey(settings.AUTH_USER_MODEL,blank=True, null=True, on_delete=models.CASCADE, related_name="candidate_meeting")
    candidate_email = models.EmailField(blank=True, null=True)

    meeting_title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    room_type = models.CharField(max_length=30, choices=ROOM_TYPE_CHOICES, default="interview")
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default="interview")
    environment = models.CharField(max_length=30, choices=ENVIRONMENT_CHOICES, default="office")
    privacy = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default="private")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    enable_recording = models.BooleanField(default=False)
    room_code = models.CharField(max_length=20, unique=True, default=unique_room_code)
    meet_link = models.URLField(max_length=500, null=True, blank=True)
    
    is_deleted = models.BooleanField(default=False)

    @property
    def meeting_date(self):
        if self.start_time:
            return self.start_time.date()
        return None
    
    @property
    def duration(self):
        if self.start_time and self.end_time:
            diff = self.end_time - self.start_time
            return int(diff.total_seconds()//60)
        return None

    class Meta:
        db_table = 'meeting_rooms'
        verbose_name = 'Meeting Room'
        verbose_name_plural = 'Meeting Rooms'
        ordering = ['-created_at']

        indexes = [
            models.Index(fields=['room_code']),
            models.Index(fields=['status']),
            models.Index(fields=['employer']),
        ]

class UserGoogleToken(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_google_token'
        verbose_name = 'User Google Token'
        verbose_name_plural = 'User Google Tokens'
        ordering = ['-created_at']