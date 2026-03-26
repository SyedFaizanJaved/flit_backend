import json
import logging
from rest_framework import serializers
from .models import Candidate, ReferenceRequest, WorkDNAQuestion, Education, Experience, Achievement
from companies.models import Company
from jobs.serializers import JobListSerializer
from projects.serializers import ProjectListSerializer
from utils.timezone_helpers import convert_to_user_timezone, format_datetime_for_user


class DiscoverTalentSerializer(serializers.ModelSerializer):
    """
    Serializer for discover_talent endpoint with minimal required fields
    """
    fullName = serializers.CharField(source='full_name', read_only=True)
    title = serializers.SerializerMethodField()
    bio = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    skills = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    lastSeen = serializers.SerializerMethodField()
    profile_views_display = serializers.SerializerMethodField()
    minSalary = serializers.SerializerMethodField()
    maxSalary = serializers.SerializerMethodField()
    profileImage = serializers.SerializerMethodField()
    userId = serializers.SerializerMethodField()
    seniorityLevel = serializers.SerializerMethodField()
    
    def get_userId(self, obj):
        return obj.user.id if obj.user else None
    
    def get_title(self, obj):
        return obj.title.title() if obj.title else obj.title
        
    def get_profileImage(self, obj):
        if obj.profile_image and hasattr(obj.profile_image, 'url'):
            return self.context['request'].build_absolute_uri(obj.profile_image.url)
        return None
        
    def get_minSalary(self, obj):
        return getattr(obj, 'min_salary', None) or getattr(obj, 'minSalary', None)
        
    def get_maxSalary(self, obj):
        return getattr(obj, 'max_salary', None) or getattr(obj, 'maxSalary', None)
        
    def get_profile_views_display(self, obj):
        views = getattr(obj, 'profile_views', 0)
        if views >= 1000:
            return f"{views/1000:.1f}k"
        return str(views)
        
    def get_lastSeen(self, obj):
        last_seen = getattr(obj, 'last_seen', None)
        if last_seen:
            from django.utils import timezone
            from django.utils.timesince import timesince
            now = timezone.now()
            if last_seen > now - timezone.timedelta(days=1):
                return f"{timesince(last_seen, now).split(', ')[0]} ago"
            return last_seen.strftime('%b %d, %Y')
        return 'Never'
        
    def get_availability(self, obj):
        return getattr(obj, 'availability', 'Not specified') or 'Not specified'

    class Meta:
        model = Candidate
        fields = [
            'id', 'fullName', 'title', 'bio', 'skills', 'location',
            'availability', 'lastSeen', 'profile_views_display',
            'minSalary', 'maxSalary', 'profileImage', 'userId', 'seniorityLevel'
        ]

    def get_skills(self, obj):
        # Return a list of skill names if skills field exists, otherwise empty list
        if hasattr(obj, 'skills') and obj.skills:
            # Handle both list and queryset cases
            if hasattr(obj.skills, 'all'):  # It's a queryset
                skills = [skill.name for skill in obj.skills.all()]
                return [skill.title() if isinstance(skill, str) else skill for skill in skills]
            elif isinstance(obj.skills, list):  # It's already a list
                skills = [skill.name if hasattr(skill, 'name') else skill for skill in obj.skills]
                return [skill.title() if isinstance(skill, str) else skill for skill in skills]
            elif isinstance(obj.skills, str):  # It's a JSON string
                try:
                    skills_list = json.loads(obj.skills)
                    if isinstance(skills_list, list):
                        return [skill.title() if isinstance(skill, str) else skill for skill in skills_list]
                except json.JSONDecodeError:
                    pass
        return []

    def get_availability(self, obj):
        # Return only the availability type display (capitalized)
        return obj.get_availability_type_display() if hasattr(obj, 'get_availability_type_display') else getattr(obj, 'availability_type', None)

    def get_lastSeen(self, obj):
        # Return last login time if user exists and has last_login
        if hasattr(obj, 'user') and hasattr(obj.user, 'last_login') and obj.user.last_login:
            request = self.context.get('request')
            if request and hasattr(request, 'user') and request.user.is_authenticated:
                return format_datetime_for_user(obj.user.last_login, request.user)
            return obj.user.last_login.isoformat()
        return None

    def get_profile_views_display(self, obj):
        # Return profile views count if exists, otherwise 0
        return getattr(obj, 'profile_views', 0)

    def get_minSalary(self, obj):
        # Return minimum salary if exists, otherwise None
        return getattr(obj, 'min_salary', None)
        
    def get_maxSalary(self, obj):
        # Return maximum salary if exists, otherwise None
        return getattr(obj, 'max_salary', None)

    def get_profileImage(self, obj):
        # Return profile image URL if exists, otherwise None
        if hasattr(obj, 'profile_image') and obj.profile_image:
            try:
                # Try to get the URL directly without checking existence first
                # This avoids the extra HEAD request that might be failing with 403
                return obj.profile_image.url
            except Exception as e:
                # Log the error for debugging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error getting profile image URL for user {obj.id}: {str(e)}")
                return None
        return None
        
    def get_user(self, obj):
        # Return user ID in the same format as the detailed view
        return obj.user.id if hasattr(obj, 'user') and obj.user else None
    
    def get_seniorityLevel(self, obj):
        # Return seniority level in the same format as the detailed view
        return obj.seniority_level if hasattr(obj, 'seniority_level') else None

