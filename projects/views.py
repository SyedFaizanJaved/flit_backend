from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Project, ProjectSkill, ProjectMilestone
from .serializers import (
    ProjectSerializer, ProjectListSerializer, ProjectCreateSerializer, ProjectUpdateSerializer,
    ProjectSkillSerializer, ProjectMilestoneSerializer
)


class ProjectListView(generics.ListCreateAPIView):
    """
    Project list and create view
    """
    queryset = Project.objects.filter(status='active')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'complexity', 'paymentType', 'work_style', 'company']
    search_fields = ['title', 'description', 'company__company_name']
    ordering_fields = ['created_at', 'budget_min', 'budget_max']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProjectCreateSerializer
        return ProjectListSerializer


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Project detail view
    """
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ProjectUpdateSerializer
        return ProjectSerializer


class MyProjectsView(generics.ListAPIView):
    """
    User's posted projects view
    """
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Project.objects.filter(employer=self.request.user)


class ProjectSkillView(generics.ListCreateAPIView):
    """
    Project skills view
    """
    serializer_class = ProjectSkillSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        project_id = self.kwargs['project_id']
        return ProjectSkill.objects.filter(project_id=project_id)
    
    def perform_create(self, serializer):
        project_id = self.kwargs['project_id']
        project = Project.objects.get(id=project_id, employer=self.request.user)
        serializer.save(project=project)


class ProjectMilestoneView(generics.ListCreateAPIView):
    """
    Project milestones view
    """
    serializer_class = ProjectMilestoneSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        project_id = self.kwargs['project_id']
        return ProjectMilestone.objects.filter(project_id=project_id)
    
    def perform_create(self, serializer):
        project_id = self.kwargs['project_id']
        project = Project.objects.get(id=project_id, employer=self.request.user)
        serializer.save(project=project)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def project_applications(request, project_id):
    """
    Get project applications
    """
    try:
        project = Project.objects.get(id=project_id, employer=request.user)
        applications = project.applications.all()
        
        data = {
            'project': ProjectSerializer(project).data,
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
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_project_status(request, project_id):
    """
    Update project status
    """
    try:
        project = Project.objects.get(id=project_id, employer=request.user)
        new_status = request.data.get('status')
        
        if new_status not in ['draft', 'active', 'paused', 'closed', 'in-progress', 'completed']:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        
        project.status = new_status
        project.save()
        
        return Response({
            'message': 'Project status updated successfully',
            'project': ProjectSerializer(project).data
        }, status=status.HTTP_200_OK)
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def shortlist_application(request, project_id, application_id):
    """
    Shortlist a project application
    """
    try:
        project = Project.objects.get(id=project_id, employer=request.user)
        application = project.applications.get(id=application_id)
        
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
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def reject_application(request, project_id, application_id):
    """
    Reject a project application
    """
    try:
        project = Project.objects.get(id=project_id, employer=request.user)
        application = project.applications.get(id=application_id)
        
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
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
