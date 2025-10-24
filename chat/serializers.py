from rest_framework import serializers
from .models import ChatMessage, ChatRoom, ChatRoomMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for chat messages
    """
    sender_name = serializers.CharField(source='sender.email', read_only=True)
    recipient_name = serializers.CharField(source='recipient.email', read_only=True)
    
    class Meta:
        model = ChatMessage
        fields = '__all__'
        read_only_fields = ('sender', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)


class ChatMessageListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing chat messages
    """
    sender_name = serializers.CharField(source='sender.email', read_only=True)
    recipient_name = serializers.CharField(source='recipient.email', read_only=True)
    direction = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatMessage
        fields = ('id', 'sender', 'recipient', 'sender_name', 'recipient_name', 'message', 'messageType',
                 'is_read', 'created_at', 'direction')

    def get_direction(self, obj):
        request = self.context.get('request')
        if request and request.user.id == obj.sender.id:
            return 'outgoing' 
        return 'incoming'   


class ChatRoomSerializer(serializers.ModelSerializer):
    """
    Serializer for chat rooms
    """
    created_by_name = serializers.CharField(source='created_by.email', read_only=True)
    participant_count = serializers.SerializerMethodField()
    participant_names = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatRoom
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')
    
    def get_participant_count(self, obj):
        return obj.participants.count()
    
    def get_participant_names(self, obj):
        return [user.email for user in obj.participants.all()]
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        room = super().create(validated_data)
        # Add creator as participant
        room.participants.add(room.created_by)
        return room


class ChatRoomListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing chat rooms
    """
    created_by_name = serializers.CharField(source='created_by.email', read_only=True)
    participant_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatRoom
        fields = ('id', 'name', 'room_type', 'description', 'is_active', 'is_private',
                 'created_by_name', 'participant_count', 'created_at')
    
    def get_participant_count(self, obj):
        return obj.participants.count()


class ChatRoomMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for chat room messages
    """
    sender_name = serializers.CharField(source='sender.email', read_only=True)
    room_name = serializers.CharField(source='room.name', read_only=True)
    
    class Meta:
        model = ChatRoomMessage
        fields = '__all__'
        read_only_fields = ('sender', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)


class ChatRoomMessageListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing chat room messages
    """
    sender_name = serializers.CharField(source='sender.email', read_only=True)
    
    class Meta:
        model = ChatRoomMessage
        fields = ('id', 'sender_name', 'message', 'message_type', 'file_url',
                 'created_at')


class ChatRoomCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating chat rooms
    """
    participant_emails = serializers.ListField(
        child=serializers.EmailField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = ChatRoom
        fields = ('name', 'room_type', 'description', 'is_private', 'participant_emails')
    
    def create(self, validated_data):
        participant_emails = validated_data.pop('participant_emails', [])
        room = super().create(validated_data)
        
        # Add participants
        for email in participant_emails:
            try:
                from accounts.models import User
                user = User.objects.get(email=email)
                room.participants.add(user)
            except User.DoesNotExist:
                pass  # Skip invalid emails
        
        return room


class ChatRoomAddParticipantSerializer(serializers.Serializer):
    """
    Serializer for adding participants to chat rooms
    """
    participant_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=True
    )
    
    def validate_participant_emails(self, value):
        from accounts.models import User
        valid_emails = []
        for email in value:
            try:
                user = User.objects.get(email=email)
                valid_emails.append(user)
            except User.DoesNotExist:
                pass  # Skip invalid emails
        return valid_emails