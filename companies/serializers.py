from rest_framework import serializers
from .models import Company


class CompanySerializer(serializers.ModelSerializer):
    """
    Serializer for company
    """
    class Meta:
        model = Company
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')
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
        return super().create(validated_data)


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