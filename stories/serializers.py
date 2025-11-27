from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import Story, Like, Comment, SavedItem
from accounts.serializers import UserListSerializer as UserSerializer


class StorySerializer(serializers.ModelSerializer):
    """
    Serializer for Story model
    """
    user = UserSerializer(read_only=True)
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    target_content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        write_only=True,
        required=False
    )
    target_object_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = Story
        fields = [
            'id', 'user', 'user_type', 'content_type', 
            'text_content', 'image_content', 'video_content',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at',
            'target_content_type', 'target_object_id', 'company', 'candidate'
        ]
        read_only_fields = ['user', 'created_at', 'like_count', 'comment_count', 'is_liked', 'is_saved']
        extra_kwargs = {
            'text_content': {'required': False, 'allow_blank': True},
            'image_content': {'required': False, 'allow_null': True},
            'video_content': {'required': False, 'allow_null': True},
            'content_type': {'required': False},  # Made not required for GET requests
            'user_type': {'required': False}     # Made not required for GET requests
        }
    
    def validate(self, data):
        content_type = data.get('content_type')
        text_content = data.get('text_content')
        image_content = data.get('image_content')
        video_content = data.get('video_content')
        user_type = data.get('user_type')
        company = data.get('company')
        candidate = data.get('candidate')
        
        # Validate content based on content_type
        if content_type == 'text' and not text_content:
            raise serializers.ValidationError({
                'text_content': 'Text content is required for text stories'
            })
            
        if content_type == 'image' and not image_content:
            raise serializers.ValidationError({
                'image_content': 'Image file is required for image stories'
            })
            
        if content_type == 'video' and not video_content:
            raise serializers.ValidationError({
                'video_content': 'Video file is required for video stories'
            })
            
        # Ensure only the relevant content field is provided
        if content_type == 'text' and (image_content or video_content):
            raise serializers.ValidationError({
                'content_type': 'Only text content should be provided for text stories'
            })
            
        if content_type == 'image' and (text_content or video_content):
            raise serializers.ValidationError({
                'content_type': 'Only image content should be provided for image stories'
            })
            
        if content_type == 'video' and (text_content or image_content):
            raise serializers.ValidationError({
                'content_type': 'Only video content should be provided for video stories'
            })
            
        # Validate company/candidate based on user_type
        if user_type == 'employer' and not company:
            raise serializers.ValidationError({
                'company': 'Company is required for employer stories'
            })
            
        if user_type == 'candidate' and not candidate:
            raise serializers.ValidationError({
                'candidate': 'Candidate is required for candidate stories'
            })
            
        # Clean up data
        if 'media_file' in data and content_type == 'text':
            data['media_file'] = None
            
        return data
        
    def create(self, validated_data):
        target_content_type = validated_data.pop('target_content_type', None)
        target_object_id = validated_data.pop('target_object_id', None)
        
        # Get company and candidate from validated_data if they exist
        company = validated_data.pop('company', None)
        candidate = validated_data.pop('candidate', None)
        
        # Clean up content fields based on content_type
        content_type = validated_data.get('content_type')
        if content_type == 'text':
            validated_data['image_content'] = None
            validated_data['video_content'] = None
        elif content_type == 'image':
            validated_data['text_content'] = None
            validated_data['video_content'] = None
        elif content_type == 'video':
            validated_data['text_content'] = None
            validated_data['image_content'] = None
            
        if target_content_type and target_object_id:
            validated_data['content_type'] = target_content_type.model
            validated_data['object_id'] = target_object_id
        
        # Set company and candidate based on user_type
        user_type = validated_data.get('user_type')
        if user_type == 'employer' and company:
            validated_data['company'] = company
        elif user_type == 'candidate' and candidate:
            validated_data['candidate'] = candidate
            
        return super().create(validated_data)
    
    def get_like_count(self, obj):
        return obj.likes.count()
    
    def get_comment_count(self, obj):
        return obj.comments.count()
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(id=request.user.id).exists()
        return False
    
    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.saved_by.filter(id=request.user.id).exists()
        return False


class LikeSerializer(serializers.ModelSerializer):
    """
    Serializer for Like model
    """
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Like
        fields = ['id', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class CommentSerializer(serializers.ModelSerializer):
    """
    Serializer for Comment model
    """
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Comment
        fields = ['id', 'user', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class SavedItemSerializer(serializers.ModelSerializer):
    """
    Serializer for SavedItem model
    """
    content_object = serializers.SerializerMethodField()
    item_type = serializers.CharField(read_only=True)
    
    class Meta:
        model = SavedItem
        fields = ['id', 'content_object', 'item_type', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_content_object(self, obj):
        from stories.serializers_company_project_job import (
            CompanySerializer, ProjectSerializer, JobSerializer
        )
        
        content_object = obj.content_object
        if content_object is None:
            return None
            
        if hasattr(content_object, 'to_dict'):
            return content_object.to_dict()
            
        # Try to serialize based on content type
        if obj.item_type == 'company':
            return CompanySerializer(content_object).data
        elif obj.item_type == 'project':
            return ProjectSerializer(content_object).data
        elif obj.item_type == 'job':
            return JobSerializer(content_object).data
        elif obj.item_type == 'story':
            return StorySerializer(content_object).data
            
        return str(content_object)
