import logging
import requests
import time
import re
from rest_framework import permissions
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, permissions, mixins
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import action, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from accounts.permissions import IsEmployer
from utils.pagination import CustomPagination
from utils.email_service import send_shortlist_notification, send_rejection_notification
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Job, JobSkill, JobLanguage
from .serializers import (
    JobSerializer, JobListSerializer, JobCreateSerializer, JobUpdateSerializer,
    JobSkillSerializer, JobLanguageSerializer
)

logger = logging.getLogger(__name__)
exception_logger = logging.getLogger("exceptions")


class PublicAuthentication(BaseAuthentication):
    def authenticate(self, request):
        return None


class JobMLMixin:
    """
    Mixin to handle ML API integrations for Jobs
    """
    def _call_ml_create_api(self, job):
        return self._call_ml_api(f"{settings.FLIT_AI_URL}/create_jobs/{job.id}", job, is_create=True)

    def _call_ml_update_api(self, job):
        return self._call_ml_api(f"{settings.FLIT_AI_URL}/update_job_data/{job.id}", job, is_create=False)

    def _call_ml_metadata_api(self, job):
        """
        New API for updating job metadata, specifically used when status changes (e.g., auto-closed)
        """
        return self._call_ml_api(f"{settings.FLIT_AI_URL}/update_job_metadata/{job.id}", job, is_create=False)

    def _call_ml_api(self, url, job, is_create=True):
        payload = {
            "title": job.title,
            "description": job.description,
            "company_name": job.company.company_name if job.company else "",
            "employment_type": job.employmentType,
            "experience_level": job.experienceLevel,
            "work_style": job.workStyle,
            "category": job.category,
            "salary_range_min": job.salaryRangeMin,
            "salary_range_max": job.salaryRangeMax,
            "benefits": job.benefits or [],
            "application_deadline": job.applicationDeadline.isoformat() if job.applicationDeadline else None,
            "status": job.status,
            "location": job.location,
            "skills": job.skills or [],
        }

        method = requests.post if is_create else requests.patch
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                ml_response = method(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                break
            except requests.exceptions.Timeout:
                if attempt == max_retries:
                    return False, None, [], "ML API timed out after retries"
                time.sleep(1)
            except requests.exceptions.RequestException as e:
                return False, None, [], f"ML API request failed: {str(e)}"

        if ml_response.status_code in (200, 201):
            try:
                data = ml_response.json()
                summary = data.get('job_profile_summary')
                tags = data.get('job_tags', [])

                updates = {}
                if summary is not None:
                    updates['job_profile_summary'] = summary
                if tags:
                    updates['job_tags'] = tags
                if updates:
                    for field, value in updates.items():
                        setattr(job, field, value)
                    job.save(update_fields=updates.keys())

                return True, summary, tags, None
            except Exception as e:
                exception_logger.exception("Error processing ML response")
                return False, None, [], "Invalid ML response format"
        else:
            return False, None, [], f"ML API error: {ml_response.status_code}"



@permission_classes([permissions.IsAuthenticatedOrReadOnly])
class PublicJobViewSet(JobMLMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """
    Public endpoints: List and retrieve active jobs (no auth required)
    """
    authentication_classes = [JWTAuthentication]
    queryset = Job.objects.filter(status='active').select_related('company')
    serializer_class = JobListSerializer
    pagination_class = CustomPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']

    def get_queryset(self):
        # Auto-close moved to `manage.py close_expired_jobs` (Bug #23).
        # Public list filters by applicationDeadline >= today (or null),
        # so expired rows are already excluded here without mutating them.
        queryset = super().get_queryset().filter(
            models.Q(applicationDeadline__date__gte=timezone.now().date()) |
            models.Q(applicationDeadline__isnull=True)
        )
    
        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    queryset = queryset.filter(title__icontains=term)
       
        return queryset
   

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Non-paginated fallback (rare but consistent)
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'results': serializer.data
        })


