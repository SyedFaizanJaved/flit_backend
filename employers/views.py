from rest_framework import generics, status, permissions, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models
from .models import Employer, EmployerPreference, EmployerCompliance
from chat.models import ChatMessage
from .serializers import (
    EmployerSerializer, EmployerListSerializer, EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer, EmployerComplianceSerializer ,EmployerConversationSummarySerializer
)
from accounts.views import BaseRoleRegistrationView
from candidates.models import Candidate

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
        try:
            employer = request.user.employer_profile
        except Employer.DoesNotExist:
            return Response({'error': 'Employer profile not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'profile': EmployerSerializer(employer).data,
            'profile_completed': employer.is_profile_complete,
            'jobs_posted': employer.total_jobs_posted,
            'projects_posted': employer.total_projects_posted,
            'applications_received': employer.total_applications_received,
            'hires': employer.total_hires,
        }

        recent_job_applications = getattr(employer, 'received_job_applications', []).all()[:5]
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

        recent_project_applications = getattr(employer, 'received_project_applications', []).all()[:5]
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
        
class EmployerConversationListView(generics.ListAPIView):
    """
    Lists, for the authenticated employer, each candidate they have chatted with
    along with candidate id, name, title, and the last message time.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmployerConversationSummarySerializer

    def get_queryset(self):

        # Subquery to get the latest message created_at between request.user and each candidate.user
        latest_msg_subq = ChatMessage.objects.filter(
            (
                models.Q(sender=self.request.user, recipient=models.OuterRef('user')) |
                models.Q(sender=models.OuterRef('user'), recipient=self.request.user)
            )
        ).order_by('-created_at').values('created_at')[:1]

        qs = Candidate.objects.annotate(
            last_message_time=models.Subquery(latest_msg_subq)
        ).filter(
            last_message_time__isnull=False
        ).order_by('-last_message_time')

        return qs



# @api_view(['POST'])
# @permission_classes([permissions.IsAuthenticated])
# def complete_profile_section(request, section):
#     """
#     Mark a profile section as complete
#     """
#     try:
#         employer = request.user.employer_profile
#         section_fields = {
#             'basic_info': 'basic_info_completed',
#             'company_info': 'company_info_completed',
#         }
        
#         if section not in section_fields:
#             return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)
        
#         setattr(employer, section_fields[section], True)
#         employer.save()
        
#         return Response({
#             'message': f'{section} section marked as complete',
#             'is_profile_complete': employer.is_profile_complete
#         }, status=status.HTTP_200_OK)
#     except Employer.DoesNotExist:
#         return Response({'error': 'Employer profile not found'}, status=status.HTTP_404_NOT_FOUND)
