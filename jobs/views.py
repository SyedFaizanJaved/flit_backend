import logging
import requests
import time
import re
from rest_framework import permissions
from django.conf import settings
from django.db import models
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


@authentication_classes([PublicAuthentication])
@permission_classes([permissions.AllowAny])
class PublicJobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """
    Public endpoints: List and retrieve active jobs (no auth required)
    """
    queryset = Job.objects.filter(status='active').select_related('company')
    serializer_class = JobListSerializer
    pagination_class = CustomPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
    
        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    escaped_term = re.escape(term)
                    # Match whole word, including at start or end of title
                    pattern = fr'(?:^|\s){escaped_term}(?:\s|$)'
                    queryset = queryset.filter(title__iregex=pattern)
       
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


class JobViewSet(viewsets.ModelViewSet):
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
        qs = super().get_queryset()

        if hasattr(self.request.user, 'employer_profile'):
            qs = qs.filter(company=self.request.user.employer_profile.company)

        if self.action == 'list':
            qs = qs.filter(status='active')

        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    escaped_term = re.escape(term)
                    qs = qs.filter(title__iregex=fr'\b{escaped_term}\b')

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

        # Get company for counting active items
        company = None
        if hasattr(request.user, 'employer_profile'):
            company = request.user.employer_profile.company

        # Count active jobs
        active_jobs_count = 0
        if company:
            active_jobs_count = Job.objects.filter(company=company, status='active').count()

        page = self.paginate_queryset(queryset)
        serializer = JobListSerializer(
            page if page is not None else queryset,
            many=True,
            context={'request': request}
        )

        if page is not None:
            paginated_response = self.get_paginated_response(serializer.data)
            # Reconstruct response with active_jobs right after current_page
            return Response({
                'count': paginated_response.data['count'],
                'next': paginated_response.data['next'],
                'previous': paginated_response.data['previous'],
                'total_pages': paginated_response.data['total_pages'],
                'current_page': paginated_response.data['current_page'],
                'active_jobs': active_jobs_count,
                'results': paginated_response.data['results']
            })

        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
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

    def _call_ml_create_api(self, job):
        return self._call_ml_api(f"{settings.FLIT_AI_URL}/create_jobs/{job.id}", job, is_create=True)

    def _call_ml_update_api(self, job):
        return self._call_ml_api(f"{settings.FLIT_AI_URL}/update_job_data/{job.id}", job, is_create=False)

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
                application_type='job'
            )
        except Exception as e:
            logger.error(f"Failed to send shortlist email notification: {str(e)}")
            # Don't fail the request if email fails
        
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
                rejection_reason=app.rejection_reason
            )
        except Exception as e:
            logger.error(f"Failed to send rejection email notification: {str(e)}")
            # Don't fail the request if email fails
        
        return Response({'message': 'Application rejected successfully'})