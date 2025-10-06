from rest_framework import serializers
from .models import Job, JobSkill, JobLanguage


class JobSkillSerializer(serializers.ModelSerializer):
    """
    Serializer for job skills
    """
    class Meta:
        model = JobSkill
        fields = '__all__'
        read_only_fields = ('job',)


class JobLanguageSerializer(serializers.ModelSerializer):
    """
    Serializer for job languages
    """
    class Meta:
        model = JobLanguage
        fields = '__all__'
        read_only_fields = ('job',)


class JobSerializer(serializers.ModelSerializer):
    """
    Serializer for job postings
    """
    # Only expose flat skills list; keep languages nested
    # required_languages = JobLanguageSerializer(many=True, read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'description', 'company_name', 'workStyle', 'category',
            'experienceLevel', 'employmentType', 'skills', 'salaryRangeMin',
            'salaryRangeMax', 'benefits', 'applicationDeadline', 'hasTemporaryOption',
            'status', 'created_at', 'updated_at'
        )
        # read_only_fields = ('employer', 'created_at', 'updated_at', 'slug')
    
    # def create(self, validated_data):
    #     validated_data['employer'] = self.context['request'].user
    #     return super().create(validated_data)


class JobListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing jobs
    """
    company_name = serializers.CharField(source='company.company_name', read_only=True)    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'company_name', 'workStyle',
            'category', 'experienceLevel', 'employmentType', 'salaryRangeMin', 'salaryRangeMax',
            'status', 'created_at', 'skills'
        )


class JobCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating jobs
    """
    skills = serializers.ListField(
        child=serializers.CharField(), 
        write_only=True, 
        min_length=1  # Ensure at least one skill
    )
    # Accept alias 'required_skills' from client; treat it the same as 'skills'
    required_skills = serializers.ListField(
        child=serializers.CharField(), 
        write_only=True, 
        required=False,
        min_length=0
    )
    # languages = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    
    class Meta:
        model = Job
        fields = (
            'title', 'description', 'company', 'workStyle', 'category',
            'skills', 'required_skills', 'experienceLevel', 'employmentType',
            'hasTemporaryOption', 'salaryRangeMin', 'salaryRangeMax',
            'benefits', 'applicationDeadline'
        )
        extra_kwargs = {
            'title': {'required': True},
            'description': {'required': True},
            'company': {'required': True},
            'workStyle': {'required': True},
            'category': {'required': True},
            'experienceLevel': {'required': True},
            'employmentType': {'required': True},
            'salaryRangeMin': {'required': True, 'min_value': 0},
            'salaryRangeMax': {'required': True, 'min_value': 0},
            'benefits': {'required': True},
            'applicationDeadline': {'required': True},
            'hasTemporaryOption': {'required': False},
        }
    
    def create(self, validated_data):
        skills = validated_data.pop('skills', [])
        # Merge alias list if provided
        alias_required_skills = validated_data.pop('required_skills', [])
        if alias_required_skills:
            skills = list({*skills, *alias_required_skills})
        # languages = validated_data.pop('languages', [])
        
        # Ensure employer is set from the authenticated user
        validated_data['employer'] = self.context['request'].user
        # Persist flat skills list into model JSONField
        validated_data['skills'] = skills
        job = super().create(validated_data)
        
        # Create job skills
        for skill in skills:
            JobSkill.objects.create(job=job, name=skill)
        
        # Create job languages
        # for language in languages:
        #     JobLanguage.objects.create(job=job, name=language)
        
        return job

    def to_representation(self, instance):
        # Return unified representation with single 'skills' field
        data = JobSerializer(instance, context=self.context).data
        return data


class JobUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating jobs
    """
    class Meta:
        model = Job
        fields = (
            'title', 'description', 'workStyle', 'category',
            'experienceLevel', 'employmentType', 'hasTemporaryOption', 
            'salaryRangeMin', 'salaryRangeMax', 
            'benefits', 'applicationDeadline', 'status'
        )
        extra_kwargs = {
            'title': {'required': True},
            'description': {'required': True},
            'workStyle': {'required': True},
            'category': {'required': True},
            'experienceLevel': {'required': True},
            'employmentType': {'required': True},
            'salaryRangeMin': {'required': True, 'min_value': 0},
            'salaryRangeMax': {'required': True, 'min_value': 0},
            'benefits': {'required': True},
            'applicationDeadline': {'required': True},
            'hasTemporaryOption': {'required': False},
        }