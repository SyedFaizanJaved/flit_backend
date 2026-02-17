from rest_framework import serializers
from .models import ChatMessage, ChatRoom, ChatRoomMessage
from candidates.models import Candidate
from utils.timezone_helpers import format_datetime_for_user

class EmployerConversationSummarySerializer(serializers.ModelSerializer):
    """
    Serializer for listing candidates that an employer has chatted with.
    Shows candidate details like name, title, profile image, etc.
    """
    user_id = serializers.IntegerField(source='user.id')
    full_name = serializers.SerializerMethodField()
    title = serializers.CharField(allow_null=True)
    profile_image = serializers.SerializerMethodField()
    last_message_time = serializers.DateTimeField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Candidate
        fields = ('user_id', 'full_name', 'title', 'profile_image', 'last_message_time', 'unread_count')
    
    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"
        
    def get_profile_image(self, obj):
        if obj.profile_image:
            return obj.profile_image.url
        return None



class CandidateConversationSummarySerializer(serializers.ModelSerializer):
    """
    Serializer for listing candidates that an employer has chatted with.
    Used on the employer side to list candidates they have chatted with.
    Shows candidate details like name, title, profile image, etc.
    """
    id = serializers.IntegerField(source='id', read_only=True)
    name = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    last_seen = serializers.DateTimeField(source='last_login', read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        from django.contrib.auth import get_user_model
        model = get_user_model()
        fields = (
            'id', 'name', 'title', 'profile_image', 
            'last_seen', 'last_message_time', 'unread_count'
        )
    
    def get_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    
    def get_title(self, obj):
        try:
            return obj.candidate_profile.title
        except:
            return None
    
    def get_profile_image(self, obj):
        try:
            if hasattr(obj, 'candidate_profile') and obj.candidate_profile.profile_image:
                return obj.candidate_profile.profile_image.url
        except:
            pass
        return None
    
    def get_candidate_info(self, obj):
        """Helper method to get candidate info"""
        from candidates.models import Candidate
        try:
            candidate = Candidate.objects.get(user=obj)
            return {
                'name': f"{candidate.user.first_name} {candidate.user.last_name}",
                'title': candidate.title,
                'profile_image': candidate.profile_image.url if candidate.profile_image else None
            }
        except Candidate.DoesNotExist:
            return {
                'name': f"{obj.first_name} {obj.last_name}" if obj.first_name or obj.last_name else obj.email,
                'title': 'No title',
                'profile_picture': None
            }
    
    def get_name(self, obj):
        return self.get_candidate_info(obj)['name']
    
    def get_title(self, obj):
        return self.get_candidate_info(obj)['title']
    
    def get_profile_picture(self, obj):
        return self.get_candidate_info(obj)['profile_picture']


class EmployerCompanyConversationSummarySerializer(serializers.Serializer):
    """
    Unified serializer for the candidate inbox.
    It returns conversation participants (employers or candidates) using the
    same structure that the frontend already consumes.
    """
    id = serializers.IntegerField(read_only=True)
    company_name = serializers.SerializerMethodField()
    company_id = serializers.SerializerMethodField()
    industry = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()
    last_message_time = serializers.DateTimeField(allow_null=True)
    last_seen = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField()
    
    def _build_absolute_uri(self, path):
        """Helper to build absolute URLs when request context is available."""
        request = self.context.get('request')
        if request and path:
            return request.build_absolute_uri(path)
        return path
    
    def _get_employer_profile(self, obj):
        # First try to get employer_profile directly
        employer = getattr(obj, 'employer_profile', None)
        
        # If not found, try to get through user relation
        if not employer and hasattr(obj, 'user'):
            employer = getattr(obj.user, 'employer_profile', None)
            
        # If still not found, try to get employer through candidate's user (for reverse lookups)
        if not employer and hasattr(obj, 'candidate_profile'):
            candidate = obj.candidate_profile
            if hasattr(candidate, 'user'):
                employer = getattr(candidate.user, 'employer_profile', None)
                
        return employer
    
    def _get_candidate_profile(self, obj):
        # First try to get candidate_profile directly
        candidate = getattr(obj, 'candidate_profile', None)
        
        # If not found, try to get through user relation
        if not candidate and hasattr(obj, 'user'):
            candidate = getattr(obj.user, 'candidate_profile', None)
            
        # If still not found, try to get candidate through employer's user (for reverse lookups)
        if not candidate and hasattr(obj, 'employer_profile'):
            employer = obj.employer_profile
            if hasattr(employer, 'user'):
                candidate = getattr(employer.user, 'candidate_profile', None)
                
        return candidate
    
    def get_company_name(self, obj):
        try:
            # Check if this is an employer with company
            employer = self._get_employer_profile(obj)
            if employer:
                # If employer has a company
                if hasattr(employer, 'company') and employer.company:
                    return getattr(employer.company, 'company_name', None) or \
                           getattr(employer.company, 'name', 'Company')
                
                # If no company but has name fields
                if hasattr(employer, 'full_name') and employer.full_name:
                    return employer.full_name.strip()
                if hasattr(employer, 'first_name') or hasattr(employer, 'last_name'):
                    return f"{getattr(employer, 'first_name', '')} {getattr(employer, 'last_name', '')}".strip()
            
            # Check if this is a candidate
            candidate = self._get_candidate_profile(obj)
            if candidate:
                if hasattr(candidate, 'full_name') and candidate.full_name:
                    return candidate.full_name.strip()
                if hasattr(candidate, 'first_name') or hasattr(candidate, 'last_name'):
                    return f"{getattr(candidate, 'first_name', '')} {getattr(candidate, 'last_name', '')}".strip()
            
            # Fallback to user's name or email
            if hasattr(obj, 'get_full_name') and obj.get_full_name():
                return obj.get_full_name().strip()
            if hasattr(obj, 'email'):
                return obj.email
                
        except Exception as e:
            print(f"Error in get_company_name: {str(e)}")
            
        return 'User'
        
    def get_company_id(self, obj):
        try:
            employer = self._get_employer_profile(obj)
            if employer and hasattr(employer, 'company') and employer.company:
                return employer.company.id
            return None
        except Exception as e:
            print(f"Error in get_company_id: {str(e)}")
            return None
    
    def get_industry(self, obj):
        try:
            # Check if this is an employer with company
            employer = self._get_employer_profile(obj)
            if employer:
                # If employer has a company with industry
                if hasattr(employer, 'company') and employer.company:
                    industry = getattr(employer.company, 'industry', None)
                    if industry:
                        return industry
                
                # Fallback to position or default
                return getattr(employer, 'position', 'Employer')
            
            # Check if this is a candidate
            candidate = self._get_candidate_profile(obj)
            if candidate:
                if hasattr(candidate, 'title') and candidate.title:
                    return candidate.title
                return 'Candidate'
            
            # Fallback to role or user type
            if hasattr(obj, 'role') and obj.role and hasattr(obj.role, 'name'):
                return obj.role.name
            if hasattr(obj, 'user_type'):
                return str(obj.user_type).capitalize()
                
        except Exception as e:
            print(f"Error in get_industry: {str(e)}")
            
        return 'User'
    
    def get_logo(self, obj):
        try:
            # First try to get employer logo
            employer = self._get_employer_profile(obj)
            if employer:
                try:
                    # Try to get company logo first
                    if (hasattr(employer, 'company') and employer.company and 
                        hasattr(employer.company, 'logo') and employer.company.logo):
                        logo_url = getattr(employer.company.logo, 'url', None)
                        if logo_url:
                            return self._build_absolute_uri(logo_url)
                    
                    # Fall back to employer's profile picture
                    if hasattr(employer, 'profile_picture') and employer.profile_picture:
                        profile_pic_url = getattr(employer.profile_picture, 'url', None)
                        if profile_pic_url:
                            return self._build_absolute_uri(profile_pic_url)
                            
                except Exception as e:
                    print(f"Error getting employer logo for user {getattr(obj, 'id', 'unknown')}: {str(e)}")
            
            # If no employer logo found, try candidate profile image
            candidate = self._get_candidate_profile(obj)
            if candidate:
                try:
                    if hasattr(candidate, 'profile_image') and candidate.profile_image:
                        profile_img_url = getattr(candidate.profile_image, 'url', None)
                        if profile_img_url:
                            return self._build_absolute_uri(profile_img_url)
                except Exception as e:
                    print(f"Error getting candidate profile image for user {getattr(obj, 'id', 'unknown')}: {str(e)}")
            
            # If we have a user object with a profile picture
            user = getattr(obj, 'user', obj)
            if hasattr(user, 'profile_picture') and user.profile_picture:
                try:
                    user_pic_url = getattr(user.profile_picture, 'url', None)
                    if user_pic_url:
                        return self._build_absolute_uri(user_pic_url)
                except Exception as e:
                    print(f"Error getting user profile image: {str(e)}")
                    
        except Exception as e:
            print(f"Unexpected error in get_logo for user {getattr(obj, 'id', 'unknown')}: {str(e)}")
            
        # Return None if no logo/image found
        return None
    
    def get_last_seen(self, obj):
        return getattr(obj, 'last_login', None)
    
    # Removed entity_type field as per requirement
        return 'user'

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
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user
            if instance.created_at:
                data['created_at'] = format_datetime_for_user(instance.created_at, user)
        return data


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