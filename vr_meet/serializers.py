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
    candidate_email = serializers.EmailField(write_only=True, required=False)
    candidate_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='candidate',
        required=False,
        allow_null=True,
        write_only=True
    )
    duration = serializers.ReadOnlyField()
    meeting_date = serializers.ReadOnlyField()

    class Meta:
        model = MeetingRoom
        exclude = ['room_type', 'environment', 'privacy', 'status', 'enable_recording', 'room_code']
        read_only_fields = ('created_at', 'id', 'meet_link', 'employer', 'duration', 'meeting_date')
        
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