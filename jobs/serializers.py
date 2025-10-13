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
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'description', 'company_name', 'workStyle', 'category',
            'experienceLevel', 'employmentType', 'skills', 'salaryRangeMin',
            'salaryRangeMax', 'benefits', 'applicationDeadline', 'hasTemporaryOption','temporaryDuration',
            'status', 'created_at', 'updated_at'
        )


class JobListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing jobs
    """
    company_name = serializers.CharField(source='company.company_name', read_only=True)    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'company_name', 'location', 'workStyle',
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

    required_skills = serializers.ListField(
        child=serializers.CharField(), 
        write_only=True, 
        required=False,
        min_length=0
    )
    
    class Meta:
        model = Job
        fields = (
            'title', 'description', 'company', 'workStyle', 'category',
            'skills', 'required_skills', 'experienceLevel', 'employmentType',
            'hasTemporaryOption', 'temporaryDuration', 'salaryRangeMin', 'salaryRangeMax',
            'benefits', 'applicationDeadline','status'
        )
        extra_kwargs = {
            'title': {'required': True},
            'description': {'required': True},
            'company': {'required': True},
            'workStyle': {'required': True},
            'required_skills': {'required': True},
            'category': {'required': True},
            'experienceLevel': {'required': True},
            'employmentType': {'required': True},
            'salaryRangeMin': {'required': True, 'min_value': 0},
            'salaryRangeMax': {'required': True, 'min_value': 0},
            'benefits': {'required': True},
            'applicationDeadline': {'required': True},
            'hasTemporaryOption': {'required': False},
            'temporaryDuration': {'required': False, 'allow_blank': True},
            'status': {'required': False},
        }
    
    def create(self, validated_data):
        skills = validated_data.pop('skills', [])
        # Merge alias list if provided
        alias_required_skills = validated_data.pop('required_skills', [])
        if alias_required_skills:
            skills = list({*skills, *alias_required_skills})
        # Ensure employer is set from the authenticated user
        validated_data['employer'] = self.context['request'].user
        # Persist flat skills list into model JSONField
        validated_data['skills'] = skills
        job = super().create(validated_data)
        
        # Create job skills
        for skill in skills:
            JobSkill.objects.create(job=job, name=skill)
        
        return job

    def to_representation(self, instance):
        # Return unified representation with single 'skills' field
        data = JobSerializer(instance, context=self.context).data
        return data


class JobUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating jobs
    """

    company_name = serializers.CharField(source='company.company_name', read_only=True)

    class Meta:
        model = Job
        fields = ('title', 'description', 'location', 'workStyle', 'category',
                 'experienceLevel', 'employmentType', 'hasTemporaryOption', 
                 'temporaryDuration', 'salaryRangeMin', 'salaryRangeMax', 
                 'benefits', 'applicationDeadline', 'start_date', 'status')