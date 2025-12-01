from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from companies.models import Company
from projects.models import Project
from jobs.models import Job
from candidates.models import Candidate, Education, Experience, Achievement
from .models import Comment, Like, SavedItem
from accounts.serializers import UserListSerializer as UserSerializer

class CommentSerializer(serializers.ModelSerializer):
    """
    Serializer for comments on companies, projects, jobs, and candidates
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
            'id', 'user', 'user_id', 'content', 'created_at', 'updated_at',
            'company', 'project', 'job', 'candidate'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'user']
        extra_kwargs = {
            'company': {'write_only': True, 'required': False},
            'project': {'write_only': True, 'required': False},
            'job': {'write_only': True, 'required': False},
            'candidate': {'write_only': True, 'required': False},
        }
    
    def validate(self, data):
        # Ensure only one entity is being commented on
        entity_count = sum([
            'company' in data,
            'project' in data,
            'job' in data,
            'candidate' in data
        ])
        
        if entity_count != 1:
            raise serializers.ValidationError("A comment must reference exactly one entity (company, project, job, or candidate)")
        
        return data


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
            'size', 'location', 'values', 'is_verified', 'is_active','total_employees',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at', 'updated_at'
        ]


class CompanyBasicSerializer(serializers.ModelSerializer):
    """
    Basic company serializer that only includes id and name
    """
    class Meta:
        model = Company
        fields = ['id', 'company_name']

class ProjectSerializer(serializers.ModelSerializer):
    """
    Project serializer with interaction data
    """
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    project_id = serializers.IntegerField(source='id', read_only=True)
    company = CompanyBasicSerializer()
    
    class Meta:
        model = Project
        fields = [
            'project_id', 'title', 'description', 'category', 'paymentType', 'paymentAmount',
            'estimatedHours', 'deadline', 'status', 'company', 'created_at',
            'like_count', 'comment_count', 'is_liked', 'is_saved'
        ]
        read_only_fields = ['created_at']
    
    def get_like_count(self, obj):
        from stories.models import Like
        return Like.objects.filter(project_id=obj.id).count()
    
    def get_comment_count(self, obj):
        from stories.models import Comment
        from django.db.models import Q
        # Count both direct comments and story comments
        direct_comments = Comment.objects.filter(project=obj).count()
        story_comments = Comment.objects.filter(story__project=obj).count()
        return direct_comments + story_comments
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from stories.models import Like
            return Like.objects.filter(
                project_id=obj.id,
                user=request.user
            ).exists()
        return False
    
    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from stories.models import SavedItem
            return SavedItem.objects.filter(
                project_id=obj.id,
                user=request.user,
                item_type='project'
            ).exists()
        return False


class JobSerializer(serializers.ModelSerializer):
    """
    Job serializer with interaction data
    """
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    job_id = serializers.IntegerField(source='id', read_only=True)
    
    class Meta:
        model = Job
        fields = [
            'job_id', 'title', 'description', 'employmentType', 'location', 'salaryRangeMin', 'salaryRangeMax',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at', 'skills', 'applicationDeadline'
        ]
    
    def get_like_count(self, obj):
        from stories.models import Like
        return Like.objects.filter(job_id=obj.id).count()
    
    def get_comment_count(self, obj):
        from stories.models import Comment
        from django.db.models import Q
        # Count both direct comments and story comments
        direct_comments = Comment.objects.filter(job=obj).count()
        story_comments = Comment.objects.filter(story__job=obj).count()
        return direct_comments + story_comments
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from stories.models import Like
            return Like.objects.filter(
                job_id=obj.id,
                user=request.user
            ).exists()
        return False
    
    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from stories.models import SavedItem
            return SavedItem.objects.filter(
                job_id=obj.id,
                user=request.user,
                item_type='job'
            ).exists()
        return False


class CandidateSerializer(serializers.ModelSerializer):
    """
    Candidate serializer with interaction data
    """
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    candidate_id = serializers.IntegerField(source='id', read_only=True)
    
    class Meta:
        model = Candidate
        fields = [
            'candidate_id', 'full_name', 'title', 'bio', 'location',
            'work_style', 'is_available', 'availability_type',
            'skills', 'seniority_level','min_salary', 'max_salary', 'salary_currency', 'profile_image',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at'
        ]
        read_only_fields = ['created_at']
    
    def get_like_count(self, obj):
        return Like.objects.filter(candidate_id=obj.id).count()
    
    def get_comment_count(self, obj):
        from stories.models import Comment
        # Count both direct comments and story comments
        direct_comments = Comment.objects.filter(candidate=obj).count()
        story_comments = Comment.objects.filter(story__candidate=obj).count()
        return direct_comments + story_comments
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Like.objects.filter(
                candidate_id=obj.id,
                user=request.user
            ).exists()
        return False
    
    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return SavedItem.objects.filter(
                candidate_id=obj.id,
                user=request.user,
                item_type='candidate'
            ).exists()
        return False
