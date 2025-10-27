from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Project, ProjectSkill, ProjectMilestone
from .serializers import (
    ProjectSerializer, ProjectListSerializer, ProjectCreateSerializer, ProjectUpdateSerializer,
    ProjectSkillSerializer, ProjectMilestoneSerializer
)
from accounts.permissions import IsEmployer

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'paymentType', 'company']
    search_fields = ['title', 'description', 'company__company_name']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list':
            return qs.filter(status='active')
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
        if self.action == 'create':
            return ProjectCreateSerializer
        if self.action in ['update', 'partial_update']:
            return ProjectUpdateSerializer
        return ProjectSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'update_status', 'shortlist_application', 'reject_application', 'skills', 'milestones']:
            return [permissions.IsAuthenticated(), IsEmployer()]
        return [permissions.IsAuthenticated()]
        
    @action(detail=False, methods=['get'], url_path='my-projects')
    def my_projects(self, request):
        projects = Project.objects.filter(employer=request.user)
        page = self.paginate_queryset(projects)
        serializer = ProjectSerializer(page or projects, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
        
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            response.data = {
                'message': 'Project created successfully',
                'data': response.data
            }
        return response
        
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            response.data = {
                'message': 'Project updated successfully',
                'data': response.data
            }
        return response
        
    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        self.perform_destroy(project)
        return Response(
            {'message': 'Project deleted successfully'}, 
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['get', 'post'], url_path='skills')
    def skills(self, request, pk=None):
        project = self.get_object()
        if request.method == 'GET':
            skills = ProjectSkill.objects.filter(project=project)
            serializer = ProjectSkillSerializer(skills, many=True)
            return Response(serializer.data)
        serializer = ProjectSkillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(project=project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], url_path='milestones')
    def milestones(self, request, pk=None):
        project = self.get_object()
        if request.method == 'GET':
            milestones = ProjectMilestone.objects.filter(project=project)
            serializer = ProjectMilestoneSerializer(milestones, many=True)
            return Response(serializer.data)
        serializer = ProjectMilestoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(project=project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='applications')
    def applications(self, request, pk=None):
        try:
            project = Project.objects.get(id=pk, employer=request.user)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
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

    @action(detail=True, methods=['post'], url_path='status')
    def update_status(self, request, pk=None):
        try:
            project = Project.objects.get(id=pk, employer=request.user)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        new_status = request.data.get('status')
        if new_status not in ['draft', 'active', 'paused', 'closed', 'in-progress', 'completed']:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        project.status = new_status
        project.save()
        return Response({'message': 'Project status updated successfully', 'project': ProjectSerializer(project).data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/shortlist')
    def shortlist_application(self, request, pk=None, application_id=None):
        try:
            project = Project.objects.get(id=pk, employer=request.user)
            application = project.applications.get(id=application_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        application.is_shortlisted = True
        application.is_rejected = False
        application.status = 'shortlisted'
        application.save()
        return Response({'message': 'Application shortlisted successfully', 'application': {'id': application.id, 'candidate_name': application.candidate.full_name, 'status': application.status, 'is_shortlisted': application.is_shortlisted}}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/reject')
    def reject_application(self, request, pk=None, application_id=None):
        try:
            project = Project.objects.get(id=pk, employer=request.user)
            application = project.applications.get(id=application_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        application.is_rejected = True
        application.is_shortlisted = False
        application.status = 'rejected'
        application.rejection_reason = request.data.get('rejection_reason', '')
        application.save()
        return Response({'message': 'Application rejected successfully', 'application': {'id': application.id, 'candidate_name': application.candidate.full_name, 'status': application.status, 'is_rejected': application.is_rejected}}, status=status.HTTP_200_OK)