class JobViewSet(JobMLMixin, viewsets.ModelViewSet):
    queryset = Job.objects.all().select_related('company')
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']

    def get_queryset(self):
        # Auto-close moved to `manage.py close_expired_jobs` (Bug #23).
        # Active-with-past-deadline updates are blocked by JobUpdateSerializer.validate().
        qs = super().get_queryset()

        # For retrieve action: candidates should be able to view any job
        # they've applied to, even if it's closed/expired.
        if self.action == 'retrieve':
            # Pure employers (no candidate profile) can only see their company's jobs
            if hasattr(self.request.user, 'employer_profile') and not hasattr(self.request.user, 'candidate_profile'):
                qs = qs.filter(company=self.request.user.employer_profile.company)
            # Candidates (including dual-role users) can retrieve any job
            return qs.distinct()

        # Restriction: Employers can only manage/see their own items,
        # but dual-role users (who are also candidates) should be able to browse all active ones.
        if hasattr(self.request.user, 'employer_profile'):
            from django.db.models import Q
            if not hasattr(self.request.user, 'candidate_profile'):
                qs = qs.filter(company=self.request.user.employer_profile.company)
            else:
                # Dual role: allow viewing any active job or their own company's jobs
                qs = qs.filter(
                    Q(company=self.request.user.employer_profile.company) | Q(status='active')
                )

        if self.action == 'list':
            qs = qs.filter(status='active')

        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    qs = qs.filter(title__icontains=term)

        return qs.distinct()

    def get_serializer_class(self):
        if self.action in ['list', 'my_jobs']:
            return JobListSerializer
        if self.action == 'create':
            return JobCreateSerializer
        if self.action in ['update', 'partial_update']:
            return JobUpdateSerializer
        return JobSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'update_status',
                            'shortlist_application', 'reject_application', 'skills', 'languages']:
            return [permissions.IsAuthenticated(), IsEmployer()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='my-jobs')
    def my_jobs(self, request):
        queryset = self.filter_queryset(self.get_queryset())

        # Get company for scoping per-tab counts
        company = None
        if hasattr(request.user, 'employer_profile'):
            company = request.user.employer_profile.company

        # Per-tab counts must be scoped to the Job model only — never mixed
        # with Project counts (Bug #22).
        total_jobs_count = 0
        active_jobs_count = 0
        if company:
            company_jobs = Job.objects.filter(company=company)
            total_jobs_count = company_jobs.count()
            active_jobs_count = company_jobs.filter(status='active').count()

        page = self.paginate_queryset(queryset)
        serializer = JobListSerializer(
            page if page is not None else queryset,
            many=True,
            context={'request': request}
        )

        if page is not None:
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                'count': paginated_response.data['count'],
                'next': paginated_response.data['next'],
                'previous': paginated_response.data['previous'],
                'total_pages': paginated_response.data['total_pages'],
                'current_page': paginated_response.data['current_page'],
                'total_jobs': total_jobs_count,
                'active_jobs': active_jobs_count,
                'results': paginated_response.data['results']
            })

        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'total_jobs': total_jobs_count,
            'active_jobs': active_jobs_count,
            'results': serializer.data
        })

    # ==================== ML Integration ====================

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code != status.HTTP_201_CREATED:
            return response

        job = Job.objects.get(id=response.data['id'])
        ml_success, job_profile_summary, job_tags, ml_error = self._call_ml_create_api(job)

        response.data = {
            'message': 'Job created successfully',
            'ml_success': ml_success,
            'job_profile_summary': job_profile_summary,
            'job_tags': job_tags,
            'data': response.data
        }
        if ml_error:
            response.data['ml_error'] = ml_error

        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code != status.HTTP_200_OK:
            return response

        job = self.get_object()
        ml_success, job_profile_summary, job_tags, ml_error = self._call_ml_update_api(job)

        updated_data = JobSerializer(job).data
        response.data = {
            'message': 'Job updated successfully',
            'ml_success': ml_success,
            'job_profile_summary': job_profile_summary,
            'job_tags': job_tags,
            'data': updated_data
        }
        if ml_error:
            response.data['ml_error'] = ml_error
            response.data['message'] += f' (ML processing failed: {ml_error})'

        return response

        if ml_response.status_code in (200, 201):
            try:
                data = ml_response.json()
                summary = data.get('job_profile_summary')
                tags = data.get('job_tags', [])

                updates = {}
                if summary is not None:
                    updates['job_profile_summary'] = summary
                if tags:
                    updates['job_tags'] = tags
                if updates:
                    for field, value in updates.items():
                        setattr(job, field, value)
                    job.save(update_fields=updates.keys())

                return True, summary, tags, None
            except Exception as e:
                exception_logger.exception("Error processing ML response")
                return False, None, [], "Invalid ML response format"
        else:
            return False, None, [], f"ML API error: {ml_response.status_code}"

    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        self.perform_destroy(job)
        return Response({'message': 'Job deleted successfully'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'post'], url_path='skills')
    def skills(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            skills = JobSkill.objects.filter(job=job)
            return Response(JobSkillSerializer(skills, many=True).data)
        serializer = JobSkillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], url_path='languages')
    def languages(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            langs = JobLanguage.objects.filter(job=job)
            return Response(JobLanguageSerializer(langs, many=True).data)
        serializer = JobLanguageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='applications')
    def applications(self, request, pk=None):
        job = get_object_or_404(Job, id=pk, employer=request.user)
        apps = job.applications.all()
        data = {
            'job': JobSerializer(job).data,
            'applications': [
                {
                    'id': app.id,
                    'candidate_name': app.candidate.full_name,
                    'status': app.status,
                    'overall_match_score': app.overall_match_score,
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected
                } for app in apps
            ],
            'total_applications': apps.count(),
            'shortlisted_count': apps.filter(is_shortlisted=True).count(),
            'rejected_count': apps.filter(is_rejected=True).count(),
        }
        return Response(data)

    @action(detail=True, methods=['post'], url_path='status')
    def update_status(self, request, pk=None):
        job = get_object_or_404(Job, id=pk, employer=request.user)
        new_status = request.data.get('status')
        valid = ['draft', 'active', 'paused', 'closed', 'filled']
        if new_status not in valid:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        job.status = new_status
        job.save()
        return Response({'message': 'Job status updated successfully', 'job': JobSerializer(job).data})

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/shortlist')
    def shortlist_application(self, request, pk=None, application_id=None):
        job = get_object_or_404(Job, id=pk, employer=request.user)
        app = get_object_or_404(job.applications, id=application_id)
        app.is_shortlisted = True
        app.is_rejected = False
        app.status = 'shortlisted'
        app.save()
        
        # Send email notification to candidate
        try:
            send_shortlist_notification(
                candidate=app.candidate,
                job_or_project_title=job.title,
                application_type='job',
                company_name=job.company.company_name if job.company else None
            )
        except Exception as e:
            logger.error(f"Failed to send shortlist email notification: {str(e)}")
            # Don't fail the request if email fails
            
        # Notify Candidate via WebSocket
        if app.candidate and app.candidate.user:
            from utils.broadcaster import broadcast_count_update
            from candidates.utils import get_candidate_unread_counts
            broadcast_count_update(
                user_id=app.candidate.user.id,
                count_type="applications",
                unread_count=get_candidate_unread_counts(app.candidate.user)
            )
        
        return Response({'message': 'Application shortlisted successfully'})

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/reject')
    def reject_application(self, request, pk=None, application_id=None):
        job = get_object_or_404(Job, id=pk, employer=request.user)
        app = get_object_or_404(job.applications, id=application_id)
        app.is_rejected = True
        app.is_shortlisted = False
        app.status = 'rejected'
        app.rejection_reason = request.data.get('rejection_reason', '')
        app.save()
        
        # Send email notification to candidate
        try:
            send_rejection_notification(
                candidate=app.candidate,
                job_or_project_title=job.title,
                application_type='job',
                rejection_reason=app.rejection_reason,
                company_name=job.company.company_name if job.company else None
            )
        except Exception as e:
            logger.error(f"Failed to send rejection email notification: {str(e)}")
            # Don't fail the request if email fails
            
        # Notify Candidate via WebSocket
        if app.candidate and app.candidate.user:
            from utils.broadcaster import broadcast_count_update
            from candidates.utils import get_candidate_unread_counts
            broadcast_count_update(
                user_id=app.candidate.user.id,
                count_type="applications",
                unread_count=get_candidate_unread_counts(app.candidate.user)
            )
        
        return Response({'message': 'Application rejected successfully'})