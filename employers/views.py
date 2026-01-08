import logging
import requests
from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.urls import reverse as drf_reverse

from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from accounts.views import BaseRoleRegistrationView
from utils.pagination import CustomPagination

from .models import Employer, EmployerPreference, EmployerCompliance, CandidateAction
from .serializers import (
    EmployerSerializer,
    EmployerListSerializer,
    EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer,
    EmployerComplianceSerializer,
    CandidateActionSerializer,
    CandidateActionDetailSerializer,
)
from applications.models import JobApplication, ProjectApplication

User = get_user_model()
logger = logging.getLogger(__name__)
exception_logger = logging.getLogger("exceptions")


class EmployerDashboardBaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_employer_profile(self, user):
        try:
            return user.employer_profile
        except Employer.DoesNotExist:
            exception_logger.error("Employer profile not found for user %s", user.id)
            raise Http404("Employer profile not found")


class CandidateActionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'shortlisted']:
            return CandidateActionDetailSerializer
        return CandidateActionSerializer
        
    def get_queryset(self):
        return CandidateAction.objects.filter(
            employer__user=self.request.user,
            action='pass'
        ).select_related('employer').order_by('-created_at')

    def create(self, request, *args, **kwargs):
        employer = request.user.employer_profile
        candidate_id = request.data.get('candidate_id') or request.query_params.get('candidate_id')
        requested_action = request.data.get('action')

        if not candidate_id:
            return Response({"detail": "candidate_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not requested_action:
            return Response({"detail": "action is required"}, status=status.HTTP_400_BAD_REQUEST)
        if requested_action not in ['pass', 'reject']:
            return Response({"detail": "action must be 'pass' or 'reject'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance = CandidateAction.objects.get(employer=employer, candidate_id=candidate_id)
            instance.action = requested_action
            instance.save()
            serializer = CandidateActionDetailSerializer(instance, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CandidateAction.DoesNotExist:
            serializer = self.get_serializer(data={
                'candidate_id': candidate_id,
                'action': requested_action
            })
            serializer.is_valid(raise_exception=True)
            serializer.save(employer=employer)
            detail_serializer = CandidateActionDetailSerializer(serializer.instance, context={'request': request})
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def shortlisted(self, request):
        employer_user = request.user

        job_applications = JobApplication.objects.filter(
            employer=employer_user,
            is_shortlisted=True
        ).select_related('candidate__user', 'job', 'company')

        project_applications = ProjectApplication.objects.filter(
            employer=employer_user,
            is_shortlisted=True
        ).select_related('candidate__user', 'project', 'company')

        combined = []

        for app in job_applications:
            combined.append({
                'id': app.id,
                'type': 'job',
                'title': app.job.title,
                'status': 'shortlisted',
                'applied_at': app.applied_at,
                'application': {
                    'id': app.id,
                    'candidate_id': app.candidate.id,
                    'candidate_name': app.candidate.full_name,
                    'candidate_email': app.candidate.user.email,
                    'candidate_user_id': app.candidate.user.id,
                    'job_title': app.job.title,
                    'job_id': app.job.id,
                    'company_name': app.company.name,
                    'status': app.status,
                    'candidate_profile_image': app.candidate.profile_image.url if app.candidate.profile_image else None,
                    'coverLetter': app.coverLetter,
                    'overall_match_score': getattr(app, 'overall_match_score', None),
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected,
                }
            })

        for app in project_applications:
            combined.append({
                'id': app.id,
                'type': 'project',
                'title': app.project.title,
                'status': 'shortlisted',
                'applied_at': app.applied_at,
                'application': {
                    'id': app.id,
                    'candidate_id': app.candidate.id,
                    'candidate_name': app.candidate.full_name,
                    'candidate_email': app.candidate.user.email,
                    'candidate_user_id': app.candidate.user.id,
                    'project_title': app.project.title,
                    'project_id': app.project.id,
                    'company_name': app.company.name,
                    'status': app.status,
                    'candidate_profile_image': app.candidate.profile_image.url if app.candidate.profile_image else None,
                    'coverLetter': app.coverLetter,
                    'overall_match_score': getattr(app, 'overall_match_score', None),
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected,
                }
            })

        combined.sort(key=lambda x: x['applied_at'], reverse=True)

        page = self.paginate_queryset(combined)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(combined)


class EmployerProfileDashboardView(EmployerDashboardBaseView):
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
    def get(self, request):
        applications = JobApplication.objects.filter(
            employer=request.user
        ).select_related('candidate__user', 'job', 'company').order_by('-applied_at')

        status_choices = ['pending', 'reviewing', 'shortlisted', 'interviewed', 'hired', 'rejected', 'withdrawn']
        status_counts = {f'{s}_count': applications.filter(status=s).count() for s in status_choices}

        recent = applications[:5]
        data = []
        for app in recent:
            candidate_name = app.candidate.full_name if app.candidate else "Unknown Candidate"
            data.append({
                'id': app.id,
                'candidate_name': candidate_name,
                'job_title': app.job.title if app.job else "Unknown Job",
                'company': app.company.company_name if app.company else "Unknown Company",
                'status': app.status,
                'applied_at': app.applied_at,
                'type': 'job',
                'match_score': getattr(app, 'overall_match_score', None),
            })

        return Response({
            'recent_job_applications': data,
            'total_job_applications': applications.count(),
            **status_counts
        })


class EmployerProjectApplicationsView(EmployerDashboardBaseView):
    def get(self, request):
        applications = ProjectApplication.objects.filter(
            employer=request.user
        ).select_related('candidate__user', 'project', 'company').order_by('-applied_at')

        status_choices = ['pending', 'reviewing', 'shortlisted', 'hired', 'rejected', 'withdrawn']
        status_counts = {f'{s}_count': applications.filter(status=s).count() for s in status_choices}

        recent = applications[:5]
        data = []
        for app in recent:
            candidate_name = app.candidate.full_name if app.candidate else "Unknown Candidate"
            data.append({
                'id': app.id,
                'candidate_name': candidate_name,
                'project_title': app.project.title if app.project else "Unknown Project",
                'company': app.company.company_name if app.company else "Unknown Company",
                'status': app.status,
                'applied_at': app.applied_at,
                'type': 'project',
                'match_score': getattr(app, 'overall_match_score', None),
            })

        return Response({
            'recent_project_applications': data,
            'total_project_applications': applications.count(),
            **status_counts
        })


class EmployerRegistrationView(BaseRoleRegistrationView):
    fixed_user_type = "employer"


class EmployerViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    def list(self, request):
        queryset = Employer.objects.filter(is_profile_public=True)
        serializer = EmployerListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        employer, _ = Employer.objects.get_or_create(
            user=request.user,
            defaults={'first_name': request.user.first_name, 'last_name': request.user.last_name}
        )

        if request.method == 'GET':
            return Response(EmployerSerializer(employer, context={'request': request}).data)

        serializer = EmployerProfileUpdateSerializer(
            employer, data=request.data, partial=(request.method == 'PATCH')
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(EmployerSerializer(employer, context={'request': request}).data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard(self, request):
        base_url = request.build_absolute_uri('/')

        profile_url = base_url.rstrip('/') + drf_reverse('employer-profile-dashboard', request=request)
        profile_response = requests.get(profile_url, headers={'Authorization': request.headers.get('Authorization', '')})

        if profile_response.status_code != 200:
            return Response({'error': 'Could not fetch profile data'}, status=profile_response.status_code)

        response_data = profile_response.json()

        endpoints = [
            ('job_applications', 'employer-job-applications'),
            ('project_applications', 'employer-project-applications'),
        ]

        for key, url_name in endpoints:
            url = base_url.rstrip('/') + drf_reverse(url_name, request=request)
            resp = requests.get(url, headers={'Authorization': request.headers.get('Authorization', '')})
            if resp.status_code == 200:
                response_data.update(resp.json())

        return Response(response_data)

    @action(detail=False, methods=['post'], url_path='profile/complete/(?P<section>[^/.]+)', permission_classes=[permissions.IsAuthenticated])
    def complete_profile_section(self, request, section=None):
        employer = get_object_or_404(Employer, user=request.user)

        section_map = {
            'basic_info': 'basic_info_completed',
            'company_info': 'company_info_completed',
        }
        if section not in section_map:
            return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)

        setattr(employer, section_map[section], True)
        employer.save(update_fields=[section_map[section]])

        if employer.is_profile_complete:
            request.user.profile_completed = True
            request.user.save(update_fields=['profile_completed'])

        return Response({
            'message': f'{section.replace("_", " ").title()} section marked as complete',
            'profile_completed': employer.is_profile_complete
        })

    @action(detail=False, methods=['delete'], permission_classes=[permissions.IsAuthenticated])
    def delete_profile(self, request):
        """
        Sirf Employer profile delete karta hai (user account safe rahega)
        """
        try:
            employer = request.user.employer_profile

            # Related data delete
            if hasattr(employer, 'preferences'):
                employer.preferences.delete()
            if hasattr(employer, 'compliance'):
                employer.compliance.delete()

            CandidateAction.objects.filter(employer=employer).delete()

            # Employer profile delete
            employer.delete()

            # User se employer-related flags clear
            request.user.profile_completed = False
            if hasattr(request.user, 'user_type'):
                request.user.user_type = None  # ya 'candidate' ya default
            request.user.save(update_fields=['profile_completed', 'user_type'])

            return Response({
                'message': 'Employer profile successfully deleted. You can now switch to candidate role if needed.'
            }, status=status.HTTP_200_OK)

        except Employer.DoesNotExist:
            return Response({'error': 'Employer profile not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            exception_logger.exception("Error deleting employer profile for user %s", request.user.id)
            return Response({'error': 'Failed to delete profile'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['delete'], url_path='delete-account', permission_classes=[permissions.IsAuthenticated])
    def delete_account(self, request):
        """
        Pura account delete (soft delete - recommended for safety & compliance)
        User login nahi kar payega baad mein
        """
        user = request.user

        try:
            # Employer profile aur related data delete
            if hasattr(user, 'employer_profile'):
                employer = user.employer_profile
                if hasattr(employer, 'preferences'):
                    employer.preferences.delete()
                if hasattr(employer, 'compliance'):
                    employer.compliance.delete()
                CandidateAction.objects.filter(employer=employer).delete()
                employer.delete()

            # Soft delete user (industry standard)
            user.is_active = False
            user.email = f"deleted_{user.id}_{timezone.now().timestamp()}@deleted.com"
            user.username = f"deleted_user_{user.id}"
            user.first_name = "Deleted"
            user.last_name = "User"
            user.set_unusable_password()
            user.save()

            return Response({
                'message': 'Your account has been permanently deleted. You have been logged out.'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            exception_logger.exception("Critical error deleting account for user %s", user.id)
            return Response({'error': 'Failed to delete account'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EmployerPreferenceView(generics.RetrieveUpdateAPIView):
    serializer_class = EmployerPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        pref, _ = EmployerPreference.objects.get_or_create(employer=self.request.user.employer_profile)
        return pref


class EmployerComplianceView(generics.RetrieveUpdateAPIView):
    serializer_class = EmployerComplianceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        comp, _ = EmployerCompliance.objects.get_or_create(employer=self.request.user.employer_profile)
        return comp


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])  # Optional: agar sirf logged in employer access kare
def get_flitpass_data(request, company_id):
    try:
        ml_api_url = f"{settings.FLIT_AI_URL}/flitpass/{company_id}"
        response = requests.get(ml_api_url, timeout=10)
        response.raise_for_status()
        return Response(response.json())
    except requests.exceptions.RequestException as e:
        exception_logger.exception("ML API call failed for company_id=%s", company_id)
        return Response(
            {"error": "Failed to fetch data from ML API"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )