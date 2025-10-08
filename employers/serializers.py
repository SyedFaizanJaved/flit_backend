from rest_framework import serializers
from .models import Employer, EmployerPreference, EmployerCompliance


class EmployerSerializer(serializers.ModelSerializer):
    """
    Serializer for employer profile
    """
    full_name = serializers.ReadOnlyField()
    is_profile_complete = serializers.ReadOnlyField()
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_id = serializers.IntegerField(source='company.id', read_only=True)
    
    class Meta:
        model = Employer
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class EmployerListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing employers
    """
    full_name = serializers.ReadOnlyField()
    is_profile_complete = serializers.ReadOnlyField()
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_id = serializers.IntegerField(source='company.id', read_only=True)
    
    class Meta:
        model = Employer
        fields = (
            'id', 'full_name',
            'company_id', 'company_name',
            'is_profile_complete', 'created_at'
        )


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
        
        return super().update(instance, validated_data)


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
