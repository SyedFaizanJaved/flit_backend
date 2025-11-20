from rest_framework import serializers
from .models import MeetingRoom
from django.contrib.auth import get_user_model

User = get_user_model()

class MeetingRoomSerializer(serializers.ModelSerializer):
    candidates = serializers.PrimaryKeyRelatedField(many=True,queryset=User.objects.all(),required=False)

    class Meta:
        model = MeetingRoom
        fields = '__all__'
        read_only_fields = ('created_at','id','room_code','meet_link','creator')

    # max participants validation
    def validate_max_participants(self, value):
        if value < 2 or value > 20:
            raise serializers.ValidationError("Max participants must be between 2 and 20")
        return value
    
    # time validation
    def validate(self, data):
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError("End time must be greater than start time")
        return data
    
    # create room
    def create(self, validated_data):
        candidates = validated_data.pop('candidates',[])
        room = MeetingRoom.objects.create(**validated_data)
        room.candidates.set(candidates)
        return room