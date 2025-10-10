from rest_framework import serializers
from .models import Company
from django.conf import settings
from employers.models import Employer


class CompanySerializer(serializers.ModelSerializer):
    """
    Serializer for company
    """
    profile_completed = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Company
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'profile_completed')
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

    # no is_profile_complete helper - using profile_completed only


class CompanyListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing companies
    """
    class Meta:
        model = Company
        fields = ('id', 'company_name', 'industry', 'description', 'size', 'logo', 'location', 'website', 'values',
                  'is_active', 'created_at')


class CompanyUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating company
    """
    class Meta:
        model = Company
        fields = ('company_name', 'description', 'industry', 'size', 'website', 
                 'logo', 'values', 'location')