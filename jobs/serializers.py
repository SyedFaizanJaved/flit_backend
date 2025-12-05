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
    company_id = serializers.IntegerField(source='company.id', read_only=True)
    is_applied = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'description', 'company_name', 'company_id', 'workStyle', 'category',
            'experienceLevel', 'employmentType', 'skills', 'salaryRangeMin',
            'salaryRangeMax', 'benefits', 'applicationDeadline', 'hasTemporaryOption','temporaryDuration',
            'status', 'created_at', 'updated_at', 'is_applied'
        )
    
    def get_is_applied(self, obj):
        """
        Check if the current user (must be a candidate) has applied to this job.
        Returns False for non-candidate users or if not authenticated.
        """
        request = self.context.get('request')
        
        print("\n[JOB DEBUG] Checking is_applied for job:", obj.id)
        print("[JOB DEBUG] Request user:", getattr(request, 'user', 'No request.user'))
        
        # Only proceed if user is authenticated and is a candidate
        if not request or not request.user.is_authenticated:
            print("[JOB DEBUG] User not authenticated")
            return False
            
        if not hasattr(request.user, 'candidate_profile'):
            print("[JOB DEBUG] User is not a candidate")
            return False
            
        print("[JOB DEBUG] User is a candidate, checking applications...")
        
        # Debug: Print all job applications for this candidate
        from applications.models import JobApplication
        all_apps = JobApplication.objects.filter(
            candidate=request.user.candidate_profile
        )
        print(f"[JOB DEBUG] Candidate has {all_apps.count()} total job applications")
        for app in all_apps:
            print(f"[JOB DEBUG] App ID: {app.id}, Job: {app.job_id}, Status: {app.status}, Withdrawn: {app.is_withdrawn}")
            
        # Check if candidate has an active application for this job
        application_exists = obj.applications.filter(
            candidate=request.user.candidate_profile,
            is_withdrawn=False
        ).exists()
        
        print(f"[JOB DEBUG] Application exists for job {obj.id}: {application_exists}")
        return application_exists


class JobListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing jobs
    """
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_id = serializers.IntegerField(source='company.id', read_only=True)
    is_applied = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = (
            'id', 'description', 'title', 'company_name', 'company_id', 'location', 'workStyle',
            'category', 'experienceLevel', 'employmentType', 'salaryRangeMin', 'salaryRangeMax',
            'status', 'created_at', 'skills', 'is_applied'
        )
    
    def get_is_applied(self, obj):
        """
        Check if the current user (must be a candidate) has applied to this job.
        Returns False for non-candidate users or if not authenticated.
        """
        request = self.context.get('request')
        
        print("\n[JOB LIST DEBUG] Checking is_applied for job:", obj.id)
        print("[JOB LIST DEBUG] Request user:", getattr(request, 'user', 'No request.user'))
        
        # Only proceed if user is authenticated and is a candidate
        if not request or not request.user.is_authenticated:
            print("[JOB LIST DEBUG] User not authenticated")
            return False
            
        if not hasattr(request.user, 'candidate_profile'):
            print("[JOB LIST DEBUG] User is not a candidate")
            return False
            
        # Check if candidate has an active application for this job
        application_exists = obj.applications.filter(
            candidate=request.user.candidate_profile,
            is_withdrawn=False
        ).exists()
        
        print(f"[JOB LIST DEBUG] Application exists for job {obj.id}: {application_exists}")
        return application_exists


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
            'title', 'description', 'company', 'workStyle', 'category', 'status',
            'skills', 'required_skills', 'experienceLevel', 'employmentType',
            'hasTemporaryOption','temporaryDuration', 'salaryRangeMin', 'salaryRangeMax',
            'benefits', 'applicationDeadline'
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
            'status': {'required': False}
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
                 'benefits', 'applicationDeadline', 'start_date', 'status', 'company_name')
                 