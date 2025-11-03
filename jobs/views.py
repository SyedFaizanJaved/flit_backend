from rest_framework import viewsets, status, permissions, mixins, authentication
from rest_framework.decorators import action, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Job, JobSkill, JobLanguage
from .serializers import (
    JobSerializer, JobListSerializer, JobCreateSerializer, JobUpdateSerializer,
    JobSkillSerializer, JobLanguageSerializer
)
from companies.models import Company
from accounts.permissions import IsEmployer



class PublicAuthentication(authentication.BaseAuthentication):
    """
    Authentication class that allows any request (public access).
    """
    def authenticate(self, request):
        return None  

@authentication_classes([]) 
@permission_classes([permissions.AllowAny])  # Anyone can access
class PublicJobViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      GenericViewSet):
    """
    Public API: Anyone can see active jobs
    """
    queryset = Job.objects.all()
    serializer_class = JobListSerializer

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title', 'description', 'company__company_name']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']
    pagination_class = None  # Disable pagination to show all jobs on one page


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title', 'description', 'company__company_name']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Filter jobs based on the current user and request context.
        For employer users, only show jobs from their company by default.
        """
        queryset = super().get_queryset()
        
        # For list action, only show active jobs
        if self.action == 'list':
            queryset = queryset.filter(status='active')
            
        # For employer users, filter by their company
        if hasattr(self.request.user, 'employer_profile'):
            queryset = queryset.filter(company=self.request.user.employer_profile.company)
        
        # For owner-scoped actions, filter by the employer
        owner_scoped_actions = {
            'update', 'partial_update', 'destroy',
            'skills', 'languages', 'applications', 'update_status',
            'shortlist_application', 'reject_application'
        }
        if getattr(self, 'action', None) in owner_scoped_actions:
            queryset = queryset.filter(employer=self.request.user)
            
        # Allow explicit company filtering via query params
        company_id = self.request.query_params.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
            
        return queryset
    
    @action(detail=False, methods=['get'])
    def my_jobs(self, request):
        """
        Get jobs posted by the current user's company.
        """
        # Get the company ID from query params if provided
        company_id = request.query_params.get('company_id')
        
        if company_id:
            # If company_id is provided, verify the user has access to this company
            from companies.models import Company
            try:
                company = Company.objects.get(id=company_id)
                if not (request.user.is_staff or company.employers.filter(user=request.user).exists()):
                    return Response(
                        {'error': 'You do not have permission to view jobs for this company'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                queryset = self.filter_queryset(Job.objects.filter(company_id=company_id))
            except Company.DoesNotExist:
                return Response(
                    {'error': 'Company not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # If no company_id provided, get all companies the user has access to
          
            user_companies = Company.objects.filter(employers__user=request.user)
            if not user_companies.exists():
                return Response([], status=status.HTTP_200_OK)
                
            queryset = self.filter_queryset(Job.objects.filter(company__in=user_companies))
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = JobListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
            
        serializer = JobListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


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
        
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            response.data = {
                'message': 'Job created successfully',
                'data': response.data
            }
        return response
        
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            response.data = {
                'message': 'Job updated successfully',
                'data': response.data
            }
        return response
        
    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        self.perform_destroy(job)
        return Response(
            {'message': 'Job deleted successfully'}, 
            status=status.HTTP_200_OK
        )

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