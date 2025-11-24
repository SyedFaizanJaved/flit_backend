from rest_framework import serializers
from companies.models import Company
from projects.models import Project
from jobs.models import Job
from .models import Comment, Like, SavedItem
from accounts.serializers import UserListSerializer as UserSerializer

class CommentSerializer(serializers.ModelSerializer):
    """
    Serializer for comments on companies, projects, and jobs
    """
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source='user',
        read_only=True,
        default=serializers.CurrentUserDefault()
    )
    
    class Meta:
        model = Comment
        fields = [
            'id', 'user', 'user_id', 'content', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LikeSerializer(serializers.ModelSerializer):
    """
    Serializer for likes on companies, projects, and jobs
    """
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Like
        fields = ['id', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class SavedItemSerializer(serializers.ModelSerializer):
    """
    Serializer for saved items
    """
    class Meta:
        model = SavedItem
        fields = ['id', 'item_type', 'created_at']
        read_only_fields = ['id', 'created_at']


class CompanySerializer(serializers.ModelSerializer):
    """
    Company serializer with interaction data
    """
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    company_id = serializers.IntegerField(source='id', read_only=True)
    
    class Meta:
        model = Company
        fields = [
            'company_id', 'company_name', 'description', 'website', 'logo', 'industry',
            'size', 'location', 'values', 'is_verified', 'is_active',
            'total_jobs', 'total_projects', 'total_hires', 'total_employees',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at', 'updated_at'
        ]


class ProjectSerializer(serializers.ModelSerializer):
    """
    Project serializer with interaction data
    """
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    project_id = serializers.IntegerField(source='id', read_only=True)
    
    class Meta:
        model = Project
        fields = [
            'project_id', 'title', 'description', 'budget_min', 'budget_max', 'budget_currency',
            'deadline', 'work_style', 'is_budget_negotiable', 'estimatedHours',
            'is_timeline_flexible', 'required_skills', 'technologies',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at'
        ]
        read_only_fields = ['created_at']
        depth = 1


class JobSerializer(serializers.ModelSerializer):
    """
    Job serializer with interaction data
    """
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    job_id = serializers.IntegerField(source='id', read_only=True)
    
    class Meta:
        model = Job
        fields = [
            'job_id', 'title', 'description', 'employmentType', 'location', 'salaryRangeMin', 'salaryRangeMax',
            'like_count', 'comment_count', 'is_liked', 'is_saved'
        ]
