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

    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    candidates = models.ManyToManyField(settings.AUTH_USER_MODEL,blank=True, related_name="candidate_meetings")
    
    room_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    room_type = models.CharField(max_length=30, choices=ROOM_TYPE_CHOICES, default="interview")
    environment = models.CharField(max_length=30, choices=ENVIRONMENT_CHOICES, default="office")
    privacy = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default="private")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    max_participants = models.IntegerField(validators=[MinValueValidator(2), MaxValueValidator(20)], default=2)

    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    enable_recording = models.BooleanField(default=False)
    room_code = models.CharField(max_length=20, unique=True, default=unique_room_code)
    meet_link = models.URLField(max_length=500, null=True, blank=True)
    
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = 'meeting_rooms'
        verbose_name = 'Meeting Room'
        verbose_name_plural = 'Meeting Rooms'
        ordering = ['-created_at']

        indexes = [
            models.Index(fields=['room_code']),
            models.Index(fields=['status']),
            models.Index(fields=['creator']),
        ]