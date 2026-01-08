from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Employer, EmployerPreference, EmployerCompliance, CandidateAction
from candidates.models import Candidate

User = get_user_model()


class EmployerRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for employer registration"""
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'first_name', 'last_name']
        extra_kwargs = {
            'password': {'write_only': True},
            'first_name': {'required': True},
            'last_name': {'required': True}
        }
    
    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            is_employer=True
        )
        Employer.objects.create(
            user=user,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name']
        )
        return user


class EmployerSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    
    def get_company_id(self, obj):
        return obj.company.id if obj.company else None
    
    company_id = serializers.SerializerMethodField(method_name='get_company_id')
    
    class Meta:
        model = Employer
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

    def get_company(self, obj):
        if obj.company_id:
            return obj.company_id
        try:
            latest_company = obj.user.created_companies.order_by('-created_at').first()
            return latest_company.id if latest_company else None
        except Exception:
            return None

    def get_profile_completed(self, obj):
        return bool(getattr(obj, 'is_profile_complete', False))


class EmployerListSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    host_email = serializers.SerializerMethodField()
    
    def get_company_id(self, obj):
        return obj.company.id if obj.company else None
    
    company_id = serializers.SerializerMethodField(method_name='get_company_id')
    
    class Meta:
        model = Employer
        fields = (
            'id', 'full_name',
            'company_id', 'company_name',
            'profile_completed', 'created_at',
            'host_email'
        )

    def get_profile_completed(self, obj):
        return bool(getattr(obj, 'is_profile_complete', False))
            
    def get_host_email(self, obj):
        request = self.context.get('request')
        if request and hasattr(request.user, 'employer_profile'):
            return obj.user.email if obj.user else None
        return None


class EmployerProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employer
        fields = (
            'first_name', 'last_name', 'phone', 'position', 'department',
            'profile_picture', 'bio',
            'company',
        )

    def update(self, instance, validated_data):
        if 'first_name' in validated_data and 'last_name' in validated_data:
            instance.basic_info_completed = True
        if 'company' in validated_data and validated_data.get('company'):
            instance.company_info_completed = True

        updated = super().update(instance, validated_data)

        try:
            user = instance.user
            if instance.is_profile_complete and not getattr(user, 'profile_completed', False):
                user.profile_completed = True
                user.save(update_fields=['profile_completed', 'updated_at'])
        except Exception:
            pass

        return updated


class EmployerPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployerPreference
        fields = '__all__'
        read_only_fields = ('employer',)


class EmployerComplianceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployerCompliance
        fields = '__all__'
        read_only_fields = ('employer', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['employer'] = self.context['request'].user.employer_profile
        return super().create(validated_data)


class EmployerConversationSummarySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        from candidates.models import Candidate
        model = Candidate
        fields = ('id', 'title', 'last_message_time', 'unread_count')
    

class EmployerCompanyConversationSummarySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    industry = serializers.CharField(source='company.industry', read_only=True)
    logo = serializers.ImageField(source='company.logo', read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True)
    last_seen = serializers.DateTimeField(source='user.last_login', read_only=True)
    unread_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Employer
        fields = ('id', 'company_name', 'industry', 'logo', 'last_message_time', 'last_seen', 'unread_count')


class CandidateActionSerializer(serializers.ModelSerializer):
    employer = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = CandidateAction
        fields = ['id', 'employer', 'candidate_id', 'action', 'created_at']
        read_only_fields = ['employer', 'created_at']

    def validate(self, data):
        action = data.get('action')
        if action not in ['pass', 'reject']:
            raise serializers.ValidationError("action must be 'pass' or 'reject'")
        return data


class CandidateActionDetailSerializer(serializers.ModelSerializer):
    """
    Optimized - No N+1, no invalid prefetch
    """
    user_id = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()

    class Meta:
        model = CandidateAction
        fields = [
            'id', 'user_id', 'action', 'created_at',
            'full_name', 'title', 'profile_image', 'skills',
            'candidate_id', 'employer_id'
        ]

    # Bulk fetch candidates once (no prefetch needed for skills)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._candidates_cache = {}

    def get_user_id(self, obj):
        candidate = self._candidates_cache.get(str(obj.candidate_id))
        return candidate.user.id if candidate and candidate.user else None

    def get_full_name(self, obj):
        candidate = self._candidates_cache.get(str(obj.candidate_id))
        return candidate.full_name if candidate else "Unknown"

    def get_title(self, obj):
        candidate = self._candidates_cache.get(str(obj.candidate_id))
        return candidate.title or "No title" if candidate else "No title"

    def get_profile_image(self, obj):
        candidate = self._candidates_cache.get(str(obj.candidate_id))
        if not candidate or not candidate.profile_image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(candidate.profile_image.url)
        return candidate.profile_image.url

    def get_skills(self, obj):
        candidate = self._candidates_cache.get(str(obj.candidate_id))
        if not candidate:
            return []
            
        raw_skills = getattr(candidate, 'skills', [])
        if isinstance(raw_skills, (list, tuple)):
            return raw_skills[:10]  # list of strings or dicts
        elif isinstance(raw_skills, dict):
            return [{'name': k, 'level': v} for k, v in raw_skills.items()][:10]
        return []

    def to_representation(self, instance):
        # Bulk load all candidates in list view
        if not self._candidates_cache:
            # Get all instances for the page (paginated queryset)
            instances = self.instance if hasattr(self.instance, '__iter__') else [instance]
            candidate_ids = [obj.candidate_id for obj in instances if obj.candidate_id]
            
            if candidate_ids:
                candidates = Candidate.objects.filter(id__in=candidate_ids).select_related('user')
                self._candidates_cache = {str(c.id): c for c in candidates}

        candidate = self._candidates_cache.get(str(instance.candidate_id))

        data = super().to_representation(instance)

        if candidate:
            data['user_id'] = candidate.user.id if candidate.user else None
            data['full_name'] = candidate.full_name or "Unknown"
            data['title'] = candidate.title or "No title"

            # Profile image
            data['profile_image'] = (
                self.context['request'].build_absolute_uri(candidate.profile_image.url)
                if candidate.profile_image and self.context.get('request')
                else candidate.profile_image.url if candidate.profile_image else None
            )

            # Skills - safe handling for JSONField / list / dict
            raw_skills = getattr(candidate, 'skills', [])
            if isinstance(raw_skills, (list, tuple)):
                data['skills'] = raw_skills[:10]  # list of strings or dicts
            elif isinstance(raw_skills, dict):
                data['skills'] = [{'name': k, 'level': v} for k, v in raw_skills.items()][:10]
            else:
                data['skills'] = []
        else:
            data.update({
                'user_id': None,
                'full_name': "Candidate Not Found",
                'title': "No title",
                'profile_image': None,
                'skills': []
            })

        return data