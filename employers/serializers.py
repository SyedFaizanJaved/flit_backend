from rest_framework import serializers
from .models import Employer, EmployerPreference, EmployerCompliance


class EmployerSerializer(serializers.ModelSerializer):
    """
    Serializer for employer profile
    """
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    
    def get_company_id(self, obj):
        """Return company ID only if company exists"""
        return obj.company.id if obj.company else None
    
    company_id = serializers.SerializerMethodField(method_name='get_company_id')
    
    class Meta:
        model = Employer
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

    def get_company(self, obj):
        # If employer has company FK set, return its id
        if obj.company_id:
            return obj.company_id

        # Otherwise try to return the most recently created company by the user
        try:
            user = obj.user
            latest = getattr(user, 'created_companies', None)
            if latest is not None:
                latest_company = latest.order_by('-created_at').first()
                if latest_company:
                    return latest_company.id
        except Exception:
            pass

        return None

    def get_profile_completed(self, obj):
        try:
            return bool(getattr(obj, 'is_profile_complete', False))
        except Exception:
            return False


class EmployerListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing employers
    """
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    
    def get_company_id(self, obj):
        """Return company ID only if company exists"""
        return obj.company.id if obj.company else None
    
    company_id = serializers.SerializerMethodField(method_name='get_company_id')
    
    class Meta:
        model = Employer
        fields = (
            'id', 'full_name',
            'company_id', 'company_name',
            'profile_completed', 'created_at'
        )

    def get_profile_completed(self, obj):
        try:
            return bool(getattr(obj, 'is_profile_complete', False))
        except Exception:
            return False


class EmployerProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating employer profile sections
    """
    class Meta:
        model = Employer
        fields = (
            'first_name', 'last_name', 'phone', 'position', 'department',
            'profile_picture', 'bio',
            'company',
        )

    def update(self, instance, validated_data):
        # Update profile completion status
        if 'first_name' in validated_data and 'last_name' in validated_data:
            instance.basic_info_completed = True
        if 'company' in validated_data and validated_data.get('company'):
            instance.company_info_completed = True

        updated = super().update(instance, validated_data)

        # Sync to user.profile_completed if employer profile is now complete
        try:
            user = instance.user
            if instance.is_profile_complete and not getattr(user, 'profile_completed', False):
                user.profile_completed = True
                user.save(update_fields=['profile_completed', 'updated_at'])
        except Exception:
            pass

        return updated


class EmployerPreferenceSerializer(serializers.ModelSerializer):
    """
    Serializer for employer preferences
    """
    class Meta:
        model = EmployerPreference
        fields = '__all__'
        read_only_fields = ('employer',)


class EmployerComplianceSerializer(serializers.ModelSerializer):
    """
    Serializer for employer compliance
    """
    class Meta:
        model = EmployerCompliance
        fields = '__all__'
        read_only_fields = ('employer', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['employer'] = self.context['request'].user.employer_profile
        return super().create(validated_data)

class EmployerConversationSummarySerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        from candidates.models import Candidate
        model = Candidate
        fields = ('user_id', 'full_name', 'title', 'last_message_time', 'unread_count')
    
class EmployerCompanyConversationSummarySerializer(serializers.ModelSerializer):
    """
    Serializer used on the candidate side to list employers they have chatted with,
    returning employer's user id, the associated company details, and unread message count.
    """
    id = serializers.IntegerField(source='user.id', read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    industry = serializers.CharField(source='company.industry', read_only=True)
    logo = serializers.ImageField(source='company.logo', read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True)
    last_seen = serializers.DateTimeField(source='user.last_login', read_only=True)
    unread_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Employer
        fields = ('id', 'company_name', 'industry', 'logo', 'last_message_time', 'last_seen', 'unread_count')