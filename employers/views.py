from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.http import Http404
from .models import Employer, EmployerPreference, EmployerCompliance
from .serializers import (
    EmployerSerializer, 
    EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer,
    EmployerComplianceSerializer,
    EmployerRegistrationSerializer
)
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
import logging
from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Employer, EmployerPreference, EmployerCompliance
from .serializers import (
    EmployerSerializer, EmployerListSerializer, EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer, EmployerComplianceSerializer
)
from accounts.views import BaseRoleRegistrationView
from django.urls import reverse
import requests
from rest_framework.reverse import reverse as drf_reverse
        

User = get_user_model()
logger = logging.getLogger(__name__)


class EmployerDashboardBaseView(APIView):
    """Base view for employer dashboard endpoints with common functionality."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_employer_profile(self, user):
        try:
            return user.employer_profile
        except Employer.DoesNotExist:
            raise Http404('Employer profile not found')


class EmployerProfileDashboardView(EmployerDashboardBaseView):
    """Endpoint for employer profile data in dashboard."""
    def get(self, request):
        employer = self.get_employer_profile(request.user)
        serializer = EmployerSerializer(employer, context={'request': request})
        
        return Response({
            'profile': serializer.data,
            'profile_completed': employer.is_profile_complete,
            'jobs_posted': employer.total_jobs_posted,
            'projects_posted': employer.total_projects_posted,
            'applications_received': employer.total_applications_received,
            'hires': employer.total_hires,
        })


class EmployerJobApplicationsView(EmployerDashboardBaseView):
    """Endpoint for employer's recent job applications."""
    def get(self, request):
        try:
            employer = self.get_employer_profile(request.user)
            
            # Get recent job applications for the employer
            from applications.models import JobApplication
            recent_job_applications = JobApplication.objects.filter(
                employer=request.user
            ).select_related('candidate', 'job', 'company')
            
            # Get the count of applications by status
            status_choices = ['pending', 'reviewing', 'shortlisted', 'interviewed', 'hired', 'rejected', 'withdrawn']
            status_counts = {f'{status}_count': recent_job_applications.filter(status=status).count() 
                           for status in status_choices}
            
            # Get recent applications for the response
            recent_applications = recent_job_applications.order_by('-applied_at')[:5]
            
            applications_data = []
            for app in recent_applications:
                try:
                    candidate_name = f"{app.candidate.first_name} {app.candidate.last_name}" \
                        if hasattr(app, 'candidate') and app.candidate else 'Unknown Candidate'
                    
                    applications_data.append({
                        'id': app.id,
                        'candidate_name': candidate_name,
                        'job_title': app.job.title if hasattr(app, 'job') and app.job else 'Unknown Job',
                        'company': app.company.company_name if hasattr(app, 'company') and app.company else 'Unknown Company',
                        'status': app.status,
                        'applied_at': app.applied_at,
                        'type': 'job',
                        'match_score': app.overall_match_score if hasattr(app, 'overall_match_score') else None
                    })
                except Exception as app_err:
                    logger.error(f"Error processing job application {app.id}: {str(app_err)}", exc_info=True)
                    continue  # Skip this application but continue with others
            
            return Response({
                'recent_job_applications': applications_data,
                'total_job_applications': recent_job_applications.count(),
                **status_counts
            })
            
        except Exception as e:
            logger.error(f"Error in EmployerJobApplicationsView: {str(e)}", exc_info=True)
            return Response(
                {'error': 'An error occurred while fetching job applications'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EmployerProjectApplicationsView(EmployerDashboardBaseView):
    """Endpoint for employer's recent project applications."""
    def get(self, request):
        try:
            employer = self.get_employer_profile(request.user)
            
            # Get recent project applications for the employer
            from applications.models import ProjectApplication
            recent_project_applications = ProjectApplication.objects.filter(
                employer=request.user
            ).select_related('candidate', 'project', 'company')
            
            # Get the count of applications by status
            status_choices = ['pending', 'reviewing', 'shortlisted', 'hired', 'rejected', 'withdrawn']
            status_counts = {f'{status}_count': recent_project_applications.filter(status=status).count() 
                           for status in status_choices}
            
            # Get recent applications for the response
            recent_applications = recent_project_applications.order_by('-applied_at')[:5]
            
            applications_data = []
            for app in recent_applications:
                try:
                    candidate_name = f"{app.candidate.first_name} {app.candidate.last_name}" \
                        if hasattr(app, 'candidate') and app.candidate else 'Unknown Candidate'
                    
                    applications_data.append({
                        'id': app.id,
                        'candidate_name': candidate_name,
                        'project_title': app.project.title if hasattr(app, 'project') and app.project else 'Unknown Project',
                        'company': app.company.company_name if hasattr(app, 'company') and app.company else 'Unknown Company',
                        'status': app.status,
                        'applied_at': app.applied_at,
                        'type': 'project',
                        'match_score': app.overall_match_score if hasattr(app, 'overall_match_score') else None
                    })
                except Exception as app_err:
                    logger.error(f"Error processing project application {app.id}: {str(app_err)}", exc_info=True)
                    continue  # Skip this application but continue with others
            
            return Response({
                'recent_project_applications': applications_data,
                'total_project_applications': recent_project_applications.count(),
                **status_counts
            })
            
        except Exception as e:
            logger.error(f"Error in EmployerProjectApplicationsView: {str(e)}", exc_info=True)
            return Response(
                {'error': 'An error occurred while fetching project applications'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




class EmployerRegistrationView(BaseRoleRegistrationView):
    """Register a new employer user (role is forced to employer)."""
    fixed_user_type = "employer"

class EmployerViewSet(viewsets.ViewSet):
    """ViewSet consolidating employer endpoints (list, profile, dashboard, prefs, compliance)."""

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        queryset = Employer.objects.filter(is_profile_public=True)
        serializer = EmployerListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        employer, _ = Employer.objects.get_or_create(
            user=request.user,
            defaults={'first_name': request.user.first_name, 'last_name': request.user.last_name}
        )

        if request.method in ['PUT', 'PATCH']:
            serializer = EmployerProfileUpdateSerializer(employer, data=request.data, partial=(request.method == 'PATCH'))
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(EmployerSerializer(employer).data, status=status.HTTP_200_OK)

        return Response(EmployerSerializer(employer).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard(self, request):
        """
        Legacy dashboard endpoint that combines all dashboard data.
        This is kept for backward compatibility but can be deprecated later.
        """

        base_url = request.build_absolute_uri('/')
        
        # Get profile data
        profile_url = base_url.rstrip('/') + drf_reverse('employer-profile-dashboard')
        profile_response = requests.get(
            profile_url,
            headers={'Authorization': request.META.get('HTTP_AUTHORIZATION', '')}
        )
        
        if profile_response.status_code != 200:
            return Response(
                {'error': 'Could not fetch profile data'}, 
                status=profile_response.status_code
            )
            
        response_data = profile_response.json()
        
        # Add other dashboard data
        endpoints = [
            ('job_applications', 'employer-job-applications'),
            ('project_applications', 'employer-project-applications')
        ]
        
        for key, url_name in endpoints:
            endpoint_url = base_url.rstrip('/') + drf_reverse(url_name)
            endpoint_response = requests.get(
                endpoint_url,
                headers={'Authorization': request.META.get('HTTP_AUTHORIZATION', '')}
            )
            
            if endpoint_response.status_code == 200:
                response_data.update(endpoint_response.json())
        
        return Response(response_data)

    @action(detail=False, methods=['post'], url_path='profile/complete/(?P<section>[^/.]+)', permission_classes=[permissions.IsAuthenticated])
    def complete_profile_section(self, request, section=None):
        try:
            employer = request.user.employer_profile
        except Employer.DoesNotExist:
            return Response({'error': 'Employer profile not found'}, status=status.HTTP_404_NOT_FOUND)

        section_fields = {
            'basic_info': 'basic_info_completed',
            'company_info': 'company_info_completed',
        }

        if section not in section_fields:
            return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)

        setattr(employer, section_fields[section], True)
        employer.save()

        # Sync to user's profile_completed flag as well
        try:
            user = employer.user
            if employer.is_profile_complete != getattr(user, 'profile_completed', False):
                user.profile_completed = employer.is_profile_complete
                user.save(update_fields=['profile_completed'])
        except Exception:
            pass

        return Response({
            'message': f'{section} section marked as complete',
            'profile_completed': employer.is_profile_complete
        }, status=status.HTTP_200_OK)


    


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

