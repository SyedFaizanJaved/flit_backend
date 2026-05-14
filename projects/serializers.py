from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from timezone_field.rest_framework import TimeZoneSerializerField
from django.utils import timezone
from .models import Project, ProjectSkill, ProjectMilestone


class ProjectSkillSerializer(serializers.ModelSerializer):
    """
    Serializer for project skills
    """
    class Meta:
        model = ProjectSkill
        fields = '__all__'
        read_only_fields = ('project',)


class ProjectMilestoneSerializer(serializers.ModelSerializer):
    """
    Serializer for project milestones
    """
    class Meta:
        model = ProjectMilestone
        fields = '__all__'
        read_only_fields = ('project',)


class ProjectSerializer(serializers.ModelSerializer):
    """
    Serializer for project postings
    """
    required_skills = ProjectSkillSerializer(many=True, read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_id = serializers.IntegerField(source='company.id', read_only=True)
    is_applied = serializers.SerializerMethodField()
    category = serializers.CharField(source='get_category_display', read_only=True)
    paymentType = serializers.CharField(source='get_paymentType_display', read_only=True)
    work_style = serializers.CharField(source='get_work_style_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    education_level = serializers.CharField(source='get_education_level_display', read_only=True)
    project_timezone = TimeZoneSerializerField()
    
    class Meta:
        model = Project
        fields = (
            'id', 'title', 'description', 'company_name', 'company_id', 'category', 'estimatedHours',
            'paymentType', 'paymentAmount', 'payment_currency', 'skills', 'deadline', 'required_skills',
            'status', 'work_style', 'education_level', 'created_at', 'updated_at', 'is_applied',
            'hasTemporaryOption', 'temporaryDuration', 'project_timezone'
        )
        read_only_fields = ('employer', 'created_at', 'updated_at', 'slug')
    
    def get_is_applied(self, obj):
        """
        Check if the current user (must be a candidate) has applied to this project.
        Returns False for non-candidate users or if not authenticated.
        """
        request = self.context.get('request')
      
        # Only proceed if user is authenticated and is a candidate
        if not request or not request.user.is_authenticated:
            return False
            
        if not hasattr(request.user, 'candidate_profile'):

            return False
        
        # Check if candidate has an active application for this project
        application_exists = obj.applications.filter(
            candidate=request.user.candidate_profile,
            is_withdrawn=False
        ).exists()
        
        return application_exists
    
    def create(self, validated_data):
        validated_data['employer'] = self.context['request'].user
        return super().create(validated_data)


class ProjectListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing projects
    """
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    company_id = serializers.IntegerField(source='company.id', read_only=True)
    company_logo = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    is_applied = serializers.SerializerMethodField()
    application_details = serializers.SerializerMethodField()
    application_count = serializers.SerializerMethodField()
    category = serializers.CharField(source='get_category_display', read_only=True)
    paymentType = serializers.CharField(source='get_paymentType_display', read_only=True)
    work_style = serializers.CharField(source='get_work_style_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    project_timezone = TimeZoneSerializerField(read_only=True)
    education_level = serializers.CharField(source='get_education_level_display', read_only=True)
    
    class Meta:
        model = Project
        fields = ('id', 'title', 'description', 'company_name', 'company_id','company_logo', 'category', 
                 'estimatedHours', 'paymentType', 'paymentAmount', 'payment_currency', 'deadline', 'status', 
                 'work_style', 'education_level', 'created_at', 'skills', 'is_applied', 'application_details',
                 'application_count', 'hasTemporaryOption', 'temporaryDuration', 'project_timezone')
    
    def get_skills(self, obj):
        # Get skills from ProjectSkill model and capitalize first letter
        skills = list(obj.required_skills.values_list('name', flat=True))
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]
    
    def get_company_logo(self, obj):
        """
        Get the company logo URL.
        """
        return obj.company.logo.url if obj.company.logo else None    

    def get_is_applied(self, obj):
        """
        Check if the current user (must be a candidate) has applied to this project.
        Returns False for non-candidate users or if not authenticated.
        """
        request = self.context.get('request')
        
        
        # Only proceed if user is authenticated and is a candidate
        if not request or not request.user.is_authenticated:
            return False
            
        if not hasattr(request.user, 'candidate_profile'):

            return False
            
        from applications.models import ProjectApplication
        all_apps = ProjectApplication.objects.filter(
            candidate=request.user.candidate_profile
        )
        # Check if candidate has an active application for this project
        application_exists = obj.applications.filter(
            candidate=request.user.candidate_profile,
            is_withdrawn=False
        ).exists()
        
        return application_exists
        
    def get_application_count(self, obj):
        """
        Return the total count of non-withdrawn applications for this project.
        """
        return obj.applications.filter(is_withdrawn=False).count()

    def get_application_details(self, obj):
        """
        Return application details for the project.
        For candidates: returns their own application if exists
        For employers: returns the 2 most recent applications if any exist
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
                    'profile_image': request.build_absolute_uri(application.candidate.profile_image.url) if hasattr(application.candidate, 'profile_image') and application.candidate.profile_image else None
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
                if hasattr(application.candidate, 'profile_image') and application.candidate.profile_image:
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


class ProjectCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating projects
    """
    project_timezone = TimeZoneSerializerField(required=False)
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
        model = Project
        fields = (
            'title', 'description', 'company', 'category', 'skills', 'required_skills',
            'paymentType', 'paymentAmount', 'payment_currency', 'estimatedHours', 'deadline', 'status',
            'work_style', 'collaboration', 'application_deadline', 'max_applicants',
            'hasTemporaryOption', 'temporaryDuration', 'project_timezone'
        )
        extra_kwargs = {
            'title': {'required': True},
            'description': {'required': True},
            'company': {'required': True},
            'category': {'required': True},
            'paymentType': {'required': True},
            'paymentAmount': {'required': True, 'min_value': 0},
            'estimatedHours': {'required': True},
            'deadline': {'required': True},
            'status': {'required': False},
            'work_style': {'required': False},
            'collaboration': {'required': False},
            'application_deadline': {'required': False},
            'max_applicants': {'required': False}
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
        project = super().create(validated_data)
        
        # Create project skills
        for skill in skills:
            ProjectSkill.objects.create(project=project, name=skill)
        return project

    def to_representation(self, instance):
        # Return unified representation with single 'skills' field
        data = ProjectSerializer(instance, context=self.context).data
        return data


class ProjectUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating projects
    """
    project_timezone = TimeZoneSerializerField(required=False)
    company_name = serializers.CharField(source='company.company_name', read_only=True)

    class Meta:
        model = Project
        fields = (
            'title', 'description', 'company_name', 'category', 'skills',
            'paymentType', 'paymentAmount', 'payment_currency', 'estimatedHours', 
            'deadline', 'status', 'work_style', 'hasTemporaryOption', 'temporaryDuration',
            'project_timezone'
        )
        extra_kwargs = {
            'title': {'required': True},
            'description': {'required': True},
            'company_name': {'required': True},
            'category': {'required': True},
            'skills': {'required': True},
            'paymentType': {'required': True},
            'paymentAmount': {'required': True, 'min_value': 0},
            'estimatedHours': {'required': True},
            'deadline': {'required': True},
            'status': {'choices': Project.STATUS_CHOICES},
        }

    def validate(self, attrs):
        # Bug #23: Block transition to `active` when the deadline is already past.
        # Without this, the project saves as active, then the next read used to
        # auto-close it; even after removing that side effect, an active project
        # with a stale deadline shouldn't exist.
        new_status = attrs.get('status', getattr(self.instance, 'status', None))
        if new_status == 'active':
            deadline = attrs.get('deadline', getattr(self.instance, 'deadline', None))
            if deadline and deadline < timezone.now().date():
                raise serializers.ValidationError({
                    'status': [ErrorDetail(
                        'Cannot mark project active: deadline has already passed. '
                        'Update the deadline first.',
                        code='deadline_in_past',
                    )]
                })
        return attrs