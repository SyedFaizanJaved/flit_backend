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
    company_name = serializers.CharField(source='company.company_name', read_only=True, default='Anonymous Company')
    company_id = serializers.IntegerField(source='company.id', read_only=True, default=None)
    is_applied = serializers.SerializerMethodField()
    category = serializers.CharField(source='get_category_display', read_only=True)
    paymentType = serializers.CharField(source='get_paymentType_display', read_only=True)
    work_style = serializers.CharField(source='get_work_style_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    effective_status = serializers.SerializerMethodField()
    education_level = serializers.CharField(source='get_education_level_display', read_only=True)
    project_timezone = TimeZoneSerializerField()

    class Meta:
        model = Project
        fields = (
            'id', 'title', 'description', 'company_name', 'company_id', 'category', 'estimatedHours',
            'paymentType', 'paymentAmount', 'payment_currency', 'skills', 'deadline', 'required_skills',
            'status', 'is_expired', 'effective_status',
            'work_style', 'education_level', 'created_at', 'updated_at', 'is_applied',
            'hasTemporaryOption', 'temporaryDuration', 'project_timezone'
        )
        read_only_fields = ('employer', 'created_at', 'updated_at', 'slug')

    def get_effective_status(self, obj):
        """Display value that reflects a passed deadline immediately — see ProjectListSerializer."""
        return 'Closed' if obj.effective_status == 'closed' else obj.get_status_display()
    
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
    company_name = serializers.CharField(source='company.company_name', read_only=True, default='Anonymous Company')
    company_id = serializers.IntegerField(source='company.id', read_only=True, default=None)
    company_logo = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    is_applied = serializers.SerializerMethodField()
    application_details = serializers.SerializerMethodField()
    application_count = serializers.SerializerMethodField()
    category = serializers.CharField(source='get_category_display', read_only=True)
    paymentType = serializers.CharField(source='get_paymentType_display', read_only=True)
    work_style = serializers.CharField(source='get_work_style_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    effective_status = serializers.SerializerMethodField()
    project_timezone = TimeZoneSerializerField(read_only=True)
    education_level = serializers.CharField(source='get_education_level_display', read_only=True)

    class Meta:
        model = Project
        fields = ('id', 'title', 'description', 'company_name', 'company_id','company_logo', 'category',
                 'estimatedHours', 'paymentType', 'paymentAmount', 'payment_currency', 'deadline', 'status',
                 'is_expired', 'effective_status',
                 'work_style', 'education_level', 'created_at', 'skills', 'is_applied', 'application_details',
                 'application_count', 'hasTemporaryOption', 'temporaryDuration', 'project_timezone')

    def get_effective_status(self, obj):
        """What the employer should see now.

        `status` is left as the stored value because the edit form writes back to it;
        this is the display value, which reflects expiry immediately rather than
        waiting for close_expired_projects to run.
        """
        if obj.status == 'active' and obj.is_expired:
            return 'Closed'
        return obj.get_status_display()
    
    def get_skills(self, obj):
        # Get skills from ProjectSkill model and capitalize first letter
        # ponytail: iterate .all() rather than .values_list() — values_list bypasses
        # the prefetch cache and re-queries per row. Uncached this still costs one
        # query, same as before.
        skills = [s.name for s in obj.required_skills.all()]
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]
    
    def get_company_logo(self, obj):
        """
        Get the company logo URL.
        """
        return obj.company.logo.url if obj.company and obj.company.logo else None    

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

        # ponytail: PublicProjectViewSet annotates this so a 24-project page costs 0
        # queries here instead of 24. Other call sites don't annotate and fall through.
        annotated = getattr(obj, 'is_applied_annotated', None)
        if annotated is not None:
            return annotated

        # ponytail: dropped an `all_apps = ProjectApplication.objects.filter(...)`
        # here — its result was never read, so it was a wasted query per row.
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
        # ponytail: annotated by PublicProjectViewSet; falls back for other call sites.
        annotated = getattr(obj, 'active_application_count', None)
        if annotated is not None:
            return annotated
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
            # ponytail: PublicProjectViewSet prefetches this candidate's own
            # non-withdrawn applications into `my_applications` (at most one per
            # project), so this costs 0 queries there. Other call sites fall through.
            prefetched = getattr(obj, 'my_applications', None)
            if prefetched is not None:
                if not prefetched:
                    return None
                application = prefetched[0]
                return {
                    'application_id': application.id,
                    'candidate_name': application.candidate.full_name,
                    'status': application.status,
                    'user_id': request.user.id,
                    'candidate_id': application.candidate.id,
                    'profile_image': request.build_absolute_uri(application.candidate.profile_image.url) if hasattr(application.candidate, 'profile_image') and application.candidate.profile_image else None
                }
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
        # Mirrors JobCreateSerializer: title/description/category/skills for the
        # matching engine, plus the payment fields. The rest default.
        extra_kwargs = {
            'title': {'required': True},
            'description': {'required': True},
            'company': {'required': False, 'allow_null': True},
            'category': {'required': True},
            'paymentType': {'required': True},
            'paymentAmount': {'required': True, 'min_value': 0},
            'estimatedHours': {'required': False, 'allow_blank': True},
            'deadline': {'required': False},
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
        # A posting with no company is deliberate ("post anonymously"), but only
        # when the employer genuinely has none. Fall back to their linked company
        # so a stale client that omits the field can't orphan a posting by mistake.
        if not validated_data.get('company'):
            employer = getattr(self.context['request'].user, 'employer_profile', None)
            if employer and employer.company_id:
                validated_data['company'] = employer.company
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
    company_name = serializers.CharField(source='company.company_name', read_only=True, default='Anonymous Company')

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
            'estimatedHours': {'required': False, 'allow_blank': True},
            'deadline': {'required': False},
            'status': {'choices': Project.STATUS_CHOICES},
        }

    def validate(self, attrs):
        # Block transition to `active` when the deadline is already past.
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