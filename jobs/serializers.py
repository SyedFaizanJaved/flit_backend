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
    workStyle = serializers.CharField(source='get_workStyle_display', read_only=True)
    category = serializers.CharField(source='get_category_display', read_only=True)
    experienceLevel = serializers.CharField(source='get_experienceLevel_display', read_only=True)
    employmentType = serializers.CharField(source='get_employmentType_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    skills = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'description', 'company_name', 'company_id', 'workStyle', 'category',
            'experienceLevel', 'employmentType', 'skills', 'salaryRangeMin',
            'salaryRangeMax', 'benefits', 'applicationDeadline', 'hasTemporaryOption','temporaryDuration',
            'status', 'created_at', 'updated_at', 'is_applied'
        )
    
    def get_skills(self, obj):
        """Return skills with first letter capitalized"""
        skills = obj.skills or []
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]
    
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
    application_details = serializers.SerializerMethodField()
    application_count = serializers.SerializerMethodField()
    workStyle = serializers.CharField(source='get_workStyle_display', read_only=True)
    category = serializers.CharField(source='get_category_display', read_only=True)
    experienceLevel = serializers.CharField(source='get_experienceLevel_display', read_only=True)
    employmentType = serializers.CharField(source='get_employmentType_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    skills = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = (
            'id', 'description', 'title', 'company_name', 'company_id', 'location', 'workStyle',
            'category', 'experienceLevel', 'employmentType', 'salaryRangeMin', 'salaryRangeMax',
            'status', 'created_at', 'skills', 'is_applied', 'application_details',
            'application_count', 'hasTemporaryOption', 'temporaryDuration'
        )
    
    def get_skills(self, obj):
        """Return skills with first letter capitalized"""
        skills = obj.skills or []
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]
    
    def get_is_applied(self, obj):
        """
        Check if the current user (must be a candidate) has applied to this job.
        Returns False for non-candidate users or if not authenticated.
        """
        request = self.context.get('request')
        
        # Only proceed if user is authenticated and is a candidate
        if not request or not request.user.is_authenticated:
            return False
            
        if not hasattr(request.user, 'candidate_profile'):
            return False
            
        # Check if candidate has an active application for this job
        return obj.applications.filter(
            candidate=request.user.candidate_profile,
            is_withdrawn=False
        ).exists()
        
    def get_application_count(self, obj):
        """
        Return the total count of non-withdrawn applications for this job.
        """
        return obj.applications.filter(is_withdrawn=False).count()

    def get_application_details(self, obj):
        """
        Return application details for the job.
        For candidates: returns their own application if exists
        For employers: returns the first application if any exists
        """
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            return None
        
        # For candidates - show their own application
        if hasattr(request.user, 'candidate_profile'):
            candidate = request.user.candidate_profile
            try:
                application = obj.applications.get(
                    candidate=candidate,
                    is_withdrawn=False
                )
                return {
                    'application_id': application.id,
                    'candidate_name': application.candidate.full_name,
                    'status': application.status,
                    'user_id': request.user.id,
                    'candidate_id': application.candidate.id,
                    'profile_image': request.build_absolute_uri(application.candidate.profile_image.url) if application.candidate.profile_image else None
                }
            except obj.applications.model.DoesNotExist:
                return None
        
        # For employers - show the 2 most recent applications if any exist
        elif hasattr(request.user, 'employer_profile') and obj.applications.exists():
            # Get the 2 most recent applications, ordered by application date (newest first)
            recent_applications = obj.applications.filter(
                is_withdrawn=False
            ).order_by('-applied_at')[:2]
            
            applications_data = []
            for application in recent_applications:
                profile_image = None
                if application.candidate.profile_image:
                    profile_image = request.build_absolute_uri(application.candidate.profile_image.url)
                
                applications_data.append({
                    'application_id': application.id,
                    'candidate_name': application.candidate.full_name,
                    'status': application.status,
                    'user_id': application.candidate.user.id,
                    'candidate_id': application.candidate.id,
                    'profile_image': profile_image,
                    'applied_at': application.applied_at
                })
                
            return applications_data
            
        return None


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
                 