class ReferenceRequestResponseSerializer(serializers.ModelSerializer):
    """
    Serializer for reference request responses (used in candidate profile)
    """
    class Meta:
        model = ReferenceRequest
        fields = [
            'id',
            'reference_name',
            'reference_email',
            'suggested_relationship',
            'reply_message'
        ]
        read_only_fields = fields

class CandidateSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    profile_completed = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    resume_url = serializers.SerializerMethodField()
    ai_resume_url = serializers.SerializerMethodField()
    video_intro_url = serializers.SerializerMethodField()
    viewers_count = serializers.SerializerMethodField()
    profile_views_display = serializers.SerializerMethodField()
    reference_responses = serializers.SerializerMethodField()
    passion_projects = serializers.SerializerMethodField()
    superpowers = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    portfolio_links = serializers.SerializerMethodField()
    preferred_roles = serializers.SerializerMethodField()
    education = serializers.SerializerMethodField()
    experience = serializers.SerializerMethodField()
    achievements = serializers.SerializerMethodField()
    user_timezone = serializers.SerializerMethodField()
    
    # Formatted fields
    title = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    work_style = serializers.CharField(source='get_work_style_display', read_only=True)
    availability_type = serializers.CharField(source='get_availability_type_display', read_only=True)
    seniority_level = serializers.CharField(source='get_seniority_level_display', read_only=True)
    
    def _parse_json_field(self, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return []
        return value or []
    
    def get_superpowers(self, obj):
        return self._parse_json_field(obj.superpowers)
        
    def get_skills(self, obj):
        skills = self._parse_json_field(obj.skills)
        # Capitalize first letter of each skill
        return [skill.title() if isinstance(skill, str) else skill for skill in skills]
        
    def get_portfolio_links(self, obj):
        return self._parse_json_field(obj.portfolio_links)
        
    def get_preferred_roles(self, obj):
        return self._parse_json_field(obj.preferred_roles)
    
    def get_title(self, obj):
        return obj.title.title() if obj.title else obj.title
    
    def get_location(self, obj):
        return obj.location.title() if obj.location else obj.location
    
    def get_education(self, obj):
        education_records = obj.education.all().order_by('-start_date')
        data = []
        for edu in education_records:
            data.append({
                'id': edu.id,
                'institution': edu.institution,
                'degree': edu.get_degree_display(),
                'field_of_study': edu.field_of_study,
                'start_date': edu.start_date,
                'end_date': edu.end_date,
                'is_current': edu.is_current,
                'grading_system': edu.grading_system,
                'gpa': edu.gpa,
                'grade': edu.grade,
                'total_marks': edu.total_marks,
                'obtained_marks': edu.obtained_marks,
                'description': edu.description,
                'created_at': edu.created_at,
                'updated_at': edu.updated_at
            })
        return data
    
    def get_experience(self, obj):
        experience_records = obj.experience.all().order_by('-start_date')
        data = []
        for exp in experience_records:
            data.append({
                'id': exp.id,
                'company_name': exp.company_name,
                'position': exp.position,
                'employment_type': exp.get_employment_type_display(),
                'start_date': exp.start_date,
                'end_date': exp.end_date,
                'is_current': exp.is_current,
                'location': exp.location,
                'description': exp.description,
                'achievements': exp.achievements,
                'skills_used': exp.skills_used,
                'created_at': exp.created_at,
                'updated_at': exp.updated_at
            })
        return data
    
    def get_achievements(self, obj):
        achievement_records = obj.achievements.all().order_by('-date_achieved')
        data = []
        for ach in achievement_records:
            data.append({
                'id': ach.id,
                'title': ach.title,
                'achievement_type': ach.get_achievement_type_display(),
                'description': ach.description,
                'date_achieved': ach.date_achieved,
                'issuer': ach.issuer,
                'url': ach.url,
                'image': self._get_file_url(ach.image) if ach.image else None,
                'created_at': ach.created_at,
                'updated_at': ach.updated_at
            })
        return data
    
    def _get_file_url(self, file_field):
        """Helper method to get the URL for a file field"""
        if not file_field:
            return None
            
        # Get the URL from the file field
        try:
            url = file_field.name  # Get the stored path/URL
            
            # If it's already a full URL, return it as is
            if url.startswith(('http://', 'https://')):
                return url
            
            # Try to get the URL using Django's storage system first
            if hasattr(file_field, 'url'):
                try:
                    full_url = file_field.url
                    if hasattr(self, 'context') and 'request' in self.context:
                        return self.context['request'].build_absolute_uri(full_url)
                    return full_url
                except:
                    pass
                
            # Fallback to manual URL construction
            # Determine the base path based on the field name
            if hasattr(file_field, 'field'):
                if file_field.field.name == 'resume_url':
                    base_path = 'candidates/resumes/'
                elif file_field.field.name == 'ai_resume_url':
                    base_path = 'candidates/resumes/'
                elif file_field.field.name == 'video_intro_url':
                    base_path = 'candidates/videos/'
                elif file_field.field.name == 'profile_image':
                    base_path = 'candidates/profile_images/'
                elif file_field.field.name == 'image':
                    base_path = 'candidates/achievements/'
                else:
                    base_path = ''
                
                # If the URL is just a filename, prepend the base path
                if '/' not in url and base_path:
                    url = f"{base_path}{url}"
            
            # If it's a path, construct the full URL
            if hasattr(file_field.storage, 'bucket_name'):
                # For S3 storage
                full_url = f"https://{file_field.storage.bucket_name}.s3.{file_field.storage.region_name}.amazonaws.com/{url.lstrip('/')}"
            else:
                # For other storage backends, use the storage's url method
                full_url = file_field.storage.url(url)
            
            # Build absolute URL if request is available
            if hasattr(self, 'context') and 'request' in self.context:
                return self.context['request'].build_absolute_uri(full_url)
            return full_url
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating URL for {file_field}: {str(e)}")
            return None
    
    def get_profile_image(self, obj):
        return self._get_file_url(obj.profile_image)
        
    def get_resume_url(self, obj):
        return self._get_file_url(obj.resume_url)
        
    def get_ai_resume_url(self, obj):
        return self._get_file_url(obj.ai_resume_url)
        
    def get_video_intro_url(self, obj):
        return self._get_file_url(obj.video_intro_url)
    
    class Meta:
        model = Candidate
        fields = [
            "id", "full_name", "profile_completed", "title", "bio", "work_style", "availability_type",
            "skills", "superpowers", "preferred_roles", "min_salary", "max_salary", "salary_currency",
            "resume_url", "ai_resume_url", "video_intro_url",
            "video_transcription", "privacy_completed", "location", "created_at", "updated_at", "user",
            "profile_image", "profile_views", "viewers_count", "profile_views_display",
            "passion_projects", "reference_responses", "portfolio_links", "seniority_level", "is_available",
            "resume_data", "education", "experience", "achievements", "user_timezone"
        ]
        read_only_fields = ("user", "created_at", "updated_at")
    
    def _get_request_user(self):
        """Get the authenticated user from the request context."""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return request.user
        return None
    
    def _convert_dt(self, dt):
        """Convert a datetime to the request user's timezone."""
        user = self._get_request_user()
        if user and dt:
            return format_datetime_for_user(dt, user)
        return dt.isoformat() if dt else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = self._get_request_user()
        if user:
            # Convert top-level datetime fields
            for field_name in ('created_at', 'updated_at'):
                if data.get(field_name):
                    raw_dt = getattr(instance, field_name, None)
                    if raw_dt:
                        data[field_name] = format_datetime_for_user(raw_dt, user)
            
            # Convert education datetime fields
            if data.get('education'):
                for edu in data['education']:
                    for dt_field in ('created_at', 'updated_at'):
                        if edu.get(dt_field):
                            edu_obj_dt = edu[dt_field]
                            if hasattr(edu_obj_dt, 'isoformat'):
                                edu[dt_field] = format_datetime_for_user(edu_obj_dt, user)
            
            # Convert experience datetime fields
            if data.get('experience'):
                for exp in data['experience']:
                    for dt_field in ('created_at', 'updated_at'):
                        if exp.get(dt_field):
                            exp_obj_dt = exp[dt_field]
                            if hasattr(exp_obj_dt, 'isoformat'):
                                exp[dt_field] = format_datetime_for_user(exp_obj_dt, user)
            
            # Convert achievement datetime fields
            if data.get('achievements'):
                for ach in data['achievements']:
                    for dt_field in ('created_at', 'updated_at'):
                        if ach.get(dt_field):
                            ach_obj_dt = ach[dt_field]
                            if hasattr(ach_obj_dt, 'isoformat'):
                                ach[dt_field] = format_datetime_for_user(ach_obj_dt, user)
        
        return data
    
    def get_passion_projects(self, obj):
        return obj.passion_projects
    
    def get_user_timezone(self, obj):
        """Get timezone from related User model."""
        if obj.user and hasattr(obj.user, 'user_timezone') and obj.user.user_timezone:
            return str(obj.user.user_timezone)
        return 'America/New_York'
    
    def get_reference_responses(self, obj):
        # Get all accepted reference requests with reply messages
        references = ReferenceRequest.objects.filter(
            candidate=obj,
            status='accepted',
            reply_message__isnull=False
        ).order_by('-updated_at')
        return ReferenceRequestResponseSerializer(references, many=True).data
    
    def update(self, instance, validated_data):
        # Handle full_name update
        full_name = validated_data.pop('full_name', None)
        if full_name:
            # Split the full name into first and last name
            name_parts = full_name.split(' ', 1)
            instance.user.first_name = name_parts[0]
            instance.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            instance.user.save()
        
        updated_instance = super().update(instance, validated_data)
        self._update_completion_flags(updated_instance, validated_data)
        return updated_instance

    def to_internal_value(self, data):
        """
        Ensure empty strings coming from JSON/form submissions are treated as null
        for optional file/url fields so DRF doesn't expect an uploaded file.
        """
        data_copy = data.copy() if hasattr(data, 'copy') else data
        if hasattr(data_copy, 'get'):
            if data_copy.get('profile_image') in ('', None):
                data_copy['profile_image'] = None
        return super().to_internal_value(data_copy)

    def _update_completion_flags(self, instance, validated_data):
        """
        Shared helper to update completion flags across create/update flows.
        """
        try:
            updated_fields = set()

            # Basic info
            if getattr(instance, 'full_name', None) and getattr(instance, 'title', None):
                if not instance.basic_info_completed:
                    instance.basic_info_completed = True
                    updated_fields.add('basic_info_completed')

            # Work preferences
            work_pref_keys = [
                'work_style', 'availability_type', 'is_available', 'is_remote', 'time_zone', 'location'
            ]
            if any(key in validated_data for key in work_pref_keys) and not instance.work_preferences_completed:
                instance.work_preferences_completed = True
                updated_fields.add('work_preferences_completed')

            # Skills
            if 'skills' in validated_data and getattr(instance, 'skills', None) and not instance.skills_completed:
                instance.skills_completed = True
                updated_fields.add('skills_completed')

            # Portfolio
            if (
                'portfolio_links' in validated_data or
                ('resume_url' in validated_data and instance.resume_url) or
                ('video_intro_url' in validated_data and instance.video_intro_url)
            ) and not instance.portfolio_completed:
                instance.portfolio_completed = True
                updated_fields.add('portfolio_completed')

            # Privacy: allow explicit flag or infer from visibility fields
            privacy_keys = ['profile_visibility', 'video_visibility', 'contact_visibility', 'salary_visibility']
            if any(key in validated_data for key in privacy_keys) and not instance.privacy_completed:
                instance.privacy_completed = True
                updated_fields.add('privacy_completed')
            if 'privacy_completed' in validated_data:
                desired_privacy_state = bool(validated_data.get('privacy_completed'))
                if instance.privacy_completed != desired_privacy_state:
                    instance.privacy_completed = desired_privacy_state
                    updated_fields.add('privacy_completed')

            if updated_fields:
                updated_fields.add('updated_at')
                instance.save(update_fields=list(updated_fields))

            # Sync to user if needed
            try:
                user = instance.user
                if instance.is_profile_complete and not getattr(user, 'profile_completed', False):
                    user.profile_completed = True
                    user.save(update_fields=['profile_completed', 'updated_at'])
            except Exception:
                pass

        except Exception:
            # Don't break serializer flow on sync errors
            pass

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        instance = super().create(validated_data)
        self._update_completion_flags(instance, validated_data)
        return instance

    
    def get_profile_completed(self, obj):
        try:
            return bool(getattr(obj, 'is_profile_complete', False))
        except Exception:
            return False
    
    def get_viewers_count(self, obj):
        try:
            return len(obj.viewers or [])
        except Exception:
            return 0

    def get_profile_views_display(self, obj):
        try:
            n = int(getattr(obj, 'profile_views', 0) or 0)
        except Exception:
            n = 0
        if n >= 1000000:
            v = n / 1000000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}m"
        if n >= 1000:
            v = n / 1000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}k"
        return str(n)


class CandidateListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    full_name = serializers.ReadOnlyField()
    profile_completed = serializers.SerializerMethodField()
    profile_views_display = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = '__all__'

    def get_profile_completed(self, obj):
        try:
            return bool(getattr(obj, 'is_profile_complete', False))
        except Exception:
            return False

    def get_profile_views_display(self, obj):
        try:
            n = int(getattr(obj, 'profile_views', 0) or 0)
        except Exception:
            n = 0
        if n >= 1000000:
            v = n / 1000000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}m"
        if n >= 1000:
            v = n / 1000.0
            s = ("{:.1f}".format(v)).rstrip('0').rstrip('.')
            return f"{s}k"
        return str(n)


class WorkDNAQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for Work DNA Questions
    """
    class Meta:
        model = WorkDNAQuestion
        fields = '__all__'
        read_only_fields = ('candidate', 'created_at', 'updated_at')
    
    def create(self, validated_data):
        validated_data['candidate'] = self.context['request'].user.candidate_profile
        return super().create(validated_data)
        
    def update(self, instance, validated_data):
        # Handle answers update if provided
        answers = validated_data.pop('answers', None)
        if answers is not None:
            instance.answers = answers
            instance.save()
        return super().update(instance, validated_data)
    
class ReferenceRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for reference requests.
    Prevents duplicate requests and ensures emails are sent exactly once.
    """
    token = serializers.UUIDField(read_only=True)
    user_id = serializers.SerializerMethodField()

    class Meta:
        model = ReferenceRequest
        fields = [
            'id', 'token', 'reference_email', 'reference_name',
            'suggested_relationship', 'suggested_company', 'request_message',
            'reply_message', 'status', 'expires_at', 'created_at',
            'updated_at', 'candidate', 'user_id',
        ]
        read_only_fields = (
            'candidate', 'created_at', 'updated_at', 'token', 'user_id',
        )

    def get_user_id(self, obj):
        """Return the user ID associated with the candidate."""
        if obj.candidate and hasattr(obj.candidate, 'user'):
            return obj.candidate.user.id
        return None

    def validate(self, attrs):
        """
        Prevent duplicate reference requests.
        If there's already a request for the same candidate + email with status:
        - pending
        - accepted
        - declined
        Reject the new request. This ensures only one active/recent cycle per email.
        """
        request = self.context.get('request')
        if request and hasattr(request, 'user') and hasattr(request.user, 'candidate_profile'):
            candidate = request.user.candidate_profile
            email = attrs.get('reference_email')

            existing = ReferenceRequest.objects.filter(
                candidate=candidate,
                reference_email=email,
                status__in=['pending', 'accepted', 'declined'],
            ).exists()

            if existing:
                raise serializers.ValidationError(
                    "An active or recent reference request already exists for this email. "
                    "You cannot send another one while it is pending, accepted, or declined."
                )

        return attrs

    def create(self, validated_data):
        """
        Create a ReferenceRequest and send the notification email exactly once.
        Uses select_for_update() as a safety net against race conditions.
        """
        import logging
        from django.db import transaction

        logger = logging.getLogger(__name__)
        request = self.context.get('request')

        # Attach candidate profile
        if request and hasattr(request, 'user') and hasattr(request.user, 'candidate_profile'):
            validated_data['candidate'] = request.user.candidate_profile

        # Create the record (status defaults to 'pending')
        ref_request = super().create(validated_data)

        # Idempotent email dispatch with row-level lock
        try:
            with transaction.atomic():
                locked_ref = (
                    ReferenceRequest.objects
                    .select_for_update()
                    .get(pk=ref_request.pk)
                )

                if locked_ref.email_sent_at is not None:
                    logger.info(
                        f"Skipping duplicate email for ReferenceRequest "
                        f"#{locked_ref.pk} — already sent at {locked_ref.email_sent_at}"
                    )
                else:
                    from .views_reference import send_reference_request_email
                    email_sent = send_reference_request_email(locked_ref, request)

                    if email_sent:
                        locked_ref.mark_email_sent()
                        logger.info(
                            f"Reference email sent for ReferenceRequest #{locked_ref.pk}"
                        )
                    else:
                        logger.warning(
                            f"Email sending failed for ReferenceRequest #{locked_ref.pk}"
                        )
        except Exception:
            logger.exception(
                f"Error in email dispatch for ReferenceRequest #{ref_request.pk}"
            )

        ref_request.refresh_from_db()
        return ref_request

class CandidateActionDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for candidate actions detail view
    """
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = Candidate
        fields = [
            'id', 'user_id', 'full_name', 'title', 'skills', 'location',
            'work_style', 'availability_type', 'is_available', 'profile_image'
        ]
        read_only_fields = fields


class CandidateProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating candidate profile sections
    """
    profile_image = serializers.ImageField(required=False, use_url=True)
    class Meta:
        model = Candidate
        # include privacy_completed so frontend can explicitly mark the privacy section complete
        fields = ('full_name', 'title', 'bio', 'location', 'time_zone', 'is_remote', 
                 'work_style', 'is_available', 'availability_type', 'skills', 'superpowers', 
                 'preferred_roles', 'passion_projects', 'min_salary', 'max_salary', 
                 'salary_currency', 'portfolio_links', 'profile_image', 'resume_url', 
                 'video_intro_url', 'intro_video_description', 'profile_visibility', 
                 'video_transcription', 'seniority_level',
                 'video_visibility', 'contact_visibility', 'salary_visibility', 'privacy_completed')
    
    def to_internal_value(self, data):
    
        data_copy = data.copy() if hasattr(data, 'copy') else data    
        # Convert empty string to None for profile_image when no file is uploaded
        if hasattr(data_copy, 'get') and data_copy.get('profile_image') == '':
            data_copy['profile_image'] = None
            
        return super().to_internal_value(data_copy)
    
    def validate(self, attrs):
        if 'profile_image' in attrs and attrs['profile_image'] in (None, ""):
            attrs['profile_image'] = None
        return attrs
    
    def update(self, instance, validated_data):
        # Update profile completion status based on filled fields
        updated_instance = super().update(instance, validated_data)

        # Only clear profile_image if it's explicitly set to None or empty string in the request
        if 'profile_image' in self.initial_data and self.initial_data.get('profile_image') in (None, ''):
            if getattr(updated_instance, 'profile_image', None):
                updated_instance.profile_image = None
                updated_instance.save(update_fields=['profile_image'])

        # Basic info complete when name and title are set (and non-empty)
        if (updated_instance.full_name and updated_instance.title):
            updated_instance.basic_info_completed = True

        # Work preferences complete when any of key work pref fields are set
        work_pref_keys = [
            'work_style', 'availability_type', 'is_available', 'is_remote', 'time_zone', 'location'
        ]
        if any(key in validated_data for key in work_pref_keys):
            updated_instance.work_preferences_completed = True

        # Skills complete when skills array provided and not empty
        if 'skills' in validated_data and getattr(updated_instance, 'skills', None):
            updated_instance.skills_completed = True

        # Portfolio complete when links or resume/video provided
        if (
            'portfolio_links' in validated_data or
            ('resume_url' in validated_data and updated_instance.resume_url) or
            ('video_intro_url' in validated_data and updated_instance.video_intro_url)
        ):
            updated_instance.portfolio_completed = True

        # Privacy complete when any visibility field set
        privacy_keys = [
            'profile_visibility', 'video_visibility', 'contact_visibility', 'salary_visibility'
        ]
        if any(key in validated_data for key in privacy_keys):
            updated_instance.privacy_completed = True

        # Allow client to explicitly set privacy_completed (frontend may send this flag)
        if 'privacy_completed' in validated_data:
            updated_instance.privacy_completed = bool(validated_data.get('privacy_completed'))

        # Persist flag changes
        updated_instance.save(update_fields=[
            'basic_info_completed', 'work_preferences_completed', 'skills_completed',
            'portfolio_completed', 'privacy_completed', 'updated_at'
        ])

        # Sync to user.profile_completed if candidate profile is complete
        user = updated_instance.user
        if updated_instance.is_profile_complete and not getattr(user, 'profile_completed', False):
            user.profile_completed = True
            user.save(update_fields=['profile_completed', 'updated_at'])

        return updated_instance


class AchievementSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Achievement
        fields = '__all__'
        read_only_fields = ('candidate', 'created_at', 'updated_at')

    def to_representation(self, instance):
        """
        Keep `achievement_type` writable as-is, but return the humanized label
        in API responses (e.g. "award" -> "Award").
        """
        representation = super().to_representation(instance)
        representation['achievement_type'] = instance.get_achievement_type_display()
        return representation


class CompanyWithOpeningsSerializer(serializers.ModelSerializer):
    """
    Company serializer with nested active jobs and projects lists.
    Limits can be controlled via query params: jobs_limit, projects_limit.
    """
    jobs = serializers.SerializerMethodField()
    projects = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = (
            'id', 'company_name', 'industry', 'description', 'size', 'logo',
            'location', 'website', 'values', 'jobs', 'projects'
        )

    def _get_limits(self):
        request = self.context.get('request')
        def parse_int(v, default):
            try:
                return int(v)
            except Exception:
                return default
        jobs_limit = 5
        projects_limit = 5
        if request is not None:
            jobs_limit = parse_int(request.query_params.get('jobs_limit', 5), 5)
            projects_limit = parse_int(request.query_params.get('projects_limit', 5), 5)
        return jobs_limit, projects_limit

    def get_jobs(self, obj):
        qs = obj.jobs.all().order_by('-created_at')
        return JobListSerializer(qs, many=True).data

    def get_projects(self, obj):
        qs = obj.projects.all().order_by('-created_at')
        return ProjectListSerializer(qs, many=True).data