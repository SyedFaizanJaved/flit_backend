from rest_framework import serializers
from .models import Candidate, WorkDNA, Reference, ReferenceRequest


class CandidateSerializer(serializers.ModelSerializer):
    """
    Serializer for candidate profile
    """
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    profile_image = serializers.ImageField(required=False, allow_null=True, use_url=True)
    
    class Meta:
        model = Candidate
        fields = ("id", "full_name", "profile_completed","title", "bio","work_style","availability_type",
            "skills","superpowers","preferred_roles","min_salary","max_salary","resume_url","video_intro_url",
            "intro_video_description", "privacy_completed","location","created_at","updated_at","user",
            "profile_image","resume_url"
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


class CandidateListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing candidates
    """
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = ('id', 'full_name', 'title',"bio", "profile_image", 'location', 'is_available', 'work_style', 
                 'skills', 'superpowers', 'profile_completed', 'min_salary', 'max_salary', 'created_at')
    
    def get_profile_completed(self, obj):
        try:
            return bool(getattr(obj, 'is_profile_complete', False))
        except Exception:
            return False


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
                 'video_visibility', 'contact_visibility', 'salary_visibility', 'privacy_completed')
    
    def validate(self, attrs):
        if attrs.get('profile_image', None) == "":
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
