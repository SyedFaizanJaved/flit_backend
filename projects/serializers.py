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
        fields = ('id', 'title', 'description', 'company_name', 'category', 'estimatedHours', 'paymentType', 'paymentAmount', 'deadline', 'required_skills', 'status', 'created_at', 'updated_at')
        # fields = '__all__'
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
        fields = ('id', 'title', 'company_name', 'category', 'estimatedHours', 'paymentType', 'paymentAmount', 'deadline', 'status', 'created_at')
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
    # deliverables = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    # tools = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    # technologies = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    
    class Meta:
        model = Project
        fields = ('title', 'description', 'company', 'category', 'skills', 'paymentType',
                 'paymentAmount', 'estimatedHours', 'deadline')
        # fields = ('title', 'description', 'company', 'category', 'skills', 'paymentType',
        #          'paymentAmount', 'estimatedHours', 'deliverables', 'tools', 'technologies',
        #          'complexity', 'budget_min', 'budget_max', 'duration_days', 'start_date',
        #          'deadline', 'work_style', 'collaboration', 'application_deadline', 'max_applicants')
    
    def create(self, validated_data):
        skills = validated_data.pop('skills', [])
        # deliverables = validated_data.pop('deliverables', [])
        # tools = validated_data.pop('tools', [])
        # technologies = validated_data.pop('technologies', [])
        
        # Ensure employer is set from the authenticated user
        validated_data['employer'] = self.context['request'].user
        # Persist flat skills list into model JSONField
        validated_data['skills'] = skills
        project = super().create(validated_data)
        
        # Create project skills
        for skill in skills:
            ProjectSkill.objects.create(project=project, name=skill)
        
        # Update JSON fields
        # project.deliverables = deliverables
        # project.tools = tools
        # project.technologies = technologies
        # project.save()
        
        return project

    def to_representation(self, instance):
        # Return full representation
        return ProjectSerializer(instance, context=self.context).data


class ProjectUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating projects
    """
    class Meta:
        model = Project
        fields = ('title', 'description', 'category', 'paymentType', 'paymentAmount',
                 'estimatedHours', 'deadline', 'status')
        # fields = ('title', 'description', 'category', 'paymentType', 'paymentAmount',
        #          'estimatedHours', 'complexity', 'budget_min', 'budget_max', 'duration_days',
        #          'start_date', 'deadline', 'work_style', 'collaboration', 'application_deadline',
        #          'max_applicants', 'status')