from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.core.exceptions import ObjectDoesNotExist
from .models import Company
from .serializers import CompanySerializer, CompanyListSerializer, CompanyUpdateSerializer
from employers.models import Employer

class CompanyViewSet(viewsets.ViewSet):
    """
    ViewSet for Company management
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['industry', 'size', 'is_verified']
    search_fields = ['company_name', 'industry', 'description']
    ordering_fields = ['created_at', 'company_name']
    ordering = ['-created_at']

    def list(self, request):
        queryset = Company.objects.filter(is_active=True)
        for backend in self.filter_backends:
            queryset = backend().filter_queryset(request, queryset, self)
        serializer = CompanyListSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = CompanySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            company = serializer.save()

            # Update employer's profile to link with the created company
            try:
                employer = request.user.employer_profile
                employer.company = company
                employer.company_info_completed = True
                employer.save()

                # Update user's profile_completed flag as well
                if employer.is_profile_complete:
                    request.user.profile_completed = True
                    request.user.save(update_fields=['profile_completed'])

            except Employer.DoesNotExist:
                # If employer profile doesn't exist, create it
                employer = Employer.objects.create(
                    user=request.user,
                    company=company,
                    company_info_completed=True,
                    first_name=request.user.first_name,
                    last_name=request.user.last_name
                )

                # Update user's profile_completed flag
                if employer.is_profile_complete:
                    request.user.profile_completed = True
                    request.user.save(update_fields=['profile_completed'])

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None):
        try:
            company = Company.objects.get(pk=pk, is_active=True)
            serializer = CompanySerializer(company)
            return Response(serializer.data)
        except Company.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    def partial_update(self, request, pk=None):
        try:
            company = Company.objects.get(pk=pk, created_by=request.user, is_active=True)
            serializer = CompanyUpdateSerializer(company, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Company.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='my-companies')
    def my_companies(self, request):
        queryset = Company.objects.filter(created_by=request.user, is_active=True)
        serializer = CompanySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='dashboard')
    def dashboard(self, request, pk=None):
        try:
            company = Company.objects.get(id=pk, created_by=request.user)
            data = {
                'company': CompanySerializer(company).data,
                'company_name': company.company_name,
                'name': company.name,
                'jobs_count': getattr(company, 'jobs', type('obj', (object,), {'count': lambda: 0})()).count() if hasattr(company, 'jobs') else 0,
                'projects_count': getattr(company, 'projects', type('obj', (object,), {'count': lambda: 0})()).count() if hasattr(company, 'projects') else 0,
                'applications_count': 0,
                'hires_count': 0,  
            }
            
            # Add recent jobs (if jobs model exists)
            if hasattr(company, 'jobs'):
                recent_jobs = company.jobs.all()[:5]
                data['recent_jobs'] = [
                    {
                        'id': job.id,
                        'title': getattr(job, 'title', ''),
                        'status': getattr(job, 'status', ''),
                        'applications_count': getattr(job, 'applications', type('obj', (object,), {'count': lambda: 0})()).count(),
                        'created_at': getattr(job, 'created_at', None)
                    }
                    for job in recent_jobs
                ]
            else:
                data['recent_jobs'] = []
            
            # Add recent projects (similarly)
            if hasattr(company, 'projects'):
                recent_projects = company.projects.all()[:5]
                data['recent_projects'] = [
                    {
                        'id': project.id,
                        'title': getattr(project, 'title', ''),
                        'status': getattr(project, 'status', ''),
                        'applications_count': getattr(project, 'applications', type('obj', (object,), {'count': lambda: 0})()).count(),
                        'created_at': getattr(project, 'created_at', None)
                    }
                    for project in recent_projects
                ]
            else:
                data['recent_projects'] = []
            
            return Response(data, status=status.HTTP_200_OK)
        except Company.DoesNotExist:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        if not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            company = Company.objects.get(id=pk)
            company.is_verified = True
            company.save()
            
            return Response({
                'message': 'Company verified successfully',
                'company': CompanySerializer(company).data
            }, status=status.HTTP_200_OK)
        except Company.DoesNotExist:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        try:
            company = Company.objects.get(id=pk, created_by=request.user)
            company.is_active = False
            company.save()
            
            return Response({
                'message': 'Company deactivated successfully',
                'company': CompanySerializer(company).data
            }, status=status.HTTP_200_OK)
        except Company.DoesNotExist:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)