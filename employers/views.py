from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from utils.pagination import CustomPagination
from django.shortcuts import get_object_or_404
from django.http import Http404, JsonResponse
import os
import requests
import logging
from .models import Employer, EmployerPreference, EmployerCompliance, CandidateAction
from .serializers import (
    EmployerSerializer, 
    EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer,
    EmployerComplianceSerializer,
    EmployerRegistrationSerializer,
    CandidateActionSerializer
)
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework.decorators import api_view
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
from .models import Employer, EmployerPreference, EmployerCompliance, CandidateAction
from .serializers import (
    EmployerSerializer, EmployerListSerializer, EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer, EmployerComplianceSerializer, CandidateActionDetailSerializer
)
from accounts.views import BaseRoleRegistrationView
from django.urls import reverse
import requests
from applications.models import JobApplication, ProjectApplication
from rest_framework.reverse import reverse as drf_reverse

exception_logger = logging.getLogger("exceptions")
        

User = get_user_model()
logger = logging.getLogger(__name__)


class EmployerDashboardBaseView(APIView):
    """Base view for employer dashboard endpoints with common functionality."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_employer_profile(self, user):
        try:
            return user.employer_profile
        except Employer.DoesNotExist:
            exception_logger.error("Employer.DoesNotExist: Employer profile not found")
            raise Http404('Employer profile not found')

class CandidateActionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for employer to pass (FLIT) or reject a candidate.
    Only one action per employer per candidate allowed.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'by_candidate', 'shortlisted']:
            return CandidateActionDetailSerializer
        return CandidateActionSerializer

    def get_queryset(self):
        return CandidateAction.objects.filter(
            employer__user=self.request.user,
            action='pass'  # Only include 'pass' actions
        ).select_related('employer').order_by('-created_at')

    def create(self, request, *args, **kwargs):
        employer = request.user.employer_profile

        # candidate_id ko body ya query params se flexibly le lo
        candidate_id = request.data.get('candidate_id') or request.query_params.get('candidate_id')
        requested_action = request.data.get('action')

        if not candidate_id:
            return Response(
                {"detail": "candidate_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not requested_action:
            return Response(
                {"detail": "action is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if requested_action not in ['pass', 'reject']:
            return Response(
                {"detail": "action must be either 'pass' or 'reject'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Check if already acted on this candidate
            instance = CandidateAction.objects.get(
                employer=employer,
                candidate_id=candidate_id
            )

            # Agar same action dobara kar raha hai
            if instance.action == requested_action:
                if requested_action == "pass":
                    message = "You have already flited this candidate"
                else:
                    message = "You have already rejected this candidate"

                return Response(
                    {"detail": message},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Different action → update kar do (e.g., pass → reject ya reject → pass)
            instance.action = requested_action
            instance.save()

            serializer = CandidateActionDetailSerializer(instance, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        except CandidateAction.DoesNotExist:
            # Pehli baar action → naya record create karo
            serializer = self.get_serializer(data={
                'candidate_id': candidate_id,
                'action': requested_action
            })
            serializer.is_valid(raise_exception=True)
            serializer.save(employer=employer)

            detail_serializer = CandidateActionDetailSerializer(
                serializer.instance,
                context={'request': request}
            )
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    # Optional: partial_update ko disable kar do ya redirect kar do create pe
    # Kyunki ab sab create endpoint se ho raha hai
    def partial_update(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)
        
    @action(detail=False, methods=['get'])
    def shortlisted(self, request):
        """
        List all candidates that have been shortlisted by the employer
        """
        from applications.models import JobApplication, ProjectApplication
        from django.db.models import Q
        
        # Get the employer profile
        employer = request.user.employer_profile
        
        # Get shortlisted job applications
        job_applications = JobApplication.objects.filter(
            employer=employer.user,
            is_shortlisted=True
        ).select_related('candidate__user')
        
        # Get shortlisted project applications
        project_applications = ProjectApplication.objects.filter(
            employer=employer.user,
            is_shortlisted=True
        ).select_related('candidate__user')
        
        # Combine and paginate results
        combined = []
        
        # Add job applications
        for app in job_applications:
            combined.append({
                'id': app.id,
                'type': 'job',
                'title': app.job.title,
                'status': 'shortlisted',
                'applied_at': app.applied_at,
                'application': {
                    'id': app.id,
                    'candidate_name': app.candidate.full_name,
                    'candidate_user_id': app.candidate.user.id,
                    'job_title': app.job.title,
                    'job_id': app.job.id,
                    'company_name': app.company.name,
                    'status': app.status,
                    'candidate_profile_image': app.candidate.profile_image.url if app.candidate.profile_image else None,
                    'coverLetter': app.coverLetter,
                    'overall_match_score': app.overall_match_score,
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected
                }
            })
        
        # Add project applications
        for app in project_applications:
            combined.append({
                'id': app.id,
                'type': 'project',
                'title': app.project.title,
                'status': 'shortlisted',
                'applied_at': app.applied_at,
                'application': {
                    'id': app.id,
                    'candidate_name': app.candidate.full_name,
                    'candidate_user_id': app.candidate.user.id,
                    'project_title': app.project.title,
                    'project_id': app.project.id,
                    'company_name': app.company.name,
                    'status': app.status,
                    'candidate_profile_image': app.candidate.profile_image.url if app.candidate.profile_image else None,
                    'coverLetter': app.coverLetter,
                    'overall_match_score': app.overall_match_score,
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected
                }
            })
        
        # Sort by applied_at in descending order
        combined.sort(key=lambda x: x['applied_at'], reverse=True)
        
        # Paginate the results
        page = self.paginate_queryset(combined)
        if page is not None:
            return self.get_paginated_response(page)
            
        return Response(combined)

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
                    exception_logger.exception(f"Error processing job application {app.id}")
                    logger.error(f"Error processing job application {app.id}: {str(app_err)}", exc_info=True)
                    continue  # Skip this application but continue with others
            
            return Response({
                'recent_job_applications': applications_data,
                'total_job_applications': recent_job_applications.count(),
                **status_counts
            })
            
        except Exception as e:
            exception_logger.exception("Error fetching job applications")
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
                    exception_logger.exception(f"Error processing project application {app.id}")
                    logger.error(f"Error processing project application {app.id}: {str(app_err)}", exc_info=True)
                    continue  # Skip this application but continue with others
            
            return Response({
                'recent_project_applications': applications_data,
                'total_project_applications': recent_project_applications.count(),
                **status_counts
            })
            
        except Exception as e:
            exception_logger.exception("Error fetching project applications")
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
            exception_logger.error("Employer.DoesNotExist: Employer profile not found")
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
            exception_logger.exception("Error syncing profile_completed flag for employer")
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
            exception_logger.error("EmployerPreference.DoesNotExist: Employer preferences not found")
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
            exception_logger.error("EmployerCompliance.DoesNotExist: Employer compliance not found")
            return None
    
    def perform_create(self, serializer):
        employer = self.request.user.employer_profile
        serializer.save(employer=employer)


@api_view(['GET'])
def get_flitpass_data(request, company_id):
    """
    Fetches data from the ML API for the given company ID.
    """
    try:
        # The ML API endpoint URL
        ml_api_url = f"{settings.FLIT_AI_URL}/flitpass/{company_id}"
        
        # Make the GET request to the ML API
        response = requests.get(ml_api_url)
        
        # Check if the request was successful
        response.raise_for_status()
        
        # Return the JSON response from the ML API
        return Response(response.json())
        
    except requests.exceptions.RequestException as e:
        # Log the error for debugging
        exception_logger.exception(f"Error calling ML API")
        logger.error(f"Error calling ML API: {str(e)}")
        
        # Return an error response
        return Response(
            {"error": "Failed to fetch data from ML API", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )