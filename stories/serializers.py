# stories/serializers.py (Updated with Fixed Comment Validation)

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Story, Like, Comment, SavedItem, SavedStory
from companies.models import Company
from projects.models import Project, ProjectSkill
from jobs.models import Job
from candidates.models import Candidate
from accounts.serializers import UserListSerializer as UserSerializer


class CommentUserSerializer(serializers.ModelSerializer):
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ['id', 'first_name', 'last_name', 'email', 'profile_image']

    def get_profile_image(self, obj):
        if hasattr(obj, 'candidate_profile') and obj.candidate_profile.profile_image:
            return obj.candidate_profile.profile_image.url
        return None


class StorySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)

    class Meta:
        model = Story
        fields = [
            'id', 'user', 'user_type', 'content_type', 'text_content', 'image_content', 'video_content',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at', 'company', 'candidate'
        ]
        read_only_fields = ['user', 'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at']


class CommentSerializer(serializers.ModelSerializer):
    user = CommentUserSerializer(read_only=True)

    # Explicitly add 'story' as write_only field (allows it in payload if sent)
    story = serializers.PrimaryKeyRelatedField(
        queryset=Story.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Comment
        fields = [
            'id', 'user', 'content', 'created_at', 'updated_at',
            'company', 'project', 'job', 'candidate', 'story'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']
        extra_kwargs = {
            'company': {'write_only': True, 'required': False, 'allow_null': True},
            'project': {'write_only': True, 'required': False, 'allow_null': True},
            'job': {'write_only': True, 'required': False, 'allow_null': True},
            'candidate': {'write_only': True, 'required': False, 'allow_null': True},
            'story': {'write_only': True, 'required': False, 'allow_null': True},
        }

    def validate(self, data):
        # All possible entities including story
        entities = ['story', 'company', 'project', 'job', 'candidate']
        provided_count = sum(1 for field in entities if data.get(field) is not None)

        if provided_count > 1:
            raise serializers.ValidationError(
                "Comment cannot be associated with more than one entity."
            )
        # Allow 0 or 1 entity from frontend (view will set exactly one)
        return data


class SavedItemSerializer(serializers.ModelSerializer):
    content_object = serializers.SerializerMethodField()
    item_type = serializers.CharField(read_only=True)

    class Meta:
        model = SavedItem
        fields = ['id', 'content_object', 'item_type', 'created_at']

    def get_content_object(self, obj):
        if obj.item_type == 'company' and obj.company_id:
            company = Company.objects.get(id=obj.company_id)
            return CompanySerializer(company, context=self.context).data
        if obj.item_type == 'project' and obj.project_id:
            project = Project.objects.get(id=obj.project_id)
            return ProjectSerializer(project, context=self.context).data
        if obj.item_type == 'job' and obj.job_id:
            job = Job.objects.get(id=obj.job_id)
            return JobSerializer(job, context=self.context).data
        if obj.item_type == 'candidate' and obj.candidate_id:
            candidate = Candidate.objects.get(id=obj.candidate_id)
            return CandidateSerializer(candidate, context=self.context).data
        return None


class CompanyBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'company_name']


class CompanySerializer(serializers.ModelSerializer):
    company_id = serializers.IntegerField(source='id', read_only=True)
    
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)

    class Meta:
        model = Company
        fields = [
            'company_id', 'id', 'company_name', 'description', 'website', 'logo', 'industry',
            'size', 'location', 'values', 'is_verified', 'is_active', 'total_employees',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at'
        ]


class ProjectSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(source='id', read_only=True)
    
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    
    company = CompanyBasicSerializer(read_only=True)
    skills = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'project_id', 'id', 'title', 'description', 'category', 'paymentType', 'paymentAmount',
            'estimatedHours', 'deadline', 'status', 'company', 'created_at',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'skills'
        ]

    def get_skills(self, obj):
        return list(ProjectSkill.objects.filter(project=obj).values_list('name', flat=True))


class JobSerializer(serializers.ModelSerializer):
    job_id = serializers.IntegerField(source='id', read_only=True)

    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)

    class Meta:
        model = Job
        fields = [
            'job_id', 'id', 'title', 'description', 'employmentType', 'location', 'salaryRangeMin', 'salaryRangeMax',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at','status', 'skills', 'applicationDeadline'
        ]


class CandidateSerializer(serializers.ModelSerializer):
    candidate_id = serializers.IntegerField(source='id', read_only=True)

    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    profile_completed = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            'candidate_id', 'id', 'full_name', 'title', 'bio', 'location', 'work_style', 'is_available',
            'availability_type', 'skills', 'seniority_level', 'min_salary', 'max_salary',
            'salary_currency', 'profile_image', 'like_count', 'comment_count',
            'is_liked', 'is_saved', 'created_at', 'user_id', 'profile_completed'
        ]

    def get_profile_completed(self, obj):
        return all([
            bool(getattr(obj, 'basic_info_completed', False)),
            bool(getattr(obj, 'work_preferences_completed', False)),
            bool(getattr(obj, 'skills_completed', False)),
            bool(getattr(obj, 'portfolio_completed', False)),
            bool(getattr(obj, 'privacy_completed', False)),
        ])