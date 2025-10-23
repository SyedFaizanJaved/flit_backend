from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Job, JobSkill, JobLanguage
from .serializers import (
    JobSerializer, JobListSerializer, JobCreateSerializer, JobUpdateSerializer,
    JobSkillSerializer, JobLanguageSerializer
)
from accounts.permissions import IsEmployer

class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title', 'description', 'company__company_name']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list':
            return qs.filter(status='active')
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        if self.action == 'create':
            return JobCreateSerializer
        if self.action in ['update', 'partial_update']:
            return JobUpdateSerializer
        return JobSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'update_status', 'shortlist_application', 'reject_application', 'skills', 'languages']:
            return [permissions.IsAuthenticated(), IsEmployer()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='my-jobs')
    def my_jobs(self, request):
        jobs = Job.objects.filter(employer=request.user)
        page = self.paginate_queryset(jobs)
        serializer = JobSerializer(page or jobs, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=['get', 'post'], url_path='skills')
    def skills(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            skills = JobSkill.objects.filter(job=job)
            serializer = JobSkillSerializer(skills, many=True)
            return Response(serializer.data)
        serializer = JobSkillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], url_path='languages')
    def languages(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            langs = JobLanguage.objects.filter(job=job)
            serializer = JobLanguageSerializer(langs, many=True)
            return Response(serializer.data)
        serializer = JobLanguageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='applications')
    def applications(self, request, pk=None):
        try:
            job = Job.objects.get(id=pk, employer=request.user)
        except Job.DoesNotExist:
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        applications = job.applications.all()
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
                }
                for app in applications
            ],
            'total_applications': applications.count(),
            'shortlisted_count': applications.filter(is_shortlisted=True).count(),
            'rejected_count': applications.filter(is_rejected=True).count(),
        }
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='status')
    def update_status(self, request, pk=None):
        try:
            job = Job.objects.get(id=pk, employer=request.user)
        except Job.DoesNotExist:
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        new_status = request.data.get('status')
        if new_status not in ['draft', 'active', 'paused', 'closed', 'filled']:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        job.status = new_status
        job.save()
        return Response({'message': 'Job status updated successfully', 'job': JobSerializer(job).data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/shortlist')
    def shortlist_application(self, request, pk=None, application_id=None):
        try:
            job = Job.objects.get(id=pk, employer=request.user)
            application = job.applications.get(id=application_id)
        except Job.DoesNotExist:
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        application.is_shortlisted = True
        application.is_rejected = False
        application.status = 'shortlisted'
        application.save()
        return Response({'message': 'Application shortlisted successfully', 'application': {'id': application.id, 'candidate_name': application.candidate.full_name, 'status': application.status, 'is_shortlisted': application.is_shortlisted}}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/reject')
    def reject_application(self, request, pk=None, application_id=None):
        try:
            job = Job.objects.get(id=pk, employer=request.user)
            application = job.applications.get(id=application_id)
        except Job.DoesNotExist:
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        application.is_rejected = True
        application.is_shortlisted = False
        application.status = 'rejected'
        application.rejection_reason = request.data.get('rejection_reason', '')
        application.save()
        return Response({'message': 'Application rejected successfully', 'application': {'id': application.id, 'candidate_name': application.candidate.full_name, 'status': application.status, 'is_rejected': application.is_rejected}}, status=status.HTTP_200_OK)