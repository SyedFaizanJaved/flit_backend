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
        fields = ('full_name', 'title', 'bio', 'location', 'time_zone', 'is_remote', 
                 'work_style', 'is_available', 'availability_type', 'skills', 'superpowers', 
                 'preferred_roles', 'passion_projects', 'min_salary', 'max_salary', 
                 'salary_currency', 'portfolio_links', 'profile_image', 'resume_url', 
                 'video_intro_url', 'intro_video_description', 'profile_visibility', 
                 'video_visibility', 'contact_visibility', 'salary_visibility')
    
    def update(self, instance, validated_data):
        # Update profile completion status based on filled fields
        if 'full_name' in validated_data and 'title' in validated_data:
            instance.basic_info_completed = True
        if 'skills' in validated_data:
            instance.skills_completed = True
        if 'portfolio_links' in validated_data or 'resume_url' in validated_data:
            instance.portfolio_completed = True
        if 'profile_visibility' in validated_data:
            instance.privacy_completed = True
        
        return super().update(instance, validated_data)
