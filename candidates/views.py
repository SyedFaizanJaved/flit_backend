from rest_framework import generics, status, permissions, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Candidate, WorkDNA, Reference, ReferenceRequest
from .serializers import (
    CandidateSerializer, CandidateListSerializer, WorkDNASerializer,
    ReferenceSerializer, ReferenceRequestSerializer, CandidateProfileUpdateSerializer
)
from rest_framework.exceptions import PermissionDenied
from accounts.views import BaseRoleRegistrationView


class CandidateRegistrationView(BaseRoleRegistrationView):
    """Register a new candidate user (role is forced to candidate)."""
    fixed_user_type = "candidate"


class CandidateViewSet(viewsets.ViewSet):
    """ViewSet consolidating candidate endpoints (list, profile, dashboard)."""

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        queryset = Candidate.objects.filter(profile_visibility="public")
        # Apply filters/search/order if the integration is configured on router level
        serializer = CandidateListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard(self, request):
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'profile': CandidateSerializer(candidate).data,
            'is_profile_complete': candidate.is_profile_complete,
            'applications_count': candidate.job_applications.count() + candidate.project_applications.count(),
            'job_applications_count': candidate.job_applications.count(),
            'project_applications_count': candidate.project_applications.count(),
            'references_count': candidate.references.count(),
            'reference_requests_count': candidate.reference_requests.count(),
        }

        recent_job_apps = list(candidate.job_applications.all())
        recent_project_apps = list(candidate.project_applications.all())
        recent_applications = sorted(
            recent_job_apps + recent_project_apps,
            key=lambda a: a.applied_at,
            reverse=True
        )[:5]
        data['recent_applications'] = [
            {
                'id': app.id,
                'title': app.job.title if getattr(app, 'job', None) else app.project.title,
                'company': app.company.company_name,
                'status': app.status,
                'applied_at': app.applied_at
            }
            for app in recent_applications
        ]

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        # Ensure correct role and fetch/create profile
        if request.user.userType != "candidate":
            raise PermissionDenied("Only candidates can access this endpoint.")

        candidate, _ = Candidate.objects.get_or_create(
            user=request.user,
            defaults={'full_name': f"{request.user.first_name} {request.user.last_name}"}
        )

        if request.method in ['PUT', 'PATCH']:
            serializer = CandidateProfileUpdateSerializer(candidate, data=request.data, partial=(request.method == 'PATCH'))
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(CandidateSerializer(candidate).data, status=status.HTTP_200_OK)

        return Response(CandidateSerializer(candidate).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='profile/complete/(?P<section>[^/.]+)', permission_classes=[permissions.IsAuthenticated])
    def complete_profile_section(self, request, section=None):
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

        section_fields = {
            'basic_info': 'basic_info_completed',
            'work_preferences': 'work_preferences_completed',
            'skills': 'skills_completed',
            'portfolio': 'portfolio_completed',
            'privacy': 'privacy_completed',
        }

        if section not in section_fields:
            return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)

        setattr(candidate, section_fields[section], True)
        candidate.save()

        # Ensure the user's profile_completed flag reflects the candidate profile state
        try:
            user = candidate.user
            if candidate.is_profile_complete != getattr(user, 'profile_completed', False):
                user.profile_completed = candidate.is_profile_complete
                user.save(update_fields=['profile_completed'])
        except Exception:
            # Do not block the response if user sync fails
            pass

        return Response({
            'message': f'{section} section marked as complete',
            'is_profile_complete': candidate.is_profile_complete
        }, status=status.HTTP_200_OK)


# class CandidateProfileUpdateView(generics.UpdateAPIView):
#     serializer_class = CandidateProfileUpdateSerializer
#     permission_classes = [permissions.IsAuthenticated]
#     def get_object(self):
#         candidate, created = Candidate.objects.get_or_create(
#             user=self.request.user,
#             defaults={'full_name': f"{self.request.user.first_name} {self.request.user.last_name}"}
#         )
#         return candidate


class WorkDNAView(generics.RetrieveUpdateAPIView):
    """
    Work DNA assessment view
    """
    serializer_class = WorkDNASerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        try:
            return self.request.user.candidate_profile.work_dna
        except WorkDNA.DoesNotExist:
            return None
    
    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)


class ReferenceListView(generics.ListCreateAPIView):
    """
    Reference list and create view
    """
    serializer_class = ReferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Reference.objects.filter(candidate__user=self.request.user)
    
    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)


class ReferenceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Reference detail view
    """
    serializer_class = ReferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Reference.objects.filter(candidate__user=self.request.user)


class ReferenceRequestListView(generics.ListCreateAPIView):
    """
    Reference request list and create view
    """
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)
    
    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)


class ReferenceRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Reference request detail view
    """
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def candidate_dashboard(request):
    """
    Candidate dashboard data
    """
    try:
        candidate = request.user.candidate_profile
        data = {
            'profile': CandidateSerializer(candidate).data,
            'is_profile_complete': candidate.is_profile_complete,
            'applications_count': candidate.job_applications.count() + candidate.project_applications.count(),
            'job_applications_count': candidate.job_applications.count(),
            'project_applications_count': candidate.project_applications.count(),
            'references_count': candidate.references.count(),
            'reference_requests_count': candidate.reference_requests.count(),
        }
        
        # Add recent applications
        recent_job_apps = list(candidate.job_applications.all())
        recent_project_apps = list(candidate.project_applications.all())
        recent_applications = sorted(
            recent_job_apps + recent_project_apps,
            key=lambda a: a.applied_at,
            reverse=True
        )[:5]
        data['recent_applications'] = [
            {
                'id': app.id,
                'title': app.job.title if app.job else app.project.title,
                'company': app.company.company_name,
                'status': app.status,
                'applied_at': app.applied_at
            }
            for app in recent_applications
        ]
        
        return Response(data, status=status.HTTP_200_OK)
    except Candidate.DoesNotExist:
        return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def complete_profile_section(request, section):
    """
    Mark a profile section as complete
    """
    try:
        candidate = request.user.candidate_profile
        section_fields = {
            'basic_info': 'basic_info_completed',
            'work_preferences': 'work_preferences_completed',
            'skills': 'skills_completed',
            'portfolio': 'portfolio_completed',
            'privacy': 'privacy_completed',
        }
        
        if section not in section_fields:
            return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)
        
        setattr(candidate, section_fields[section], True)
        candidate.save()
        # Sync to user's profile_completed flag as well
        try:
            user = candidate.user
            if candidate.is_profile_complete != getattr(user, 'profile_completed', False):
                user.profile_completed = candidate.is_profile_complete
                user.save(update_fields=['profile_completed'])
        except Exception:
            pass

        return Response({
            'message': f'{section} section marked as complete',
            'is_profile_complete': candidate.is_profile_complete
        }, status=status.HTTP_200_OK)
    except Candidate.DoesNotExist:
        return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)
