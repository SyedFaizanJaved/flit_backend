import io
import json
import logging
import os
import requests
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q, F, Count, Case, When
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, permissions, viewsets, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied, NotFound
from utils.pagination import CustomPagination  # YE SAHI HAI
from projects.models import Project
from projects.serializers import ProjectListSerializer
from jobs.models import Job
from jobs.serializers import JobListSerializer
from applications.models import JobApplication as Application, ProjectApplication
from companies.models import Company
from rest_framework import serializers 
from employers.models import Employer
import re
from django.db.models import Q
from rest_framework import generics
from projects.models import Project
from companies.models import Company
from .models import Candidate
from .serializers import DiscoverTalentSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction
from django.db.models import Q
from django.core.files.storage import default_storage
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
import requests
import json
import io
import logging
from .models import Candidate, ReferenceRequest, WorkDNAQuestion
from .serializers import (
    CandidateSerializer,
    CandidateListSerializer,
    ReferenceRequestSerializer,
    WorkDNAQuestionSerializer,
    DiscoverTalentSerializer,
    CompanyWithOpeningsSerializer,
)
from utils.pagination import CustomPagination
from utils.file_validators import (
    resume_upload_path, video_upload_path, image_upload_path, document_upload_path
)
from accounts.views import BaseRoleRegistrationView

logger = logging.getLogger(__name__)
exception_logger = logging.getLogger("exceptions")


class CandidateAccessMixin:
    def get_candidate(self):
        try:
            return self.request.user.candidate_profile
        except AttributeError:
            raise PermissionDenied("Authentication required.")
        except Candidate.DoesNotExist:
            raise NotFound("Candidate profile not found.")


# Public Views
class PublicJobListAPIView(generics.ListAPIView):
    queryset = Job.objects.filter(status='active')
    serializer_class = JobListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title']
    ordering_fields = ['created_at', 'salary_min', 'salary_max']
    filterset_fields = {
        'job_type': ['exact'],
        'work_style': ['exact'],
        'education_level': ['exact'],
        'is_remote': ['exact'],
    }


class PublicProjectListAPIView(generics.ListAPIView):
    queryset = Project.objects.filter(status='active')
    serializer_class = ProjectListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title']
    ordering_fields = ['created_at', 'budget', 'deadline']
    filterset_fields = {
        'project_type': ['exact'],
        'complexity': ['exact'],
        'work_style': ['exact'],
        'collaboration_style': ['exact'],
    }


class CandidateRegistrationView(BaseRoleRegistrationView):
    fixed_user_type = "candidate"


# Dashboard Views
class DashboardBaseView(CandidateAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]


class CandidateDashboardView(DashboardBaseView):
    def get(self, request):
        candidate = self.get_candidate()
        return Response({
            'profile': CandidateSerializer(candidate, context={'request': request}).data,
            'applications': self._get_applications_data(candidate),
            'latest_jobs': self._get_latest_jobs(candidate),
            'latest_projects': self._get_latest_projects(candidate),
        })

    def _get_applications_data(self, candidate):
        counts = Application.objects.filter(
            candidate=candidate,
            status__in=['pending', 'in_review', 'shortlisted', 'interview', 'offer']
        ).aggregate(
            total=Count('id'),
            job_apps=Count('id', filter=Q(job__isnull=False)),
            project_apps=Count('id', filter=Q(project__isnull=False))
        )
        return {
            'total_applications': counts['total'] or 0,
            'job_applications_count': counts['job_apps'] or 0,
            'project_applications_count': counts['project_apps'] or 0,
            'references_count': ReferenceRequest.objects.filter(candidate=candidate, is_public=True).count(),
        }

    def _get_latest_jobs(self, candidate, limit=5):
        jobs = Job.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]
        return JobListSerializer(jobs, many=True, context={'request': self.request}).data

    def _get_latest_projects(self, candidate, limit=5):
        projects = Project.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]
        return ProjectListSerializer(projects, many=True, context={'request': self.request}).data


