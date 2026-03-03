from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.conf import settings
from django.utils import timezone
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
    """
    Represents a virtual meeting room for interviews, networking, or casual calls.
    Can be optionally linked to a specific Job or Project opportunity.
    """
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

    # Optional link to Job or Project for tracking which opportunity the meeting is for
    job = models.ForeignKey(
        'jobs.Job',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='meetings',
        help_text="The job this meeting is associated with (if any)."
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='meetings',
        help_text="The project this meeting is associated with (if any)."
    )

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

    @property
    def opportunity_type(self):
        """Returns the type of opportunity linked to this meeting."""
        if self.job_id:
            return "job"
        elif self.project_id:
            return "project"
        return "unknown"

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

    def __str__(self):
        return f"{self.meeting_title} ({self.room_code})"


class Offer(models.Model):
    """
    Represents a hire/reject offer linked to a meeting.
    An employer can create an offer for a candidate after (or during) a meeting.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    meeting = models.ForeignKey(
        MeetingRoom,
        on_delete=models.CASCADE,
        related_name='offers',
        help_text="The meeting this offer originated from."
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_offers',
        help_text="The candidate receiving this offer."
    )
    employer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_offers',
        help_text="The employer who created this offer."
    )

    # Offer details
    title = models.CharField(max_length=255, help_text="Offer title / position name.")
    description = models.TextField(blank=True, default='', help_text="Additional details about the offer.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Compensation
    salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Annual or fixed salary amount."
    )
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hourly rate (if applicable)."
    )
    is_hourly = models.BooleanField(
        default=False,
        help_text="True if compensation is hourly-based, False for salary-based."
    )

    # Dates
    offer_date = models.DateField(auto_now_add=True)
    date_of_joining = models.DateField(
        null=True,
        blank=True,
        help_text="Expected date of joining."
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offers'
        verbose_name = 'Offer'
        verbose_name_plural = 'Offers'
        ordering = ['-created_at']
        # Prevent duplicate offers for the same candidate-meeting combination
        constraints = [
            models.UniqueConstraint(
                fields=['candidate', 'meeting'],
                name='unique_candidate_meeting_offer'
            ),
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['employer', 'status']),
            models.Index(fields=['candidate', 'status']),
        ]

    def __str__(self):
        return f"Offer: {self.title} → {self.candidate} ({self.status})"


class UserGoogleToken(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_google_token'
        verbose_name = 'User Google Token'
        verbose_name_plural = 'User Google Tokens'
        ordering = ['-created_at']