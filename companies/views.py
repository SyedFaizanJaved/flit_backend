from rest_framework import viewsets, mixins, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .models import Company
from .serializers import (
    CompanySerializer,
    CompanyListSerializer,
    CompanyUpdateSerializer,
)
from employers.models import Employer
import logging

logger = logging.getLogger("exceptions")

User = get_user_model()


# Custom Permission: Sirf company ka creator hi update/delete kar sake
class IsCompanyOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.created_by == request.user


class CompanyViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Optimized Company ViewSet
    - Uses GenericViewSet + Mixins for less boilerplate
    - Proper permissions
    - Clean dashboard & custom actions
    """
    queryset = Company.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['industry', 'size', 'is_verified']
    search_fields = ['company_name', 'industry', 'description']
    ordering_fields = ['created_at', 'company_name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return CompanyListSerializer
        if self.action in ['update', 'partial_update']:
            return CompanyUpdateSerializer
        return CompanySerializer

    def get_permissions(self):
        """
        Granular permissions:
        - partial_update & destroy: only company owner
        - verify: only staff/admin
        """
        if self.action in ['partial_update', 'update', 'destroy']:
            return [permissions.IsAuthenticated(), IsCompanyOwner()]
        if self.action == 'verify':
            return [permissions.IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        """
        my_companies action ke liye filtered queryset
        """
        if self.action == 'my_companies':
            return Company.objects.filter(created_by=self.request.user)
        return super().get_queryset()

    def perform_create(self, serializer):
        """
        Create ke time automatically created_by set kar do
        """
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        """
        Override create to handle Employer profile linking properly
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.save(created_by=request.user)

        # Employer profile link or create
        employer, created = Employer.objects.get_or_create(
            user=request.user,
            defaults={
                'company': company,
                'company_info_completed': True,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
            },
        )
        if not created:
            employer.company = company
            employer.company_info_completed = True
            employer.save(update_fields=['company', 'company_info_completed'])

        # Update user profile_completed flag if needed
        if employer.is_profile_complete:
            request.user.profile_completed = True
            request.user.save(update_fields=['profile_completed'])

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='my-companies')
    def my_companies(self, request):
        """
        Logged-in user ki apni companies list
        """
        queryset = self.get_queryset()  
        serializer = CompanySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='dashboard')
    def dashboard(self, request, pk=None):
        """
        Company dashboard with stats & recent jobs/projects
        """
        company = get_object_or_404(Company, id=pk, created_by=request.user)

        data = {
            'company': CompanySerializer(company).data,
            'company_name': company.company_name,
            'name': company.name,
            'jobs_count': company.jobs.count() if hasattr(company, 'jobs') else 0,
            'projects_count': company.projects.count() if hasattr(company, 'projects') else 0,
            'applications_count': 0,  
            'hires_count': 0,
            'recent_jobs': [],
            'recent_projects': [],
        }

        # Recent Jobs
        if hasattr(company, 'jobs'):
            recent_jobs = company.jobs.all()[:5]
            data['recent_jobs'] = [
                {
                    'id': job.id,
                    'title': getattr(job, 'title', ''),
                    'status': getattr(job, 'status', ''),
                    'applications_count': job.applications.count() if hasattr(job, 'applications') else 0,
                    'created_at': job.created_at,
                }
                for job in recent_jobs
            ]

        if hasattr(company, 'projects'):
            recent_projects = company.projects.all()[:5]
            data['recent_projects'] = [
                {
                    'id': project.id,
                    'title': getattr(project, 'title', ''),
                    'status': getattr(project, 'status', ''),
                    'applications_count': project.applications.count() if hasattr(project, 'applications') else 0,
                    'created_at': project.created_at,
                }
                for project in recent_projects
            ]

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        """
        Admin/Staff only: Company ko verify karna
        """
        company = get_object_or_404(Company, id=pk)
        company.is_verified = True
        company.save(update_fields=['is_verified'])

        return Response(
            {
                'message': 'Company verified successfully',
                'company': CompanySerializer(company).data,
            },
            status=status.HTTP_200_OK,
        )