class CandidateProfileDashboardView(DashboardBaseView):
    def get(self, request):
        candidate = self.get_candidate()
        applications_count = Application.objects.filter(
            candidate=candidate,
            status__in=['pending', 'in_review', 'shortlisted', 'interview', 'offer']
        ).count()
        job_count = Application.objects.filter(candidate=candidate, job__isnull=False).count()
        project_count = applications_count - job_count
        references_count = ReferenceRequest.objects.filter(candidate=candidate, is_public=True).count()
        reference_requests_count = ReferenceRequest.objects.filter(candidate=candidate).count()

        return Response({
            'profile': CandidateSerializer(candidate, context={'request': request}).data,
            'profile_completed': candidate.is_profile_complete,
            'applications_count': applications_count,
            'job_applications_count': job_count,
            'project_applications_count': project_count,
            'references_count': references_count,
            'reference_requests_count': reference_requests_count,
        })


class CandidateApplicationsView(DashboardBaseView, generics.ListAPIView):
    pagination_class = CustomPagination

    def get_queryset(self):
        candidate = self.get_candidate()
        job_apps = Application.objects.filter(candidate=candidate).select_related('job__company').order_by('-applied_at')
        project_apps = ProjectApplication.objects.filter(candidate=candidate).select_related('project__company').order_by('-applied_at')

        formatted = []
        for app in job_apps:
            formatted.append(self._format_app(app, 'job'))
        for app in project_apps:
            formatted.append(self._format_app(app, 'project'))
        formatted.sort(key=lambda x: x['applied_at'], reverse=True)
        return formatted

    def _format_app(self, app, app_type):
        if app_type == 'job':
            return {
                'app_id': app.id,
                'id': app.job.id if app.job else None,
                'title': app.job.title if app.job else 'Unknown',
                'company': app.job.company.name if app.job and app.job.company else 'Unknown',
                'status': app.status,
                'applied_at': app.applied_at,
                'type': 'job'
            }
        return {
            'app_id': app.id,
            'id': app.project.id if app.project else None,
            'title': app.project.title if app.project else 'Unknown',
            'company': app.project.company.name if app.project and app.project.company else 'Unknown',
            'status': app.status,
            'applied_at': app.applied_at,
            'type': 'project'
        }

    def list(self, request, *args, **kwargs):
        candidate = self.get_candidate()
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        counts = {
            'job': Application.objects.filter(candidate=candidate).count(),
            'project': ProjectApplication.objects.filter(candidate=candidate).count(),
        }

        data = {
            'total_applications': counts['job'] + counts['project'],
            'job_applications_count': counts['job'],
            'project_applications_count': counts['project'],
        }

        if page is not None:
            data['applications'] = page
            return self.get_paginated_response(data)

        data['applications'] = queryset
        return Response(data)


