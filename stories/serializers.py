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
            'id', 'user', 'content_type', 'content', 'media_file', 'is_active',
            'created_at', 'updated_at', 'like_count', 'comment_count',
            'is_liked', 'is_saved', 'target_content_type', 'target_object_id'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'user']
        
    def create(self, validated_data):
        target_content_type = validated_data.pop('target_content_type', None)
        target_object_id = validated_data.pop('target_object_id', None)
        
        story = Story.objects.create(**validated_data)
        
        if target_content_type and target_object_id:
            story.target_content_type = target_content_type
            story.target_object_id = target_object_id
            story.save()
            
        return story
    
    def get_like_count(self, obj):
        return obj.likes.count()
    
    def get_comment_count(self, obj):
        return obj.comments.count()
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False
    
    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.saved_by.filter(user=request.user).exists()
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
