from rest_framework import serializers
from .models import Company


class CompanySerializer(serializers.ModelSerializer):
    """
    Serializer for company
    """
    full_address = serializers.ReadOnlyField()
    
    class Meta:
        model = Company
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class CompanyListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing companies
    """
    full_address = serializers.ReadOnlyField()
    
    class Meta:
        model = Company
        fields = ('id', 'company_name', 'industry', 'size', 'location', 'website', 
                 'is_verified', 'is_active', 'created_at')


class CompanyUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating company
    """
    class Meta:
        model = Company
        fields = ('company_name', 'description', 'industry', 'size', 'founded', 'website', 
                 'logo', 'contact_email', 'contact_phone', 'address_street', 
                 'address_city', 'address_state', 'address_country', 'address_zip_code',
                 'linkedin_url', 'twitter_url', 'facebook_url', 'instagram_url',
                 'mission', 'vision', 'values', 'work_style', 'benefits', 'perks',
                 'work_life_balance')
