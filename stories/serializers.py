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
    user = serializers.SerializerMethodField()
    
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

    CONTENT_FIELDS = {'text': 'text_content', 'image': 'image_content', 'video': 'video_content'}

    def validate(self, data):
        """
        A story must carry the content its content_type promises. Without this a
        failed media upload (or a client that skips the file) saved a row with a
        null image_content/video_content, which rendered as a blank story.
        """
        content_type = data.get('content_type') or getattr(self.instance, 'content_type', None) or 'text'
        field = self.CONTENT_FIELDS.get(content_type)
        if not field:
            return data

        value = data.get(field, serializers.empty)
        if value is serializers.empty:
            value = getattr(self.instance, field, None)
        if isinstance(value, str):
            value = value.strip()

        if not value:
            raise serializers.ValidationError({
                field: f'{content_type.capitalize()} content is required for {content_type} stories.'
            })

        # The other two content fields must stay empty so content_type stays truthful.
        for other_type, other_field in self.CONTENT_FIELDS.items():
            if other_field != field and data.get(other_field):
                raise serializers.ValidationError({
                    other_field: f'Only {content_type} content should be provided for {content_type} stories.'
                })

        return data

    def get_user(self, obj):
        """
        Custom user representation that includes role-specific profile image
        """
        from accounts.serializers import UserListSerializer
        user_data = UserListSerializer(obj.user).data
        request = self.context.get('request')
        
        profile_image = None
        if obj.user_type == 'employer' and obj.company:
            if obj.company.logo:
                url = obj.company.logo.url
                profile_image = request.build_absolute_uri(url) if request else url
        elif obj.user_type == 'candidate' and obj.candidate:
            if obj.candidate.profile_image:
                url = obj.candidate.profile_image.url
                profile_image = request.build_absolute_uri(url) if request else url
        
        user_data['profile_image'] = profile_image
        return user_data


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
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = ['id', 'company_name', 'logo']

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get('request')
            url = obj.logo.url
            return request.build_absolute_uri(url) if request else url
        return None


class CompanySerializer(serializers.ModelSerializer):
    company_id = serializers.IntegerField(source='id', read_only=True)
    logo = serializers.SerializerMethodField()
    
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

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get('request')
            url = obj.logo.url
            return request.build_absolute_uri(url) if request else url
        return None


class ProjectSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(source='id', read_only=True)
    
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    
    company = CompanyBasicSerializer(read_only=True)

    skills = serializers.SerializerMethodField()
    
    # Formatted fields
    paymentType = serializers.CharField(source='get_paymentType_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    category = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Project
        fields = [
            'project_id', 'id', 'title', 'description', 'category', 'paymentType', 'paymentAmount', 'payment_currency',
            'estimatedHours', 'deadline', 'status', 'company', 'created_at',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'skills',
            'hasTemporaryOption', 'temporaryDuration'
        ]

    def get_skills(self, obj):
        skills = list(ProjectSkill.objects.filter(project=obj).values_list('name', flat=True))
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]


class JobSerializer(serializers.ModelSerializer):
    job_id = serializers.IntegerField(source='id', read_only=True)

    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    
    # Formatted fields
    employmentType = serializers.CharField(source='get_employmentType_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    workStyle = serializers.CharField(source='get_workStyle_display', read_only=True)
    category = serializers.CharField(source='get_category_display', read_only=True)
    experienceLevel = serializers.CharField(source='get_experienceLevel_display', read_only=True)
    skills = serializers.SerializerMethodField()
    company = CompanyBasicSerializer(read_only=True)

    class Meta:
        model = Job
        fields = [
            'job_id', 'id', 'title', 'description', 'employmentType', 'location', 'salaryRangeMin', 'salaryRangeMax', 'salary_currency',
            'like_count', 'comment_count', 'is_liked', 'is_saved', 'created_at','status', 'skills', 'applicationDeadline',
            'workStyle', 'category', 'experienceLevel', 'hasTemporaryOption', 'temporaryDuration', 'company'
        ]
    
    def get_skills(self, obj):
        """Return skills with first letter capitalized"""
        skills = obj.skills or []
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]


class CandidateSerializer(serializers.ModelSerializer):
    candidate_id = serializers.IntegerField(source='id', read_only=True)

    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)
    profile_completed = serializers.SerializerMethodField()
    
    # Formatted fields
    work_style = serializers.CharField(source='get_work_style_display', read_only=True)
    availability_type = serializers.CharField(source='get_availability_type_display', read_only=True)
    seniority_level = serializers.CharField(source='get_seniority_level_display', read_only=True)
    skills = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            'candidate_id', 'id', 'full_name', 'title', 'bio', 'location', 'work_style', 'is_available',
            'availability_type', 'skills', 'seniority_level', 'min_salary', 'max_salary',
            'salary_currency', 'profile_image', 'like_count', 'comment_count',
            'is_liked', 'is_saved', 'created_at', 'user_id', 'profile_completed'
        ]
    
    def get_skills(self, obj):
        """Return skills with first letter capitalized"""
        skills = obj.skills or []
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]

    def get_profile_completed(self, obj):
        return all([
            bool(getattr(obj, 'basic_info_completed', False)),
            bool(getattr(obj, 'work_preferences_completed', False)),
            bool(getattr(obj, 'skills_completed', False)),
            bool(getattr(obj, 'portfolio_completed', False)),
            bool(getattr(obj, 'privacy_completed', False)),
        ])