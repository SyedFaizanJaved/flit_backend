from rest_framework import serializers
from .models import MeetingRoom
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
            
        return data

    class Meta:
        model = MeetingRoom
        exclude = ['room_type', 'environment', 'privacy', 'status', 'enable_recording', 'room_code']
        read_only_fields = ('created_at', 'id', 'meet_link', 'employer', 'meeting_date', 'employer_company')
    
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
        return data
    
    # create room
    def create(self, validated_data):
        return MeetingRoom.objects.create(**validated_data)