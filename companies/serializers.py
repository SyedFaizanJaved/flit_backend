from rest_framework import serializers
from .models import Company, CompanyImage, CompanyMilestone
from django.conf import settings
from employers.models import Employer
from utils.file_validators import sanitize_filename
import json
import logging
import os

logger = logging.getLogger(__name__)

GALLERY_IMAGE_MAX_COUNT = 15  # matches CompanyImageBulkUploadSerializer.max_length




def _validate_gallery_images(images, existing_count):
    """
    Shared validator for `uploaded_images`: bound total gallery size
    (existing + new) at GALLERY_IMAGE_MAX_COUNT.
    """
    if not images:
        return images
    total = (existing_count or 0) + len(images)
    if total > GALLERY_IMAGE_MAX_COUNT:
        raise serializers.ValidationError(
            f"Gallery is limited to {GALLERY_IMAGE_MAX_COUNT} images "
            f"(would become {total})."
        )
    return images


class SanitizedImageField(serializers.ImageField):
    """
    Custom ImageField that sanitizes the filename before validation.
    """
    def to_internal_value(self, data):
        data = sanitize_filename(data)
        return super().to_internal_value(data)


class CompanyImageSerializer(serializers.ModelSerializer):
    """
    Serializer for company gallery images
    """
    image = SanitizedImageField(required=True)
    
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
    uploaded_images = serializers.ListField(
        child=SanitizedImageField(),
        required=False,
        write_only=True
    )
    logo = SanitizedImageField(required=False, allow_null=True)
    caption = serializers.ListField(
        child=serializers.CharField(max_length=200, required=False, allow_blank=True),
        required=False,
        write_only=True
    )
    milestones_data = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = Company
        fields = (
            'id', 'company_name', 'description', 'industry', 'size', 'website', 'logo', 
            'location', 'values', 'founded_year', 'culture', 'benefits', 'social_links', 
            'work_mode', 'created_by', 'is_verified', 'is_active', 'is_completed', 
            'total_jobs', 'total_projects', 'total_hires', 'total_employees', 
            'created_at', 'updated_at', 'profile_completed', 'images', 'milestones',
            'uploaded_images', 'caption', 'milestones_data'
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
    
    def validate_logo(self, value):
        """Sanitize logo filename if it exists"""
        return sanitize_filename(value)

    def validate_uploaded_images(self, value):
        return _validate_gallery_images(value, existing_count=0)

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', None)
        captions_data = validated_data.pop('caption', [])
        milestones_data = validated_data.pop('milestones_data', None)
        
        # Handle social_links parsing similar to update
        if 'social_links' in validated_data and isinstance(validated_data['social_links'], str):
            try:
                validated_data['social_links'] = json.loads(validated_data['social_links'])
            except json.JSONDecodeError:
                validated_data['social_links'] = {}

        # Ensure created_by is set to current user if not provided (should be provided by view but safe here)
        if 'created_by' not in validated_data:
            validated_data['created_by'] = self.context['request'].user
            
        # Ensure completion flag is explicitly set to True on creation
        validated_data['is_completed'] = True
        company = super().create(validated_data)

        # Handle images bulk upload
        if uploaded_images:
            total_bytes = sum(getattr(f, 'size', 0) or 0 for f in uploaded_images)
            logger.info(
                "Company %s: uploading %d gallery images (total %d bytes)",
                company.id, len(uploaded_images), total_bytes,
            )
            for index, image_file in enumerate(uploaded_images):
                # Map caption to image by index. If only one caption is sent for multiple images,
                # apply that single caption to all images in the batch.
                if len(captions_data) == 1 and len(uploaded_images) > 1:
                    curr_caption = captions_data[0]
                else:
                    curr_caption = captions_data[index] if index < len(captions_data) else ""

                try:
                    CompanyImage.objects.create(
                        company=company,
                        image=image_file,
                        caption=curr_caption,
                        order=index + 1
                    )
                except Exception as e:
                    logger.exception(
                        "Failed to persist gallery image %d for company %s: %s",
                        index, company.id, e,
                    )
                    raise

        # Handle milestones bulk upload
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
                    CompanyMilestone.objects.create(
                        company=company,
                        year=m_data.get('year'),
                        title=m_data.get('title'),
                        description=m_data.get('description', '')
                    )
                except Exception as e:
                    print(f"Error creating milestone during company setup: {e}")
                    pass

        # Link to creator's employer profile
        try:
            user = self.context['request'].user
            employer, _ = Employer.objects.get_or_create(
                user=user,
                defaults={'first_name': getattr(user, 'first_name', ''), 'last_name': getattr(user, 'last_name', '')}
            )

            # Attach company and mark company_info as completed
            employer.company = company
            employer.company_info_completed = True
            employer.save(update_fields=['company', 'company_info_completed', 'updated_at'])

            # Adopt anything this employer posted anonymously before setting up a
            # company, so the anonymous state resolves itself instead of stranding
            # postings that can never show a company again.
            from jobs.models import Job
            from projects.models import Project
            Job.objects.filter(employer=user, company__isnull=True).update(company=company)
            Project.objects.filter(employer=user, company__isnull=True).update(company=company)

            # Mark user profile as completed ONLY if all employer requirements are met
            if employer.is_profile_complete:
                if not getattr(user, 'profile_completed', False):
                    user.profile_completed = True
                    user.save(update_fields=['profile_completed', 'updated_at'])
        except Exception:
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
        child=SanitizedImageField(),
        required=False,
        write_only=True
    )
    milestones_data = serializers.JSONField(required=False, write_only=True)
    logo = SanitizedImageField(required=False, allow_null=True)
    deleted_images = serializers.JSONField(required=False, write_only=True)
    deleted_milestones = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = Company
        fields = (
            'company_name', 'description', 'industry', 'size', 'website', 'logo',
            'location', 'values', 'founded_year', 'culture', 'benefits',
            'social_links', 'work_mode', 'uploaded_images', 'milestones_data', 'deleted_images', 'deleted_milestones'
        )

    def validate_uploaded_images(self, value):
        # Subtract pending deletions from the existing count so a user can swap
        # images in a single PATCH (delete some, upload some) without hitting the cap.
        existing_count = 0
        if self.instance is not None:
            existing_count = self.instance.images.count()
            raw = self.initial_data.get('deleted_images') if hasattr(self, 'initial_data') else None
            if raw:
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        raw = []
                if isinstance(raw, list):
                    existing_count = max(0, existing_count - len(raw))
        return _validate_gallery_images(value, existing_count=existing_count)

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

        if uploaded_images:
            total_bytes = sum(getattr(f, 'size', 0) or 0 for f in uploaded_images)
            logger.info(
                "Company %s: appending %d gallery images (total %d bytes)",
                instance.id, len(uploaded_images), total_bytes,
            )
            last_order = CompanyImage.objects.filter(company=instance).order_by('-order').values_list('order', flat=True).first() or 0
            for index, image_file in enumerate(uploaded_images):
                try:
                    CompanyImage.objects.create(
                        company=instance,
                        image=image_file,
                        order=last_order + index + 1
                    )
                except Exception as e:
                    logger.exception(
                        "Failed to persist gallery image %d for company %s: %s",
                        index, instance.id, e,
                    )
                    raise

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
                # Check if this is an existing milestone (has id) or new milestone
                milestone_id = m_data.get('id')
                
                # Filter out temporary frontend IDs (e.g., timestamps > 2^31-1 if using Postgres Integer)
                # Assuming valid DB IDs are reasonable integers. 
                # Postgres Integer max is 2147483647. Timestamps are much larger.
                is_temp_id = False
                if milestone_id:
                    try:
                        mid_int = int(milestone_id)
                        # Accessing a really large integer might be safe in Python but not for DB query if ID field is IntegerField
                        if mid_int > 2147483647: 
                            is_temp_id = True
                    except (ValueError, TypeError):
                        is_temp_id = True

                if milestone_id and not is_temp_id:
                    # Update existing milestone
                    try:
                        milestone = CompanyMilestone.objects.get(id=milestone_id, company=instance)
                        milestone.year = m_data.get('year', milestone.year)
                        milestone.title = m_data.get('title', milestone.title)
                        milestone.description = m_data.get('description', milestone.description)
                        milestone.save()
                    except CompanyMilestone.DoesNotExist:
                        # If ID provided but not found in DB, treat as new (or could ignore)
                        # Here we choose to create new to be safe/flexible
                        CompanyMilestone.objects.create(
                            company=instance,
                            year=m_data.get('year'),
                            title=m_data.get('title'),
                            description=m_data.get('description', '')
                        )
                    except Exception as e:
                        print(f"Error updating milestone {milestone_id}: {e}")
                        # Don't silence other errors blindly
                        pass 
                else:
                    # Create new milestone
                    try:
                        CompanyMilestone.objects.create(
                            company=instance,
                            year=m_data.get('year'),
                            title=m_data.get('title'),
                            description=m_data.get('description', '')
                        )
                    except Exception as e:
                        print(f"Error creating milestone: {e}")

        return instance