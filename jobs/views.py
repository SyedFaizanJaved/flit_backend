from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Job, JobSkill, JobLanguage
from .serializers import (
    JobSerializer, JobListSerializer, JobCreateSerializer, JobUpdateSerializer,
    JobSkillSerializer, JobLanguageSerializer
)


class JobListView(generics.ListCreateAPIView):
    """
    Job list and create view
    """
    queryset = Job.objects.filter(status='active')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title', 'description', 'company__company_name']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return JobCreateSerializer
        return JobListSerializer


class JobDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Job detail view
    """
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return JobUpdateSerializer
        return JobSerializer


class MyJobsView(generics.ListAPIView):
    """
    User's posted jobs view
    """
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Job.objects.filter(employer=self.request.user)


class JobSkillView(generics.ListCreateAPIView):
    """
    Job skills view
    """
    serializer_class = JobSkillSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        job_id = self.kwargs['job_id']
        return JobSkill.objects.filter(job_id=job_id)
    
    def perform_create(self, serializer):
        job_id = self.kwargs['job_id']
        job = Job.objects.get(id=job_id, employer=self.request.user)
        serializer.save(job=job)


class JobLanguageView(generics.ListCreateAPIView):
    """
    Job languages view
    """
    serializer_class = JobLanguageSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        job_id = self.kwargs['job_id']
        return JobLanguage.objects.filter(job_id=job_id)
    
    def perform_create(self, serializer):
        job_id = self.kwargs['job_id']
        job = Job.objects.get(id=job_id, employer=self.request.user)
        serializer.save(job=job)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def job_applications(request, job_id):
    """
    Get job applications
    """
    try:
        job = Job.objects.get(id=job_id, employer=request.user)
        applications = job.applications.all()
        
        data = {
            'job': JobSerializer(job).data,
            'applications': [
                {
                    'id': app.id,
                    'candidate_name': app.candidate.full_name,
                    'status': app.status,
                    'overall_match_score': app.overall_match_score,
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected
                }
                for app in applications
            ],
            'total_applications': applications.count(),
            'shortlisted_count': applications.filter(is_shortlisted=True).count(),
            'rejected_count': applications.filter(is_rejected=True).count(),
        }
        
        return Response(data, status=status.HTTP_200_OK)
    except Job.DoesNotExist:
        return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_job_status(request, job_id):
    """
    Update job status
    """
    try:
        job = Job.objects.get(id=job_id, employer=request.user)
        new_status = request.data.get('status')
        
        if new_status not in ['draft', 'active', 'paused', 'closed', 'filled']:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        
        job.status = new_status
        job.save()
        
        return Response({
            'message': 'Job status updated successfully',
            'job': JobSerializer(job).data
        }, status=status.HTTP_200_OK)
    except Job.DoesNotExist:
        return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def shortlist_application(request, job_id, application_id):
    """
    Shortlist a job application
    """
    try:
        job = Job.objects.get(id=job_id, employer=request.user)
        application = job.applications.get(id=application_id)
        
        application.is_shortlisted = True
        application.is_rejected = False
        application.status = 'shortlisted'
        application.save()
        
        return Response({
            'message': 'Application shortlisted successfully',
            'application': {
                'id': application.id,
                'candidate_name': application.candidate.full_name,
                'status': application.status,
                'is_shortlisted': application.is_shortlisted
            }
        }, status=status.HTTP_200_OK)
    except Job.DoesNotExist:
        return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def reject_application(request, job_id, application_id):
    """
    Reject a job application
    """
    try:
        job = Job.objects.get(id=job_id, employer=request.user)
        application = job.applications.get(id=application_id)
        
        application.is_rejected = True
        application.is_shortlisted = False
        application.status = 'rejected'
        application.rejection_reason = request.data.get('rejection_reason', '')
        application.save()
        
        return Response({
            'message': 'Application rejected successfully',
            'application': {
                'id': application.id,
                'candidate_name': application.candidate.full_name,
                'status': application.status,
                'is_rejected': application.is_rejected
            }
        }, status=status.HTTP_200_OK)
    except Job.DoesNotExist:
        return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
