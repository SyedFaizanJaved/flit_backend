from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Candidate, WorkDNA, Reference, ReferenceRequest
from .serializers import (
    CandidateSerializer, CandidateListSerializer, WorkDNASerializer,
    ReferenceSerializer, ReferenceRequestSerializer, CandidateProfileUpdateSerializer
)
from rest_framework.exceptions import PermissionDenied



class CandidateProfileView(generics.RetrieveUpdateAPIView):
    """
    Candidate profile view
    """
    serializer_class = CandidateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        # Check user type
        if self.request.user.userType != "candidate":
            raise PermissionDenied("Only candidates can access this endpoint.")

        # Create profile if not exists
        candidate, created = Candidate.objects.get_or_create(
            user=self.request.user,
            defaults={
                'full_name': f"{self.request.user.first_name} {self.request.user.last_name}"
            }
        )
        return candidate
class CandidateListView(generics.ListAPIView):
    """
    Candidate list view (public profiles)
    """
    queryset = Candidate.objects.filter(profile_visibility="public")
    serializer_class = CandidateListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['work_style', 'is_available', 'location']
    search_fields = ['full_name', 'title', 'skills', 'superpowers']
    ordering_fields = ['created_at', 'full_name']
    ordering = ['-created_at']


class CandidateProfileUpdateView(generics.UpdateAPIView):
    """
    Candidate profile update view
    """
    serializer_class = CandidateProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        candidate, created = Candidate.objects.get_or_create(
            user=self.request.user,
            defaults={'full_name': f"{self.request.user.first_name} {self.request.user.last_name}"}
        )
        return candidate


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
            'applications_count': candidate.applications.count(),
            'job_applications_count': candidate.job_applications.count(),
            'project_applications_count': candidate.project_applications.count(),
            'references_count': candidate.references.count(),
            'reference_requests_count': candidate.reference_requests.count(),
        }
        
        # Add recent applications
        recent_applications = candidate.applications.all()[:5]
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
        
        return Response({
            'message': f'{section} section marked as complete',
            'is_profile_complete': candidate.is_profile_complete
        }, status=status.HTTP_200_OK)
    except Candidate.DoesNotExist:
        return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)
