from rest_framework import serializers
from .models import Candidate, WorkDNA, Reference, ReferenceRequest


class CandidateSerializer(serializers.ModelSerializer):
    """
    Serializer for candidate profile
    """
    full_name = serializers.ReadOnlyField()
    is_profile_complete = serializers.ReadOnlyField()
    
    class Meta:
        model = Candidate
        fields = ("id", "full_name", "is_profile_complete","title", "bio","work_style","availability_type",
            "skills","superpowers","preferred_roles","min_salary","max_salary","resume_url","video_intro_url",
            "intro_video_description", "privacy_completed","created_at","updated_at","user",
        )
        read_only_fields = ("user", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class CandidateListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing candidates
    """
    full_name = serializers.ReadOnlyField()
    is_profile_complete = serializers.ReadOnlyField()
    
    class Meta:
        model = Candidate
        fields = ('id', 'full_name', 'title', 'location', 'is_available', 'work_style', 
                 'skills', 'superpowers', 'is_profile_complete', 'created_at')


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
    class Meta:
        model = Candidate
        # include privacy_completed so frontend can explicitly mark the privacy section complete
        fields = ('full_name', 'title', 'bio', 'location', 'time_zone', 'is_remote', 
                 'work_style', 'is_available', 'availability_type', 'skills', 'superpowers', 
                 'preferred_roles', 'passion_projects', 'min_salary', 'max_salary', 
                 'salary_currency', 'portfolio_links', 'profile_image', 'resume_url', 
                 'video_intro_url', 'intro_video_description', 'profile_visibility', 
                 'video_visibility', 'contact_visibility', 'salary_visibility', 'privacy_completed')
    
    def update(self, instance, validated_data):
        # Update profile completion status based on filled fields
        updated_instance = super().update(instance, validated_data)

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
