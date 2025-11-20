from rest_framework import serializers
from .models import MeetingRoom
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

User = get_user_model()

class MeetingRoomSerializer(serializers.ModelSerializer):
    candidate = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(),required=False,
    allow_null=True)
    duration = serializers.ReadOnlyField()
    meeting_date = serializers.ReadOnlyField()

    class Meta:
        model = MeetingRoom
        fields = '__all__'
        read_only_fields = ('created_at','id','room_code','meet_link','employer','duration','meeting_date')
    
    def validate(self, data):
        # time validation
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError("End time must be greater than start time")
        
        # hosts email validation
        host_emails = data.get('host_email',[]) or []
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