from rest_framework import serializers
from .models import MeetingRoom, Offer
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

User = get_user_model()

class UserNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email']
        read_only_fields = ['id', 'first_name', 'last_name', 'email']

class MeetingRoomSerializer(serializers.ModelSerializer):
    candidate = UserNameSerializer(read_only=True)
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
        exclude = ['room_type', 'environment', 'privacy', 'status', 'enable_recording', 'room_code', 'job', 'project']
        read_only_fields = (
            'created_at', 'id', 'meet_link', 'employer',
            'meeting_date', 'employer_company', 'opportunity_type', 'offer_status',
        )
    
    def get_employer_company(self, obj):
        try:
            from employers.models import Employer
            employer = Employer.objects.get(user=obj.employer)
            if employer.company:
                return {
                    'id': employer.company.id,
                    'name': employer.company.company_name,
                    'logo': employer.company.logo.url if employer.company.logo else None
                }
        except Exception as e:
            print(f"Error getting employer company: {str(e)}")
        return None

    def get_offer_status(self, obj):
        """Return the latest offer status for this meeting. Defaults to 'pending' if no offer exists."""
        offer = obj.offers.order_by('-created_at').first()
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

    class Meta:
        model = Offer
        fields = [
            'id', 'meeting', 'candidate', 'employer',
            'title', 'description', 'status',
            'salary', 'hourly_rate', 'is_hourly',
            'offer_date', 'date_of_joining',
            'candidate_name', 'employer_name', 'meeting_title', 'opportunity_type',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'employer', 'offer_date', 'status',
            'candidate_name', 'employer_name', 'meeting_title', 'opportunity_type',
            'created_at', 'updated_at',
        ]

    def get_candidate_name(self, obj):
        return obj.candidate.get_full_name() or obj.candidate.email

    def get_employer_name(self, obj):
        return obj.employer.get_full_name() or obj.employer.email

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