from rest_framework import serializers
from .models import JobApplication, ProjectApplication, Interview, ApplicationMessage, InterviewRequest


class JobApplicationSerializer(serializers.ModelSerializer):
    """
    Serializer for job applications
    """
    candidate_name = serializers.CharField(
        source='candidate.full_name', read_only=True)
    job_title = serializers.CharField(source='job.title', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = JobApplication
        fields = '__all__'
        read_only_fields = (
            'candidate', 'employer', 'company', 'applied_at', 'last_updated', 'overall_match_score', 'skills_match_score',
            'experience_match_score', 'education_match_score', 'location_match_score', 'salary_match_score'
        )

    def create(self, validated_data):
        request = self.context['request']
        candidate = request.user.candidate_profile
        job = validated_data['job']

        # Prevent duplicate applications through list endpoint
        from .models import JobApplication
        if JobApplication.objects.filter(candidate=candidate, job=job).exists():
            raise serializers.ValidationError(
                {'error': 'You have already apply for this job'})

        validated_data['candidate'] = candidate
        validated_data['employer'] = job.employer
        validated_data['company'] = job.company

        # Match score calculation
        scores = self.calculate_match_scores(candidate, job)

        validated_data.update(scores)

        return super().create(validated_data)

    # -----------------------------
    # Helper methods for match score
    # -----------------------------
    def calculate_match_scores(self, candidate, job):
        skills_score = self.calculate_skills_score(candidate, job)
        experience_score = self.calculate_experience_score(candidate, job)
        education_score = self.calculate_education_score(candidate, job)
        location_score = self.calculate_location_score(candidate, job)
        salary_score = self.calculate_salary_score(candidate, job)

        # Total weight
        total_weight = (
            job.experience_weight + job.education_weight +
            job.location_weight + 10  # salary ka fixed weight rakha
        )
        skills_weight = 100 - total_weight  # skills ke liye bacha hua weight

        weighted_score = (
            (skills_score * skills_weight) +
            (experience_score * job.experience_weight) +
            (education_score * job.education_weight) +
            (location_score * job.location_weight) +
            (salary_score * 10)
        ) / 100

        return {
            'skills_match_score': skills_score,
            'experience_match_score': experience_score,
            'education_match_score': education_score,
            'location_match_score': location_score,
            'salary_match_score': salary_score,
            'overall_match_score': int(weighted_score)
        }

    def calculate_skills_score(self, candidate, job):
        if not job.skills:
            return 0
        matched = len(set(candidate.skills) & set(job.skills))
        score = int((matched / len(job.skills)) * 100)
        return score if score >= job.skill_match_threshold else score

    def calculate_experience_score(self, candidate, job):
        # Dummy example: tumhe apne candidate model me exp_years add karna hoga
        if hasattr(candidate, 'experience_years') and candidate.experience_years:
            if job.experienceLevel == 'entry' and candidate.experience_years < 2:
                return 100
            elif job.experienceLevel == 'mid' and 2 <= candidate.experience_years < 5:
                return 90
            elif job.experienceLevel == 'senior' and candidate.experience_years >= 5:
                return 80
        return 50  # default medium score

    def calculate_education_score(self, candidate, job):
        # Dummy: tumhe candidate.education_level check karna hoga
        if hasattr(candidate, 'education_level') and candidate.education_level:
            return 100 if candidate.education_level == job.category else 70
        return 50

    def calculate_location_score(self, candidate, job):
        if job.workStyle == 'remote':
            return 100
        if candidate.location and job.location and candidate.location == job.location:
            return 100
        return 50

    def calculate_salary_score(self, candidate, job):
        if candidate.min_salary and job.salaryRangeMax:
            if candidate.min_salary <= job.salaryRangeMax:
                return 100
            elif candidate.min_salary <= job.salaryRangeMax * 1.2:
                return 70
        return 0


class ProjectApplicationSerializer(serializers.ModelSerializer):
    """
    Serializer for project applications
    """
    candidate_name = serializers.CharField(
        source='candidate.full_name', read_only=True)
    project_title = serializers.CharField(
        source='project.title', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ProjectApplication
        fields = '__all__'
        read_only_fields = ('candidate', 'employer',
                            'company', 'applied_at', 'last_updated')

    def create(self, validated_data):
        candidate = self.context['request'].user.candidate_profile
        project = validated_data['project']

        # Prevent duplicate applications through list endpoint
        from .models import ProjectApplication
        if ProjectApplication.objects.filter(candidate=candidate, project=project).exists():
            raise serializers.ValidationError(
                {'error': 'You have already apply for this project'})

        validated_data['candidate'] = candidate
        validated_data['employer'] = project.employer
        validated_data['company'] = project.company
        return super().create(validated_data)


class InterviewSerializer(serializers.ModelSerializer):
    """
    Serializer for interviews
    """
    job_title = serializers.CharField(
        source='job_application.job.title', read_only=True)
    project_title = serializers.CharField(
        source='project_application.project.title', read_only=True)
    candidate_name = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_candidate_name(self, obj):
        if obj.job_application:
            return obj.job_application.candidate.full_name
        elif obj.project_application:
            return obj.project_application.candidate.full_name
        return None


class ApplicationMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for application messages
    """
    sender_name = serializers.CharField(source='sender.email', read_only=True)
    job_title = serializers.CharField(
        source='job_application.job.title', read_only=True)
    project_title = serializers.CharField(
        source='project_application.project.title', read_only=True)

    class Meta:
        model = ApplicationMessage
        fields = '__all__'
        read_only_fields = ('created_at',)

    def create(self, validated_data):
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)


class InterviewRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for interview requests
    """
    job_title = serializers.CharField(
        source='job_application.job.title', read_only=True)
    project_title = serializers.CharField(
        source='project_application.project.title', read_only=True)

    class Meta:
        model = InterviewRequest
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at','meetLink')

    def update(self, instance, validated_data):
        if set(validated_data.keys()) != {'status'}:
            raise serializers.ValidationError("Only status can be updated.")
        return super().update(instance, validated_data)

    def create(self, validated_data):
        return super().create(validated_data)



class JobApplicationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing job applications
    """
    candidate_name = serializers.CharField(
        source='candidate.full_name', read_only=True)
    job_title = serializers.CharField(source='job.title', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    candidate_user_id = serializers.IntegerField(source='candidate.user.id', read_only=True)
    candidate_profile_image = serializers.ImageField(source='candidate.profile_image', read_only=True)

    class Meta:
        model = JobApplication
        fields = ('id', 'candidate_name', 'candidate_user_id', 'job_title', 'company_name', 'status',
                  'candidate_profile_image', 'applied_at', 'is_shortlisted', 'is_rejected', 'coverLetter')


class ProjectApplicationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing project applications
    """
    candidate_name = serializers.CharField(
        source='candidate.full_name', read_only=True)
    project_title = serializers.CharField(
        source='project.title', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    candidate_user_id = serializers.IntegerField(source='candidate.user.id', read_only=True)
    candidate_profile_image = serializers.ImageField(source='candidate.profile_image', read_only=True)


    class Meta:
        model = ProjectApplication
        fields = ('id', 'candidate_name', 'candidate_user_id', 'project_title', 'company_name', 'status',
                  'candidate_profile_image','coverLetter', 'overall_match_score', 'applied_at', 'is_shortlisted', 'is_rejected')
