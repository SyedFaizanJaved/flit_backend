from rest_framework import serializers
from .models import Candidate, WorkDNA, Reference, ReferenceRequest
from companies.models import Company
from jobs.serializers import JobListSerializer
from projects.serializers import ProjectListSerializer


class CandidateSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    profile_image = serializers.ImageField(required=False, allow_null=True, use_url=True)
    viewers_count = serializers.SerializerMethodField()
    profile_views_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Candidate
        fields = ("id", "full_name", "profile_completed","title", "bio","work_style","availability_type",
            "skills","superpowers","preferred_roles","min_salary","max_salary","resume_url","video_intro_url",
             "video_transcription", "privacy_completed","location","created_at","updated_at","user",
            "profile_image","resume_url","profile_views","viewers_count","profile_views_display"
        )
        read_only_fields = ("user", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        instance = super().create(validated_data)

        # Compute component completion flags using the same heuristics as update
        try:
            # Basic info
            if getattr(instance, 'full_name', None) and getattr(instance, 'title', None):
                instance.basic_info_completed = True

            # Work preferences
            work_pref_keys = [
                'work_style', 'availability_type', 'is_available', 'is_remote', 'time_zone', 'location'
            ]
            if any(key in validated_data for key in work_pref_keys):
                instance.work_preferences_completed = True

            # Skills
            if 'skills' in validated_data and getattr(instance, 'skills', None):
                instance.skills_completed = True

            # Portfolio
            if (
                'portfolio_links' in validated_data or
                ('resume_url' in validated_data and instance.resume_url) or
                ('video_intro_url' in validated_data and instance.video_intro_url)
            ):
                instance.portfolio_completed = True

            # Privacy: allow explicit flag or infer from visibility fields
            privacy_keys = ['profile_visibility', 'video_visibility', 'contact_visibility', 'salary_visibility']
            if any(key in validated_data for key in privacy_keys):
                instance.privacy_completed = True
            if 'privacy_completed' in validated_data:
                instance.privacy_completed = bool(validated_data.get('privacy_completed'))

            # Persist any flag changes
            instance.save(update_fields=[
                'basic_info_completed', 'work_preferences_completed', 'skills_completed',
                'portfolio_completed', 'privacy_completed', 'updated_at'
            ])

            # Sync to user
            user = instance.user
            if instance.is_profile_complete and not getattr(user, 'profile_completed', False):
                user.profile_completed = True
                user.save(update_fields=['profile_completed', 'updated_at'])
        except Exception:
            # Don't break creation on sync errors
            pass

        return instance
    
    def get_profile_completed(self, obj):
        try:
            return bool(getattr(obj, 'is_profile_complete', False))
        except Exception:
            return False
    
    def get_viewers_count(self, obj):
        try:
            return len(obj.viewers or [])
        except Exception:
            return 0

    def get_profile_views_display(self, obj):
        try:
            n = int(getattr(obj, 'profile_views', 0) or 0)
        except Exception:
            n = 0
        if n >= 1000000:
            v = n / 1000000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}m"
        if n >= 1000:
            v = n / 1000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}k"
        return str(n)


class CandidateListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    profile_views_display = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = ('id', 'full_name', 'title',"bio", "profile_image", 'location', 'is_available', 'work_style', 
                 'skills', 'superpowers', 'profile_completed', 'min_salary', 'max_salary', 'created_at', 'profile_views_display')
    
    def get_profile_completed(self, obj):
        try:
            return bool(getattr(obj, 'is_profile_complete', False))
        except Exception:
            return False

    def get_profile_views_display(self, obj):
        try:
            n = int(getattr(obj, 'profile_views', 0) or 0)
        except Exception:
            n = 0
        if n >= 1000000:
            v = n / 1000000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}m"
        if n >= 1000:
            v = n / 1000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}k"
        return str(n)


class WorkDNASerializer(serializers.ModelSerializer):
    """
    Serializer for Work DNA assessment
    """
    class Meta:
        model = WorkDNA
        fields = '__all__'
        read_only_fields = ('candidate', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['candidate'] = self.context['request'].user.candidate_profile
        return super().create(validated_data)


class ReferenceSerializer(serializers.ModelSerializer):
    """
    Serializer for references
    """
    class Meta:
        model = Reference
        fields = '__all__'
        read_only_fields = ('candidate', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['candidate'] = self.context['request'].user.candidate_profile
        return super().create(validated_data)


class ReferenceRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for reference requests
    """
    class Meta:
        model = ReferenceRequest
        fields = '__all__'
        read_only_fields = ('candidate', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['candidate'] = self.context['request'].user.candidate_profile
        return super().create(validated_data)


class CandidateProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating candidate profile sections
    """
    profile_image = serializers.ImageField(required=False, allow_null=True, use_url=True)
    class Meta:
        model = Candidate
        # include privacy_completed so frontend can explicitly mark the privacy section complete
        fields = ('full_name', 'title', 'bio', 'location', 'time_zone', 'is_remote', 
                 'work_style', 'is_available', 'availability_type', 'skills', 'superpowers', 
                 'preferred_roles', 'passion_projects', 'min_salary', 'max_salary', 
                 'salary_currency', 'portfolio_links', 'profile_image', 'resume_url', 
                 'video_intro_url', 'intro_video_description', 'profile_visibility', 
                 'video_transcription',
                 'video_visibility', 'contact_visibility', 'salary_visibility', 'privacy_completed')
    
    def to_internal_value(self, data):
    
        data_copy = data.copy() if hasattr(data, 'copy') else data    
        # Convert empty string to None for profile_image when no file is uploaded
        if hasattr(data_copy, 'get') and data_copy.get('profile_image') == '':
            data_copy['profile_image'] = None
            
        return super().to_internal_value(data_copy)
    
    def validate(self, attrs):
        if 'profile_image' in attrs and attrs['profile_image'] in (None, ""):
            attrs['profile_image'] = None
        return attrs
    
    def update(self, instance, validated_data):
        # Update profile completion status based on filled fields
        updated_instance = super().update(instance, validated_data)

        # If client did not send profile_image in the payload for PUT/PATCH,
        # clear it by setting to None (so response shows null)
        if 'profile_image' not in self.initial_data and 'profile_image' not in validated_data:
            if getattr(updated_instance, 'profile_image', None):
                updated_instance.profile_image = None
                updated_instance.save(update_fields=['profile_image'])

        # Basic info complete when name and title are set (and non-empty)
        if (updated_instance.full_name and updated_instance.title):
            updated_instance.basic_info_completed = True

        # Work preferences complete when any of key work pref fields are set
        work_pref_keys = [
            'work_style', 'availability_type', 'is_available', 'is_remote', 'time_zone', 'location'
        ]
        if any(key in validated_data for key in work_pref_keys):
            updated_instance.work_preferences_completed = True

        # Skills complete when skills array provided and not empty
        if 'skills' in validated_data and getattr(updated_instance, 'skills', None):
            updated_instance.skills_completed = True

        # Portfolio complete when links or resume/video provided
        if (
            'portfolio_links' in validated_data or
            ('resume_url' in validated_data and updated_instance.resume_url) or
            ('video_intro_url' in validated_data and updated_instance.video_intro_url)
        ):
            updated_instance.portfolio_completed = True

        # Privacy complete when any visibility field set
        privacy_keys = [
            'profile_visibility', 'video_visibility', 'contact_visibility', 'salary_visibility'
        ]
        if any(key in validated_data for key in privacy_keys):
            updated_instance.privacy_completed = True

        # Allow client to explicitly set privacy_completed (frontend may send this flag)
        if 'privacy_completed' in validated_data:
            updated_instance.privacy_completed = bool(validated_data.get('privacy_completed'))

        # Persist flag changes
        updated_instance.save(update_fields=[
            'basic_info_completed', 'work_preferences_completed', 'skills_completed',
            'portfolio_completed', 'privacy_completed', 'updated_at'
        ])

        # Sync to user.profile_completed if candidate profile is complete
        user = updated_instance.user
        if updated_instance.is_profile_complete and not getattr(user, 'profile_completed', False):
            user.profile_completed = True
            user.save(update_fields=['profile_completed', 'updated_at'])

        return updated_instance


class CompanyWithOpeningsSerializer(serializers.ModelSerializer):
    """
    Company serializer with nested active jobs and projects lists.
    Limits can be controlled via query params: jobs_limit, projects_limit.
    """
    jobs = serializers.SerializerMethodField()
    projects = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = (
            'id', 'company_name', 'industry', 'description', 'size', 'logo',
            'location', 'website', 'values', 'jobs', 'projects'
        )

    def _get_limits(self):
        request = self.context.get('request')
        def parse_int(v, default):
            try:
                return int(v)
            except Exception:
                return default
        jobs_limit = 5
        projects_limit = 5
        if request is not None:
            jobs_limit = parse_int(request.query_params.get('jobs_limit', 5), 5)
            projects_limit = parse_int(request.query_params.get('projects_limit', 5), 5)
        return jobs_limit, projects_limit

    def get_jobs(self, obj):
        qs = obj.jobs.all().order_by('-created_at')
        return JobListSerializer(qs, many=True).data

    def get_projects(self, obj):
        qs = obj.projects.all().order_by('-created_at')
        return ProjectListSerializer(qs, many=True).data
