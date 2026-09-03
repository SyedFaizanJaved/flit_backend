from rest_framework import serializers
from .models import MeetingRoom, Offer
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

User = get_user_model()

class UserNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email']
        read_only_fields = ['id', 'first_name', 'last_name', 'email']

class MeetingRoomSerializer(serializers.ModelSerializer):
    candidate = UserNameSerializer(read_only=True)
    logo = serializers.SerializerMethodField()
    employer_company = serializers.SerializerMethodField()
    candidate_email = serializers.EmailField(write_only=True, required=False)
    candidate_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='candidate',
        required=False,
        allow_null=True,
        write_only=True
    )
    meeting_date = serializers.ReadOnlyField()
    meeting_title = serializers.CharField(required=False, allow_blank=True)

    # Opportunity type (read-only, computed from model property)
    opportunity_type = serializers.ReadOnlyField()

    # Allow setting job/project on creation (write-only integer fields)
    job_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    project_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    # Show offer status if an offer exists for this meeting
    offer_status = serializers.SerializerMethodField()

    # Whether the slot has passed. Read from the model so the cards stop each
    # recomputing it from start_time/end_time and drifting apart.
    is_expired = serializers.ReadOnlyField()


    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        
        # Only include host_email if user is an employer
        if not (request and hasattr(request.user, 'role') and request.user.role.name == 'employer'):
            data.pop('host_email', None)
        # Ensure host_email is properly formatted as a list
        elif 'host_email' in data:
            if isinstance(data['host_email'], str):
                data['host_email'] = [data['host_email']] if data['host_email'] else []
            elif not isinstance(data['host_email'], list):
                data['host_email'] = []  # Convert any other type to empty list

        # Include job/project info in read response
        if instance.job_id:
            data['job'] = {'id': instance.job.id, 'title': instance.job.title}
        else:
            data['job'] = None

        if instance.project_id:
            data['project'] = {'id': instance.project.id, 'title': instance.project.title}
        else:
            data['project'] = None

        return data

    class Meta:
        model = MeetingRoom
        exclude = ['room_type', 'environment', 'privacy', 'status', 'enable_recording', 'room_code']
        read_only_fields = (
            'created_at', 'id', 'meet_link', 'employer',
            'meeting_date', 'employer_company', 'opportunity_type', 'offer_status', 'logo',
            'is_expired',
        )
    
    def get_logo(self, obj):
        request = self.context.get('request')
        if obj.candidate:
            try:
                candidate_profile = obj.candidate.candidate_profile
                if candidate_profile and candidate_profile.profile_image:
                    return request.build_absolute_uri(candidate_profile.profile_image.url) if request else candidate_profile.profile_image.url
            except Exception:
                pass
        return None

    def get_employer_company(self, obj):
        # ponytail: memoised per employer id. This ran Employer.objects.get() once
        # per meeting room, and a meeting list is usually all one employer.
        if not hasattr(self, '_employer_company_cache'):
            self._employer_company_cache = {}
        employer_id = obj.employer_id
        if employer_id not in self._employer_company_cache:
            result = None
            try:
                from employers.models import Employer
                employer = Employer.objects.select_related('company').get(user_id=employer_id)
                if employer.company:
                    result = {
                        'id': employer.company.id,
                        'name': employer.company.company_name,
                        'logo': employer.company.logo.url if employer.company.logo else None
                    }
            except Exception as e:
                print(f"Error getting employer company: {str(e)}")
            self._employer_company_cache[employer_id] = result
        return self._employer_company_cache[employer_id]

    def get_offer_status(self, obj):
        """Return the latest offer status for this meeting. Defaults to 'pending' if no offer exists."""
        # ponytail: picking the newest in Python uses the view's prefetch when there
        # is one and costs a single query when there isn't — .order_by().first()
        # always re-queried, once per row. Same row either way.
        offers = list(obj.offers.all())
        offer = max(offers, key=lambda o: o.created_at) if offers else None
        if offer:
            return {
                'id': offer.id,
                'status': offer.status,
                'title': offer.title,
            }
        return 'pending'

    def validate(self, data):
        data = super().validate(data)
        candidate_email = data.pop('candidate_email', None)
        
        if candidate_email:
            try:
                candidate = User.objects.get(email=candidate_email)
                data['candidate'] = candidate
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'error': 'User with this email does not exist.'
                })
        elif 'candidate' not in data:
            raise serializers.ValidationError({
                'error': 'Either candidate_id or candidate_email is required.'
            })
            
        # Time validation
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError("End time must be greater than start time")

        # An interview scheduled into the past is already over the moment it is created:
        # it showed up as pending with a live Join button. Only rejected when the time is
        # actually being set or changed, so editing other fields on a past meeting -- or
        # rescheduling one -- is not blocked by its own stored value.
        if start_time and start_time < timezone.now():
            if self.instance is None or self.instance.start_time != start_time:
                raise serializers.ValidationError({
                    'start_time': 'Interview cannot be scheduled in the past.'
                })

        # One candidate must not be bookable twice by the same employer at the same
        # instant -- nothing stopped it before, so a double submit (or a second pass
        # through the schedule modal) produced two identical cards side by side.
        #
        # Scoped to this employer's own rooms on purpose: another company's booking is
        # not ours to reveal, and a candidate double-booked across two companies is a
        # clash only they can see. Cancelled and ended rooms do not count -- rebooking
        # a slot that was called off is exactly what an employer would expect to do.
        candidate = data.get('candidate') or getattr(self.instance, 'candidate', None)
        employer = getattr(self.context.get('request'), 'user', None)
        if start_time and candidate and employer and employer.is_authenticated:
            clash = MeetingRoom.objects.filter(
                employer=employer,
                candidate=candidate,
                start_time=start_time,
                is_deleted=False,
            ).exclude(status__in=['ended', 'cancelled'])
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError({
                    'start_time': 'This candidate already has an interview with you at '
                                  'that date and time.'
                })

        # hosts email validation
        host_emails = data.get('host_email', []) or []
        if isinstance(host_emails,str):
            host_emails = [host_emails]
        
        if not isinstance(host_emails,(list,tuple)):
            raise serializers.ValidationError("Host email must be a list")
        
        for email in host_emails:
            try:
                validate_email(email)
            except ValidationError:
                raise serializers.ValidationError(f"Invalid email {email}")

        # Resolve job_id / project_id integer fields to FK instances
        job_id = data.pop('job_id', None)
        project_id = data.pop('project_id', None)

        if job_id and project_id:
            raise serializers.ValidationError(
                "A meeting can be linked to either a job or a project, not both."
            )

        if job_id:
            from jobs.models import Job
            try:
                data['job'] = Job.objects.get(pk=job_id)
            except Job.DoesNotExist:
                raise serializers.ValidationError({'job_id': f'Job with id {job_id} does not exist.'})

        if project_id:
            from projects.models import Project
            try:
                data['project'] = Project.objects.get(pk=project_id)
            except Project.DoesNotExist:
                raise serializers.ValidationError({'project_id': f'Project with id {project_id} does not exist.'})

        return data
    
    # create room
    def create(self, validated_data):
        return MeetingRoom.objects.create(**validated_data)


