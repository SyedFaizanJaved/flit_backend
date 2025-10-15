from rest_framework import serializers
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
    
    class Meta:
        model = Project
        fields = (
            'id', 'title', 'description', 'company_name', 'category', 'estimatedHours',
            'paymentType', 'paymentAmount', 'skills', 'deadline', 'required_skills',
            'status', 'created_at', 'updated_at'
        )
        read_only_fields = ('employer', 'created_at', 'updated_at', 'slug')
    
    def create(self, validated_data):
        validated_data['employer'] = self.context['request'].user
        return super().create(validated_data)


class ProjectListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing projects
    """
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    # company_logo = serializers.CharField(source='company.logo.url', read_only=True)
    
    class Meta:
        model = Project
        fields = ('id', 'title','description', 'company_name', 'category', 'estimatedHours', 'paymentType', 'paymentAmount', 'deadline', 'status', 'created_at', 'skills')
        # fields = ('id', 'title', 'company_name', 'company_logo', 'category', 'complexity',
        #          'paymentType', 'paymentAmount', 'estimatedHours', 'budget_min', 'budget_max',
        #          'budget_currency', 'work_style', 'status', 'created_at')


class ProjectCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating projects
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
        model = Project
        fields = (
            'title', 'description', 'company', 'category', 'skills', 'required_skills',
            'paymentType', 'paymentAmount', 'estimatedHours', 'deadline','status'
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
    company_name = serializers.CharField(source='company.company_name', read_only=True)

    class Meta:
        model = Project
        fields = (
            'title', 'description', 'company_name', 'category', 'skills',
            'paymentType', 'paymentAmount', 'estimatedHours', 
            'deadline', 'status'
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
        }