from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Company
from .serializers import CompanySerializer, CompanyListSerializer, CompanyUpdateSerializer


class CompanyListView(generics.ListCreateAPIView):
    """
    Company list and create view
    """
    queryset = Company.objects.filter(is_active=True)
    serializer_class = CompanyListSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['industry', 'size', 'is_verified']
    search_fields = ['company_name', 'industry', 'description']
    ordering_fields = ['created_at', 'company_name']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CompanySerializer
        return CompanyListSerializer


class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Company detail view
    """
    queryset = Company.objects.filter(is_active=True)
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return CompanyUpdateSerializer
        return CompanySerializer


class CompanyUpdateView(generics.UpdateAPIView):
    """
    Company update view
    """
    serializer_class = CompanyUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Only allow users to update companies they created
        return Company.objects.filter(created_by=self.request.user, is_active=True)


class MyCompaniesView(generics.ListAPIView):
    """
    User's companies view
    """
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Company.objects.filter(created_by=self.request.user, is_active=True)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def company_dashboard(request, company_id):
    """
    Company dashboard data
    """
    try:
        company = Company.objects.get(id=company_id, created_by=request.user)
        data = {
            'company': CompanySerializer(company).data,
            'jobs_count': company.jobs.count(),
            'projects_count': company.projects.count(),
            'applications_count': company.job_applications.count() + company.project_applications.count(),
            'hires_count': company.total_hires,
        }
        
        # Add recent jobs
        recent_jobs = company.jobs.all()[:5]
        data['recent_jobs'] = [
            {
                'id': job.id,
                'title': job.title,
                'status': job.status,
                'applications_count': job.applications.count(),
                'created_at': job.created_at
            }
            for job in recent_jobs
        ]
        
        # Add recent projects
        recent_projects = company.projects.all()[:5]
        data['recent_projects'] = [
            {
                'id': project.id,
                'title': project.title,
                'status': project.status,
                'applications_count': project.applications.count(),
                'created_at': project.created_at
            }
            for project in recent_projects
        ]
        
        return Response(data, status=status.HTTP_200_OK)
    except Company.DoesNotExist:
        return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def verify_company(request, company_id):
    """
    Verify company (admin only)
    """
    if not request.user.is_staff:
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        company = Company.objects.get(id=company_id)
        company.is_verified = True
        company.save()
        
        return Response({
            'message': 'Company verified successfully',
            'company': CompanySerializer(company).data
        }, status=status.HTTP_200_OK)
    except Company.DoesNotExist:
        return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def deactivate_company(request, company_id):
    """
    Deactivate company
    """
    try:
        company = Company.objects.get(id=company_id, created_by=request.user)
        company.is_active = False
        company.save()
        
        return Response({
            'message': 'Company deactivated successfully',
            'company': CompanySerializer(company).data
        }, status=status.HTTP_200_OK)
    except Company.DoesNotExist:
        return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)
