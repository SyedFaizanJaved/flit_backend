from rest_framework import serializers
from .models import Company, CompanyImage, CompanyMilestone
from django.conf import settings
from employers.models import Employer
import json


class CompanyImageSerializer(serializers.ModelSerializer):
    """
    Serializer for company gallery images
    """
    image = serializers.ImageField(required=True)
    
    class Meta:
        model = CompanyImage
        fields = ('id', 'image', 'caption', 'order', 'created_at')
        read_only_fields = ('created_at',)


class CompanyImageBulkUploadSerializer(serializers.Serializer):
    """
    Serializer for bulk uploading company images
    """
    images = serializers.ListField(
        child=serializers.ImageField(),
        required=True,
        min_length=1,
        max_length=15
    )
    caption = serializers.ListField(
        child=serializers.CharField(max_length=200, required=False, allow_blank=True),
        required=False
    )


class CompanyMilestoneSerializer(serializers.ModelSerializer):
    """
    Serializer for company milestones
    """
    class Meta:
        model = CompanyMilestone
        fields = ('id', 'year', 'title', 'description')


class CompanySerializer(serializers.ModelSerializer):
    """
    Serializer for company with enhanced branding fields
    """
    profile_completed = serializers.SerializerMethodField(read_only=True)
    images = CompanyImageSerializer(many=True, read_only=True)
    milestones = CompanyMilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = (
            'id', 'company_name', 'description', 'industry', 'size', 'website', 'logo', 
            'location', 'values', 'founded_year', 'culture', 'benefits', 'social_links', 
            'work_mode', 'created_by', 'is_verified', 'is_active', 'is_completed', 
            'total_jobs', 'total_projects', 'total_hires', 'total_employees', 
            'created_at', 'updated_at', 'profile_completed', 'images', 'milestones'
        )
        read_only_fields = (
            'created_by', 'created_at', 'updated_at', 'profile_completed', 
            'is_verified', 'is_active', 'is_completed', 'total_jobs', 
            'total_projects', 'total_hires', 'total_employees'
        )
        extra_kwargs = {
            'company_name': {'required': True},
            'description': {'required': True},
            'industry': {'required': True},
            'size': {'required': True},
            'values': {'required': True},
            'location': {'required': True},
        }
    
    def validate_values(self, value):
        if not value:
            raise serializers.ValidationError("Company values are required and cannot be empty.")
        return value
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        # Ensure completion flag is explicitly set to True on creation
        validated_data['is_completed'] = True
        company = super().create(validated_data)

        # Try to link the created company to the creator's employer profile
        try:
            user = self.context['request'].user
            # Ensure an Employer profile exists for the user, create if missing
            employer, _ = Employer.objects.get_or_create(
                user=user,
                defaults={'first_name': getattr(user, 'first_name', ''), 'last_name': getattr(user, 'last_name', '')}
            )

            # Attach company and mark company_info as completed
            employer.company = company
            employer.company_info_completed = True
            employer.save(update_fields=['company', 'company_info_completed', 'updated_at'])
            # Mark the user's profile as completed now that company info exists.
            try:
                if not getattr(user, 'profile_completed', False):
                    user.profile_completed = True
                    # Save the user so subsequent serialization sees the updated flag
                    user.save(update_fields=['profile_completed', 'updated_at'])
            except Exception:
                # Don't let a user sync failure break company creation
                pass
        except Exception:
            # Don't break company creation if linking fails
            pass

        return company

    def get_profile_completed(self, obj):
        """Return whether the creating user has profile_completed set."""
        try:
            user = self.context['request'].user
            return bool(getattr(user, 'profile_completed', False))
        except Exception:
            return False


class CompanyListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing companies
    """
    class Meta:
        model = Company
        fields = ('id', 'company_name', 'industry', 'description', 'size', 'logo', 'location', 'website', 'values',
                  'work_mode', 'is_active', 'created_at')


class CompanyUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating company with consolidated images and milestones
    """
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        write_only=True
    )
    milestones_data = serializers.JSONField(required=False, write_only=True)
    deleted_images = serializers.JSONField(required=False, write_only=True)
    deleted_milestones = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = Company
        fields = (
            'company_name', 'description', 'industry', 'size', 'website', 'logo', 
            'location', 'values', 'founded_year', 'culture', 'benefits', 
            'social_links', 'work_mode', 'uploaded_images', 'milestones_data', 'deleted_images', 'deleted_milestones'
        )

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', None)
        milestones_data = validated_data.pop('milestones_data', None)
        deleted_images = validated_data.pop('deleted_images', None)
        deleted_milestones = validated_data.pop('deleted_milestones', None)
        
        # Handle social_links separately since it comes as JSON string in FormData
        social_links = validated_data.pop('social_links', None)

        # Update basic fields using standard behavior
        instance = super().update(instance, validated_data)

        # Handle social_links update
        if social_links is not None:
            # If social_links is a string (from FormData), parse it
            if isinstance(social_links, str):
                try:
                    social_links = json.loads(social_links)
                except json.JSONDecodeError:
                    social_links = {}
            
            # Ensure it's a dictionary
            if not isinstance(social_links, dict):
                social_links = {}
            
            # Update the social_links field
            instance.social_links = social_links
            instance.save(update_fields=['social_links'])

        # Handle deleted images
        if deleted_images:
            if isinstance(deleted_images, str):
                try:
                    deleted_images = json.loads(deleted_images)
                except json.JSONDecodeError:
                    pass
            if isinstance(deleted_images, list):
                CompanyImage.objects.filter(id__in=deleted_images, company=instance).delete()

        # Handle deleted milestones
        if deleted_milestones:
            if isinstance(deleted_milestones, str):
                try:
                    deleted_milestones = json.loads(deleted_milestones)
                except json.JSONDecodeError:
                    pass
            if isinstance(deleted_milestones, list):
                CompanyMilestone.objects.filter(id__in=deleted_milestones, company=instance).delete()

        # Handle images bulk upload in the same request
        if uploaded_images:
            last_order = CompanyImage.objects.filter(company=instance).order_by('-order').values_list('order', flat=True).first() or 0
            for index, image_file in enumerate(uploaded_images):
                CompanyImage.objects.create(
                    company=instance,
                    image=image_file,
                    order=last_order + index + 1
                )

        # Handle milestones bulk upload in the same request
        if milestones_data:
            # If milestones_data is a string (common when using form-data in Postman), parse it
            if isinstance(milestones_data, str):
                try:
                    milestones_data = json.loads(milestones_data)
                except json.JSONDecodeError:
                    raise serializers.ValidationError({"milestones_data": "Invalid JSON format"})

            if not isinstance(milestones_data, list):
                milestones_data = [milestones_data]

            for m_data in milestones_data:
                try:
                    # Check if this is an existing milestone (has id) or new milestone
                    milestone_id = m_data.get('id')
                    if milestone_id:
                        # Update existing milestone
                        try:
                            milestone = CompanyMilestone.objects.get(id=milestone_id, company=instance)
                            milestone.year = m_data.get('year', milestone.year)
                            milestone.title = m_data.get('title', milestone.title)
                            milestone.description = m_data.get('description', milestone.description)
                            milestone.save()
                        except CompanyMilestone.DoesNotExist:
                            # If milestone doesn't exist, create it as new
                            CompanyMilestone.objects.create(
                                company=instance,
                                year=m_data.get('year'),
                                title=m_data.get('title'),
                                description=m_data.get('description', '')
                            )
                    else:
                        # Create new milestone
                        CompanyMilestone.objects.create(
                            company=instance,
                            year=m_data.get('year'),
                            title=m_data.get('title'),
                            description=m_data.get('description', '')
                        )
                except Exception:
                    # Skip invalid milestone data
                    pass

        return instance