# -----------------------------------------------
#  Offer Serializers
# -----------------------------------------------

class OfferSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and listing Offers.
    """
    candidate_name = serializers.SerializerMethodField()
    employer_name = serializers.SerializerMethodField()
    meeting_title = serializers.CharField(source='meeting.meeting_title', read_only=True)
    opportunity_type = serializers.CharField(source='meeting.opportunity_type', read_only=True)
    job = serializers.ReadOnlyField(default=None)
    project = serializers.ReadOnlyField(default=None)
    company_logo = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            'id', 'meeting', 'candidate', 'employer',
            'title', 'description', 'status', 'is_read',
            'salary', 'hourly_rate', 'is_hourly',
            'offer_date', 'date_of_joining',
            'candidate_name', 'employer_name', 'company_logo', 'meeting_title', 'opportunity_type',
            'job', 'project',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'employer', 'offer_date', 'status',
            'candidate_name', 'employer_name', 'company_logo', 'meeting_title', 'opportunity_type',
            'created_at', 'updated_at',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        meeting = getattr(instance, 'meeting', None)
        
        # Include job/project info if available through the meeting
        data['job'] = None
        data['project'] = None
        
        if meeting:
            if meeting.job_id:
                data['job'] = {
                    'id': meeting.job.id, 
                    'title': meeting.job.title,
                    'type': 'job'
                }
            if meeting.project_id:
                data['project'] = {
                    'id': meeting.project.id, 
                    'title': meeting.project.title,
                    'type': 'project'
                }
        
        # Add a clear 'type' tag at the root level as well
        opportunity_type = meeting.opportunity_type if meeting else 'unknown'
        
        # Fallback logic: If meeting has no job/project, try to infer from candidate's applications
        if opportunity_type == 'unknown' and instance.candidate and instance.employer:
            from applications.models import JobApplication, ProjectApplication
            
            # ponytail: was exists() + first() + a lazy .job/.project load per offer —
            # 4 queries where 2 do the same work. first() is None exactly when
            # exists() was False, and select_related pulls the job/project with it.
            p_app = ProjectApplication.objects.filter(
                candidate__user=instance.candidate, employer=instance.employer
            ).select_related('project').first()
            has_project_apps = p_app is not None

            j_app = JobApplication.objects.filter(
                candidate__user=instance.candidate, employer=instance.employer
            ).select_related('job').first()
            has_job_apps = j_app is not None

            if has_job_apps and not has_project_apps:
                opportunity_type = 'job'
                data['job'] = {'id': j_app.job.id, 'title': j_app.job.title, 'type': 'job'}
            elif has_project_apps and not has_job_apps:
                opportunity_type = 'project'
                data['project'] = {'id': p_app.project.id, 'title': p_app.project.title, 'type': 'project'}
            elif has_job_apps and has_project_apps:
                # If both exist, try to match by title (brittle but better than nothing)
                # For now just default to job
                opportunity_type = 'job'
                data['job'] = {'id': j_app.job.id, 'title': j_app.job.title, 'type': 'job'}

        data['opportunity_type'] = opportunity_type
                
        return data

    def get_candidate_name(self, obj):
        return obj.candidate.get_full_name() or obj.candidate.email

    def get_employer_name(self, obj):
        return obj.employer.get_full_name() or obj.employer.email

    def get_company_logo(self, obj):
        # ponytail: memoised per employer id. This ran Employer.objects.get() once
        # per offer, and on an employer's dashboard every offer shares the same
        # employer — 5 identical queries for one logo.
        if not hasattr(self, '_company_logo_cache'):
            self._company_logo_cache = {}
        employer_id = obj.employer_id
        if employer_id not in self._company_logo_cache:
            logo = None
            try:
                from employers.models import Employer
                profile = Employer.objects.select_related('company').get(user_id=employer_id)
                if profile.company and profile.company.logo:
                    logo = profile.company.logo.url
            except Exception:
                pass
            self._company_logo_cache[employer_id] = logo
        return self._company_logo_cache[employer_id]

    def validate_meeting(self, meeting):
        """Ensure the meeting exists and is not deleted."""
        if meeting.is_deleted:
            raise serializers.ValidationError("Cannot create an offer for a deleted meeting.")
        return meeting

    def validate(self, data):
        request = self.context.get('request')
        meeting = data.get('meeting')

        # Ensure only the meeting's employer can create offers
        if meeting and request:
            if meeting.employer != request.user:
                raise serializers.ValidationError(
                    "Only the employer who hosted the meeting can create an offer."
                )

        # Ensure the candidate is actually part of the meeting
        candidate = data.get('candidate')
        if meeting and candidate and meeting.candidate != candidate:
            raise serializers.ValidationError(
                "The candidate must be a participant of the specified meeting."
            )

        # Compensation validation
        is_hourly = data.get('is_hourly', False)
        salary = data.get('salary')
        hourly_rate = data.get('hourly_rate')
        if is_hourly and not hourly_rate:
            raise serializers.ValidationError({
                'hourly_rate': 'Hourly rate is required when is_hourly is True.'
            })
        if not is_hourly and not salary:
            raise serializers.ValidationError({
                'salary': 'Salary is required when is_hourly is False.'
            })

        return data


class RejectCandidateSerializer(serializers.Serializer):
    """
    Serializer for rejecting a candidate by meeting_id.
    """
    meeting_id = serializers.IntegerField(
        help_text="ID of the meeting whose candidate should be rejected."
    )