# Latest Jobs & Projects
class CandidateLatestJobsView(CandidateAccessMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination
    serializer_class = JobListSerializer

    def get_queryset(self):
        from django.core.cache import cache
        candidate = self.get_candidate()
        cache_key = f'candidate_{candidate.id}_latest_jobs'
        cached = cache.get(cache_key)

        if cached and cached.get('ml_success'):
            return cached.get('jobs', [])

        try:
            ml_url = f"{settings.FLIT_AI_URL.rstrip('/')}/show_jobs_for_candidate/{candidate.id}"
            response = requests.get(ml_url, timeout=15)
            if response.status_code == 200:
                ranked = response.json().get('ranked_opportunities', [])
                jobs = []
                for item in ranked:
                    job_id = item.get('job_id') or item.get('id')
                    if not job_id:
                        continue
                    company = item.get('company', {})
                    jobs.append({
                        'id': job_id,
                        'title': item.get('title', 'No Title'),
                        'description': item.get('description', ''),
                        'workStyle': item.get('work_style', 'remote'),
                        'category': item.get('category', 'other'),
                        'experienceLevel': item.get('experience_level', 'mid'),
                        'employmentType': item.get('employment_type', 'full-time'),
                        'salaryRangeMin': item.get('salary_range', {}).get('min'),
                        'salaryRangeMax': item.get('salary_range', {}).get('max'),
                        'status': item.get('status', 'active'),
                        'created_at': item.get('created_at', timezone.now().isoformat()),
                        'location': item.get('location'),
                        'skills': item.get('skills', []),
                        'company_name': company.get('company_name', 'Unknown'),
                        'company_id': company.get('id'),
                    })
                if jobs:
                    cache.set(cache_key, {'jobs': jobs, 'ml_success': True}, timeout=300)
                return jobs
        except Exception as e:
            logger.warning(f"ML jobs fetch failed: {e}")
        return []

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        data = {'ml_success': bool(queryset), 'latest_jobs': page if page is not None else queryset}
        if page is not None:
            return self.get_paginated_response(data)
        return Response({**data, 'count': len(queryset), 'next': None, 'previous': None})


class CandidateLatestProjectsView(CandidateAccessMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination
    # serializer_class = ProjectListSerializer  # ← YEH COMMENT OUT KAR DO

    def get_queryset(self):
        from django.core.cache import cache
        candidate = self.get_candidate()
        cache_key = f'candidate_{candidate.id}_latest_projects'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            ml_url = f"{settings.FLIT_AI_URL.rstrip('/')}/show_projects_for_candidate/{candidate.id}"
            response = requests.get(ml_url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                projects = data.get('ranked_projects') or data.get('opportunities') or []
                
                formatted = []
                for item in projects:
                    pid = item.get('id') or item.get('project_id')
                    if not pid:
                        continue
                        
                    # Try to get project from database to fetch company info
                    project = None
                    try:
                        project = Project.objects.filter(id=pid).select_related('company').first()
                    except (Project.DoesNotExist, ValueError):
                        pass
                    
                    # Prepare company info
                    company_name = 'Unknown'
                    company_id = None
                    
                    if project and project.company:
                        company_name = project.company.company_name
                        company_id = project.company.id
                    elif isinstance(item.get('company'), dict):
                        company_name = item['company'].get('company_name', 'Unknown')
                        company_id = item['company'].get('id')
                    
                    formatted.append({
                        'id': pid,
                        'title': item.get('title', 'No Title'),
                        'description': item.get('description', ''),
                        'category': item.get('category', 'other'),
                        'status': 'active',
                        'created_at': item.get('created_at', timezone.now().isoformat()),
                        'skills': item.get('skills', []),
                        'estimatedHours': item.get('estimated_hours', '1-2 weeks'),
                        'paymentType': item.get('payment_type', 'fixed'),
                        'paymentAmount': item.get('payment_amount', 0),
                        'work_style': item.get('work_style', 'remote'),
                        'company_name': company_name,
                        'company_id': company_id,
                    })
                cache.set(cache_key, formatted, timeout=300)
                return formatted
        except Exception as e:
            logger.warning(f"ML projects fetch failed: {e}")
        return []

    # Serializer dynamically set karo kyun ke hum dict return kar rahe hain
    def get_serializer_class(self):
        # Ek simple dict serializer return karo jo sirf data pass through kare
        class DictSerializer(serializers.Serializer):
            id = serializers.IntegerField()
            title = serializers.CharField()
            description = serializers.CharField()
            category = serializers.CharField()
            status = serializers.CharField()
            created_at = serializers.CharField()
            skills = serializers.ListField(child=serializers.CharField())
            estimatedHours = serializers.CharField()  # ← Yeh add kiya
            paymentType = serializers.CharField()
            paymentAmount = serializers.IntegerField()
            work_style = serializers.CharField()
            company_name = serializers.CharField()
            company_id = serializers.IntegerField(allow_null=True)

        return DictSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(queryset if page is None else page, many=True)
        data = {
            'ml_success': bool(queryset),
            'latest_projects': serializer.data
        }
        if page is not None:
            return self.get_paginated_response(data)
        return Response({**data, 'count': len(queryset), 'next': None, 'previous': None})


logger = logging.getLogger(__name__)
exception_logger = logging.getLogger('exception')

class CandidateViewSet(CandidateAccessMixin, viewsets.ModelViewSet):
    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    pagination_class = PageNumberPagination

    def get_object(self):
        if self.request.parser_context.get('kwargs', {}).get('pk') == 'profile':
            return self.get_candidate()
        return super().get_object()

    def _save_file(self, file_obj, upload_path_func):
        try:
            path = upload_path_func(None, file_obj.name)
            default_storage.save(path, file_obj)
            return path
        except Exception as e:
            exception_logger.exception(f"File save failed: {e}")
            return None

    # ====================== RETRIEVE (Only for viewing others' profiles) ======================
    def retrieve(self, request, pk=None):
        try:
            if not pk:
                return Response({"error": "Candidate ID is required"}, status=400)

            # Try by primary key first
            candidate = Candidate.objects.filter(
                Q(pk=pk) &
                (Q(profile_visibility="public") | Q(user=request.user))
            ).select_related('user').first()

            # If not found, try by user__id
            if not candidate:
                candidate = Candidate.objects.filter(
                    Q(user__id=pk) &
                    (Q(profile_visibility="public") | Q(user=request.user))
                ).select_related('user').first()

            if not candidate:
                return Response({
                    "error": "Candidate not found or you don't have permission to view this profile"
                }, status=404)

            # Track profile view by employer
            try:
                if (hasattr(request.user, 'employer_profile') and
                    (not hasattr(request.user, 'candidate_profile') or candidate.user_id != request.user.id)):
                    with transaction.atomic():
                        candidate.refresh_from_db()
                        viewer_ids = list(candidate.viewers or [])
                        if request.user.employer_profile.id not in viewer_ids:
                            viewer_ids.append(request.user.employer_profile.id)
                            candidate.viewers = viewer_ids
                            candidate.profile_views = (candidate.profile_views or 0) + 1
                            candidate.save(update_fields=['profile_views', 'viewers', 'updated_at'])
            except Exception as view_error:
                exception_logger.error(f"Error updating profile views: {str(view_error)}", exc_info=True)

            serializer = CandidateSerializer(candidate, context={'request': request})
            return Response(serializer.data)

        except Exception as e:
            exception_logger.error(f"Unexpected error in candidate retrieve: {str(e)}", exc_info=True)
            return Response({"error": "An unexpected error occurred"}, status=500)

    # ====================== PROFILE ENDPOINT (Own profile: GET + PATCH + PUT) ======================
    @action(detail=False, methods=['get', 'patch', 'put'])
    def profile(self, request):
        candidate = self.get_candidate()  # Assumes you have this method in CandidateAccessMixin

        if request.method == 'GET':
            serializer = self.get_serializer(candidate)
            return Response(serializer.data)

        # ====================== PATCH / PUT ======================
        data = request.data
        files = request.FILES
        updated_fields = []

        # --------------------- Helper Functions ---------------------
        def to_boolean(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                cleaned = value.strip().lower().replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
                if cleaned in ('true', '1', 'yes', 'on', 't', '"true"', "'true'"):
                    return True
                if cleaned in ('false', '0', 'no', 'off', 'f', '"false"', "'false'"):
                    return False
            logger.warning(f"Invalid boolean value received: {value}")
            return None

        def parse_json_list(value):
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                    return [parsed]
                except json.JSONDecodeError:
                    logger.warning(f"JSON parse failed for list field: {value}")
                    cleaned = value.strip()
                    if cleaned.startswith('[') and cleaned.endswith(']'):
                        cleaned = cleaned[1:-1]
                    items = [item.strip().strip('"').strip("'") for item in cleaned.split(',') if item.strip()]
                    return items if items else []
            return []

        def get_file_url(field):
            if field and hasattr(field, 'url'):
                try:
                    return request.build_absolute_uri(field.url)
                except:
                    return field.url if field.url else ""
            return ""

        def delete_old_file(old_field):
            if old_field and hasattr(old_field, 'name') and old_field.name:
                try:
                    if default_storage.exists(old_field.name):
                        default_storage.delete(old_field.name)
                        logger.info(f"Deleted old file from S3: {old_field.name}")
                except Exception as e:
                    logger.error(f"Failed to delete old file {old_field.name}: {e}")

        list_fields = ['skills', 'superpowers', 'preferred_roles', 'portfolio_links']
        boolean_fields = ['is_available']

        # ====================== FILE UPLOADS ======================
        # Handle video deletion if remove_old_video is true
        if data.get('remove_old_video') == 'true':
            if candidate.video_intro_url:
                delete_old_file(candidate.video_intro_url)
                candidate.video_intro_url = None
                candidate.video_transcription = None
                candidate.intro_video_description = None
                updated_fields.extend(['video_intro_url', 'video_transcription', 'intro_video_description'])
                logger.info("Video deleted from profile")

        if 'profile_image' in files:
            if candidate.profile_image:
                delete_old_file(candidate.profile_image)
            candidate.profile_image = files['profile_image']
            updated_fields.append('profile_image')
            logger.info("New profile image uploaded (old deleted)")

        if 'resume_file' in files or 'resume' in files:
            resume_file = files.get('resume_file') or files.get('resume')
            if candidate.resume_url:
                delete_old_file(candidate.resume_url)

            path = self._save_file(resume_file, resume_upload_path)
            if path:
                candidate.resume_url = path
                candidate.portfolio_completed = True
                updated_fields.extend(['resume_url', 'portfolio_completed'])
                logger.info(f"New resume uploaded: {path}")

                try:
                    resume_file.seek(0)
                    files_ml = {'resume_file': (resume_file.name, io.BytesIO(resume_file.read()), resume_file.content_type)}
                    parse_url = f"{settings.FLIT_AI_URL}/parse_cv"
                    resp = requests.post(parse_url, files=files_ml)
                    logger.info(f"ML parse_cv response: {resp.status_code}")

                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get('success'):
                            candidate.resume_data = result.get('data', {})
                            updated_fields.append('resume_data')
                            logger.info("Resume parsed successfully")
                        else:
                            logger.warning(f"ML parse_cv failed: {result.get('message')}")
                    else:
                        logger.error(f"ML parse_cv failed: {resp.status_code}")
                except Exception as e:
                    logger.error(f"Resume parsing exception: {e}", exc_info=True)

        if 'video_file' in files:
            video_file = files['video_file']
            if candidate.video_intro_url:
                delete_old_file(candidate.video_intro_url)

            path = self._save_file(video_file, video_upload_path)
            if path:
                candidate.video_intro_url = path
                candidate.portfolio_completed = True
                updated_fields.extend(['video_intro_url', 'portfolio_completed'])
                logger.info(f"New video uploaded: {path}")

                try:
                    video_file.seek(0)
                    analyze_url = f"{settings.FLIT_AI_URL}/analyze_intro_video"
                    files_video = {'video_file': (video_file.name, io.BytesIO(video_file.read()), video_file.content_type)}
                    video_payload = {
                        'user_id': str(request.user.id),
                        'candidate_id': str(candidate.id),
                        'video_url': request.build_absolute_uri(path)
                    }
                    headers = {}
                    if hasattr(settings, 'ML_API_KEY'):
                        headers["Authorization"] = f"Bearer {settings.ML_API_KEY}"

                    resp = requests.post(analyze_url, files=files_video, data=video_payload, headers=headers)
                    logger.info(f"ML video analysis response: {resp.status_code}")

                    if resp.status_code == 200:
                        analysis = resp.json().get('analysis', {})
                        if transcription := analysis.get('video_transcript'):
                            candidate.video_transcription = transcription
                            updated_fields.append('video_transcription')
                        if description := analysis.get('description'):
                            candidate.intro_video_description = description
                            updated_fields.append('intro_video_description')
                        logger.info("Video analysis completed")
                    else:
                        logger.error(f"ML video analysis failed: {resp.status_code}")
                except Exception as e:
                    logger.error(f"Video analysis exception: {e}", exc_info=True)

        # ====================== TEXT & LIST FIELDS ======================
        text_fields = [
            'full_name', 'title', 'bio', 'location', 'work_style', 'availability_type', 'is_available',
            'skills', 'superpowers', 'preferred_roles', 'portfolio_links', 'profile_visibility',
            'min_salary', 'max_salary', 'seniority_level', 'passion_projects'
        ]

        for field in text_fields:
            if field in data:
                value = data[field]
                if field in list_fields:
                    cleaned = parse_json_list(value)
                    setattr(candidate, field, cleaned)
                    updated_fields.append(field)
                elif field in boolean_fields:
                    converted = to_boolean(value)
                    if converted is not None:
                        setattr(candidate, field, converted)
                        updated_fields.append(field)
                else:
                    if field in ['min_salary', 'max_salary']:
                        try:
                            value = float(value) if value and '.' in str(value) else int(value) if value else None
                        except:
                            value = None
                    setattr(candidate, field, value)
                    updated_fields.append(field)

        # ====================== COMPLETION FLAGS ======================
        if any(k in data for k in ['full_name', 'title', 'bio', 'location']):
            candidate.basic_info_completed = True
            updated_fields.append('basic_info_completed')
        if any(k in data for k in ['work_style', 'availability_type', 'is_available']):
            candidate.work_preferences_completed = True
            updated_fields.append('work_preferences_completed')
        if any(k in data for k in ['skills', 'superpowers', 'preferred_roles']):
            candidate.skills_completed = True
            updated_fields.append('skills_completed')
        if files or 'portfolio_links' in data:
            candidate.portfolio_completed = True
            updated_fields.append('portfolio_completed')
        if any(k in data for k in ['profile_visibility', 'video_visibility', 'contact_visibility', 'salary_visibility']):
            candidate.privacy_completed = True
            updated_fields.append('privacy_completed')

        candidate.save(update_fields=list(set(updated_fields + ['updated_at'])))
        logger.info(f"Database save completed for candidate {candidate.id}")

        # ====================== ML SYNC ======================
        ml_success = True
        ml_message = "All ML APIs successfully executed"

        try:
            ml_payload = {
                "full_name": candidate.full_name or "",
                "title": candidate.title or "",
                "bio": candidate.bio or "",
                "location": candidate.location or "",
                "work_style": candidate.work_style or "",
                "skills": candidate.skills or [],
                "superpowers": candidate.superpowers or [],
                "preferred_roles": candidate.preferred_roles or [],
                "is_available": candidate.is_available or False,
                "min_salary": candidate.min_salary if candidate.min_salary is not None else None,
                "max_salary": candidate.max_salary if candidate.max_salary is not None else None,
                "seniority_level": candidate.seniority_level or "",
                "passion_projects": candidate.passion_projects or "",
                "resume_url": get_file_url(candidate.resume_url),
                "video_intro_url": get_file_url(candidate.video_intro_url),
                "resume_data": candidate.resume_data or {},
                "user_id": str(candidate.user.id),
                "email": candidate.user.email or "",
            }

            headers = {"Content-Type": "application/json"}
            if hasattr(settings, 'ML_API_KEY'):
                headers["Authorization"] = f"Bearer {settings.ML_API_KEY}"

            update_url = f"{settings.FLIT_AI_URL}/update_candidate_data/{candidate.id}"
            create_url = f"{settings.FLIT_AI_URL}/create_candidates/{candidate.id}"

            resp = requests.patch(update_url, json=ml_payload, headers=headers)

            if resp.status_code == 404:
                logger.info("Candidate not in ML, creating new")
                resp = requests.post(create_url, json=ml_payload, headers=headers)

            if resp.status_code not in (200, 201):
                ml_success = False
                ml_message = f"ML sync failed: HTTP {resp.status_code}"
                logger.error(f"ML sync failed: {resp.status_code} - {resp.text[:500]}")
            else:
                logger.info(f"ML sync successful ({resp.status_code})")
                ml_data = resp.json()
                extra_saved = False
                if ml_data.get('candidate_profile_summary'):
                    candidate.candidate_profile_summary = ml_data['candidate_profile_summary']
                    extra_saved = True
                if ml_data.get('candidate_tags'):
                    candidate.candidate_tags = ml_data['candidate_tags']
                    extra_saved = True
                if extra_saved:
                    candidate.save(update_fields=['candidate_profile_summary', 'candidate_tags', 'updated_at'])

        except Exception as e:
            ml_success = False
            ml_message = "ML sync failed due to exception"
            logger.error(f"ML sync exception: {e}", exc_info=True)

        # ====================== FINAL RESPONSE ======================
        response_data = CandidateSerializer(candidate, context={'request': request}).data
        response_data['ml_success'] = ml_success
        response_data['ml_message'] = ml_message

        return Response(response_data)


        
# Work DNA
class WorkDNAQuestionView(CandidateAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, candidate_id=None):
        if candidate_id:
            return self.evaluate_answers(candidate_id)

        candidate = self.get_candidate()
        work_dna = WorkDNAQuestion.objects.filter(candidate=candidate).first()

        if work_dna:
            return Response(WorkDNAQuestionSerializer(work_dna).data)

        try:
            resp = requests.get(f"{settings.FLIT_AI_URL}/generate_work_dna_questions/{candidate.id}", timeout=30)
            if resp.status_code == 200:
                questions = resp.json().get('questions', [])
                work_dna = WorkDNAQuestion.objects.create(
                    candidate=candidate,
                    candidate_name=candidate.full_name,
                    questions=questions,
                    total_questions=len(questions)
                )
                return Response(WorkDNAQuestionSerializer(work_dna).data)
        except Exception as e:
            logger.error(f"Work DNA fetch failed: {e}")

        return Response({'error': 'Failed to fetch questions'}, status=503)

    def post(self, request):
        candidate = self.get_candidate()
        answers = request.data.get('answers', {})
        work_dna = WorkDNAQuestion.objects.filter(candidate=candidate).first()
        if not work_dna:
            return Response({'error': 'No questions found'}, status=404)

        current = work_dna.answers or {}
        for q_id, answer in answers.items():
            if str(q_id).isdigit() and int(q_id) <= len(work_dna.questions):
                q_text = work_dna.questions[int(q_id)-1].get('question', f'Question {q_id}')
                current[q_text] = answer

        work_dna.answers = current
        work_dna.save()
        return Response(WorkDNAQuestionSerializer(work_dna).data)

    def evaluate_answers(self, candidate_id):
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            work_dna = WorkDNAQuestion.objects.get(candidate=candidate)
            if not work_dna.answers:
                return Response({'error': 'No answers'}, status=400)

            resp = requests.get(f"{settings.FLIT_AI_URL}/evaluate_work_dna_questions/{candidate.id}", timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                work_dna.evaluation_result = result
                work_dna.save()
                return Response(result)
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
        return Response({'error': 'Evaluation failed'}, status=503)


# Other Views
class CandidateAIMatchingView(APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request, candidate_id):
        total = request.query_params.get('total')
        params = {'total': total} if total else {}
        try:
            resp = requests.get(f"{settings.FLIT_AI_URL}/ai_matching/{candidate_id}", params=params)
            resp.raise_for_status()
            return Response(resp.json())
        except requests.RequestException as e:
            return Response({'error': 'AI service unavailable'}, status=503)


class DiscoverTalentView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    serializer_class = DiscoverTalentSerializer

    def get_queryset(self):
        qs = Candidate.objects.select_related('user').filter(
            user__is_active=True,
            profile_visibility="public"
        )

        q = self.request.query_params.get('search', '').strip().lower()
        search_type = self.request.query_params.get('search_type', 'both').lower()  # 'name', 'title', or 'both'

        if q:
            words = [word.strip() for word in q.split() if word.strip()]
            if not words:
                return qs

            from django.db.models import Q, Case, When, Value, IntegerField, F
            
            # Initialize queries
            name_query = Q()
            title_query = Q()
            
            # Build name query if searching by name or both
            if search_type in ['name', 'both']:
                if len(words) >= 2:
                    # For two or more words, try different combinations of first and last name
                    name_query = (
                        Q(user__first_name__iexact=words[0], user__last_name__iexact=' '.join(words[1:])) |
                        Q(user__first_name__iexact=' '.join(words[1:]), user__last_name__iexact=words[0]) |
                        Q(user__first_name__iexact=words[-1], user__last_name__iexact=' '.join(words[:-1])) |
                        Q(user__first_name__iexact=' '.join(words[:-1]), user__last_name__iexact=words[-1])
                    )
                else:
                    # For single word, search in first or last name
                    name_query = (
                        Q(user__first_name__iexact=words[0]) |
                        Q(user__last_name__iexact=words[0])
                    )
            
            # Build title query if searching by title or both
            if search_type in ['title', 'both']:
                if len(words) >= 2:
                    # For multi-word queries, try exact match first
                    title_query = Q(title__iexact=q)
                    
                    # If no exact matches, try partial matches from start
                    if not qs.filter(title_query).exists() and search_type == 'title':
                        title_query = Q(title__istartswith=q)
                else:
                    # For single word, search from start of title
                    title_query = Q(title__istartswith=words[0])
            
            # Combine queries based on search type
            if search_type == 'name':
                qs = qs.filter(name_query)
            elif search_type == 'title':
                qs = qs.filter(title_query)
            else:  # both
                qs = qs.filter(name_query | title_query)
            
            # If no results and searching both, try partial matches
            if not qs.exists() and search_type in ['both', 'name']:
                partial_name_query = Q()
                for word in words:
                    partial_name_query |= (
                        Q(user__first_name__icontains=word) |
                        Q(user__last_name__icontains=word)
                    )
                qs = qs.filter(partial_name_query)
            
            # Create a base score of 0
            qs = qs.annotate(relevance=Value(0, output_field=IntegerField()))
            
            # Exact title match (highest priority)
            exact_title_query = Q(title__iexact=q)
            qs = qs.annotate(
                title_exact_match=Case(
                    When(exact_title_query, then=Value(1000)),  # Very high score for exact title match
                    default=Value(0),
                    output_field=IntegerField()
                )
            )
            
            # Full name exact match (high priority)
            full_name = ' '.join(words).strip()
            qs = qs.annotate(
                full_name_match=Case(
                    When(
                        Q(user__first_name__iexact=full_name) | 
                        Q(user__last_name__iexact=full_name) |
                        Q(user__first_name__iexact=words[0]) & Q(user__last_name__iexact=' '.join(words[1:]).strip() if len(words) > 1 else ''),
                        then=Value(800)  # High score for exact full name match
                    ),
                    default=Value(0),
                    output_field=IntegerField()
                )
            )
            
            # Title contains all search words (medium-high priority)
            title_contains_all = Q()
            for word in words:
                title_contains_all &= Q(title__icontains=word)
            
            qs = qs.annotate(
                title_contains_all=Case(
                    When(title_contains_all, then=Value(500)),
                    default=Value(0),
                    output_field=IntegerField()
                )
            )
            
            # Add individual word matches with different weights
            for i, word in enumerate(words):
                # Higher weight for first word matches
                weight = 3 if i == 0 else 2
                
                # Title matches
                qs = qs.annotate(**{
                    f'title_exact_{i}': Case(
                        When(title__iexact=word, then=Value(weight * 4)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    f'title_start_{i}': Case(
                        When(title__istartswith=word, then=Value(weight * 3)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    f'title_contains_{i}': Case(
                        When(title__icontains=word, then=Value(weight * 2)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    # Name matches
                    f'first_name_exact_{i}': Case(
                        When(user__first_name__iexact=word, then=Value(weight * 3)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    f'first_name_start_{i}': Case(
                        When(user__first_name__istartswith=word, then=Value(weight * 2)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    f'first_name_contains_{i}': Case(
                        When(user__first_name__icontains=word, then=Value(weight)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    f'last_name_exact_{i}': Case(
                        When(user__last_name__iexact=word, then=Value(weight * 3)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    f'last_name_start_{i}': Case(
                        When(user__last_name__istartswith=word, then=Value(weight * 2)),
                        default=Value(0),
                        output_field=IntegerField()
                    ),
                    f'last_name_contains_{i}': Case(
                        When(user__last_name__icontains=word, then=Value(weight)),
                        default=Value(0),
                        output_field=IntegerField()
                    )
                })
            
            relevance_fields = [
                'title_exact_match',
                'full_name_match',
                'title_contains_all',
                *[f'title_exact_{i}' for i in range(len(words))],
                *[f'title_start_{i}' for i in range(len(words))],
                *[f'title_contains_{i}' for i in range(len(words))],
                *[f'first_name_exact_{i}' for i in range(len(words))],
                *[f'first_name_start_{i}' for i in range(len(words))],
                *[f'first_name_contains_{i}' for i in range(len(words))],
                *[f'last_name_exact_{i}' for i in range(len(words))],
                *[f'last_name_start_{i}' for i in range(len(words))],
                *[f'last_name_contains_{i}' for i in range(len(words))],
            ]
            
            # Calculate total relevance score by summing all relevance fields
            from django.db.models import Sum, F, Case, When, Value, IntegerField
            
            # Start with a base score of 0
            score_expression = Value(0, output_field=IntegerField())
            
            # Add up all relevance fields
            for field in relevance_fields:
                score_expression = score_expression + F(field)
            
            # Add a small boost for profile views (1 point per 1000 views)
            qs = qs.annotate(
                total_score=score_expression + (F('profile_views') / 1000)
            ).order_by('-total_score')

        # Skills filter (if any)
        if skills := self.request.query_params.getlist('skills'):
            qs = qs.filter(skills__overlap=skills)

        return qs.distinct()

class ReferenceRequestListView(CandidateAccessMixin, generics.ListCreateAPIView):
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate=self.get_candidate()).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(candidate=self.get_candidate())


class ReferenceRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReferenceRequestSerializer

    def get_queryset(self):
        if self.request.method == 'GET':
            return ReferenceRequest.objects.all()
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)

    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method == 'GET' else [permissions.IsAuthenticated()]