from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Employer, EmployerPreference, EmployerCompliance
from .serializers import (
    EmployerSerializer, EmployerListSerializer, EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer, EmployerComplianceSerializer
)


class EmployerProfileView(generics.RetrieveUpdateAPIView):
    """
    Employer profile view
    """
    serializer_class = EmployerSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        employer, created = Employer.objects.get_or_create(
            user=self.request.user,
            defaults={
                'first_name': self.request.user.first_name,
                'last_name': self.request.user.last_name
            }
        )
        return employer


class EmployerListView(generics.ListAPIView):
    """
    Employer list view (public profiles)
    """
    queryset = Employer.objects.filter(is_profile_public=True)
    serializer_class = EmployerListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['industry', 'size', 'location']
    search_fields = ['first_name', 'last_name', 'companyName', 'industry']
    ordering_fields = ['created_at', 'first_name']
    ordering = ['-created_at']


class EmployerProfileUpdateView(generics.UpdateAPIView):
    """
    Employer profile update view
    """
    serializer_class = EmployerProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        employer, created = Employer.objects.get_or_create(
            user=self.request.user,
            defaults={
                'first_name': self.request.user.first_name,
                'last_name': self.request.user.last_name
            }
        )
        return employer


class EmployerPreferenceView(generics.RetrieveUpdateAPIView):
    """
    Employer preferences view
    """
    serializer_class = EmployerPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        try:
            return self.request.user.employer_profile.preferences
        except EmployerPreference.DoesNotExist:
            return None
    
    def perform_create(self, serializer):
        employer = self.request.user.employer_profile
        serializer.save(employer=employer)


class EmployerComplianceView(generics.RetrieveUpdateAPIView):
    """
    Employer compliance view
    """
    serializer_class = EmployerComplianceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        try:
            return self.request.user.employer_profile.compliance
        except EmployerCompliance.DoesNotExist:
            return None
    
    def perform_create(self, serializer):
        employer = self.request.user.employer_profile
        serializer.save(employer=employer)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def employer_dashboard(request):
    """
    Employer dashboard data
    """
    try:
        employer = request.user.employer_profile
        data = {
            'profile': EmployerSerializer(employer).data,
            'is_profile_complete': employer.is_profile_complete,
            'jobs_posted': employer.total_jobs_posted,
            'projects_posted': employer.total_projects_posted,
            'applications_received': employer.total_applications_received,
            'hires': employer.total_hires,
        }
        
        # Add recent job applications
        recent_job_applications = employer.received_job_applications.all()[:5]
        data['recent_job_applications'] = [
            {
                'id': app.id,
                'candidate_name': app.candidate.full_name,
                'job_title': app.job.title,
                'company': app.company.company_name,
                'status': app.status,
                'applied_at': app.applied_at
            }
            for app in recent_job_applications
        ]
        
        # Add recent project applications
        recent_project_applications = employer.received_project_applications.all()[:5]
        data['recent_project_applications'] = [
            {
                'id': app.id,
                'candidate_name': app.candidate.full_name,
                'project_title': app.project.title,
                'company': app.company.company_name,
                'status': app.status,
                'applied_at': app.applied_at
            }
            for app in recent_project_applications
        ]
        
        return Response(data, status=status.HTTP_200_OK)
    except Employer.DoesNotExist:
        return Response({'error': 'Employer profile not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def complete_profile_section(request, section):
    """
    Mark a profile section as complete
    """
    try:
        employer = request.user.employer_profile
        section_fields = {
            'basic_info': 'basic_info_completed',
            'company_info': 'company_info_completed',
        }
        
        if section not in section_fields:
            return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)
        
        setattr(employer, section_fields[section], True)
        employer.save()
        
        return Response({
            'message': f'{section} section marked as complete',
            'is_profile_complete': employer.is_profile_complete
        }, status=status.HTTP_200_OK)
    except Employer.DoesNotExist:
        return Response({'error': 'Employer profile not found'}, status=status.HTTP_404_NOT_FOUND)
