import logging
import requests
import time
import re  
from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, permissions, mixins
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import action, authentication_classes, permission_classes
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from accounts.permissions import IsEmployer
from utils.pagination import CustomPagination
from .models import Project, ProjectSkill, ProjectMilestone
from .serializers import (
    ProjectSerializer, ProjectListSerializer, ProjectCreateSerializer, ProjectUpdateSerializer,
    ProjectSkillSerializer, ProjectMilestoneSerializer
)

exception_logger = logging.getLogger("exceptions")
logger = logging.getLogger(__name__)

class PublicAuthentication(BaseAuthentication):
    def authenticate(self, request):
        return None

@authentication_classes([PublicAuthentication])
class PublicProjectViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectListSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = [PublicAuthentication]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'paymentType', 'company']
    search_fields = ['title']
    ordering_fields = ['created_at', 'budget_min', 'budget_max']
    ordering = ['-created_at']
    pagination_class = CustomPagination

    def get_queryset(self):
        # Base queryset with active status
        queryset = super().get_queryset().filter(status='active')

        # Apply search with whole word matching
        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    escaped_term = re.escape(term)
                    # Match whole word, including at start or end of title
                    pattern = fr'(?:^|\s){escaped_term}(?:\s|$)'
                    queryset = queryset.filter(title__iregex=pattern)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'results': serializer.data
        })

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'paymentType', 'company']
    search_fields = ['title']
    ordering = ['-created_at']
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = super().get_queryset()

        if hasattr(self.request.user, 'employer_profile'):
            queryset = queryset.filter(company=self.request.user.employer_profile.company)

        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    escaped_term = re.escape(term)
                    queryset = queryset.filter(title__iregex=fr'\b{escaped_term}\b')

        if self.action in ['list', 'my_projects']:
            queryset = queryset.filter(status='active')
            queryset = queryset.prefetch_related('applications__candidate')

        return queryset.distinct()

    def get_serializer_class(self):
        if self.action in ['list', 'my_projects']:
            return ProjectListSerializer
        if self.action == 'create':
            return ProjectCreateSerializer
        if self.action in ['update', 'partial_update']:
            return ProjectUpdateSerializer
        return ProjectSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        context = self.get_serializer_context()
        context['request'] = request
        serializer = self.get_serializer(instance, context=context)
        
        if hasattr(request.user, 'candidate_profile'):
            candidate = request.user.candidate_profile
            from applications.models import ProjectApplication
            ProjectApplication.objects.filter(
                project=instance,
                candidate=candidate,
                is_withdrawn=False
            ).exists()  
        return Response(serializer.data)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'update_status',
                            'shortlist_application', 'reject_application', 'skills', 'milestones']:
            return [permissions.IsAuthenticated(), IsEmployer()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='my-projects')
    def my_projects(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        serializer = ProjectListSerializer(
            page if page is not None else queryset,
            many=True,
            context={'request': request}
        )
        
        if page is not None:
            return self.get_paginated_response(serializer.data)
        
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'results': serializer.data
        })

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code != status.HTTP_201_CREATED:
            return response

        ml_success = False
        project_profile_summary = None
        project_tags = []
        ml_error = None

        project_id = response.data.get('id')
        project = None

        if not project_id:
            ml_error = 'Project ID missing in response; cannot trigger ML sync'
            logger.error(ml_error)
        else:
            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                exception_logger.error(f"Project.DoesNotExist: Project with ID {project_id} not found for ML sync")
                ml_error = f'Project with ID {project_id} not found for ML sync'
                logger.error(ml_error)

        if project:
            ml_api_url = f"{settings.FLIT_AI_URL}/create_projects/{project.id}"
            ml_payload = {
                "title": project.title,
                "description": project.description,
                "company_name": project.company.company_name if project.company else "",
                "category": project.category,
                "skills": project.skills if hasattr(project, 'skills') else [],
                "paymentType": project.paymentType,
                "paymentAmount": project.paymentAmount,
                "estimatedHours": project.estimatedHours,
                "deadline": project.deadline.isoformat() if project.deadline else None,
                "status": project.status
            }

            try:
                logger.info(f"Calling Project create ML API for project {project.id}")
                ml_response = requests.post(
                    ml_api_url,
                    json=ml_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                logger.info(f"Project create ML API response status: {ml_response.status_code}")
                
            except requests.exceptions.Timeout:
                exception_logger.error("Project create ML API timed out")
                ml_error = "Project create ML API timed out"
                logger.error(ml_error)
                raise
            except requests.exceptions.RequestException as exc:
                exception_logger.exception("Project create ML API request failed")
                ml_error = f"Project create ML API request failed: {str(exc)}"
                logger.error(ml_error, exc_info=True)
                raise

            if ml_response is not None:
                if ml_response.status_code in (200, 201):
                    try:
                        ml_data = ml_response.json()
                        project_profile_summary = ml_data.get('project_profile_summary')
                        project_tags = ml_data.get('project_tags', [])

                        updates = {}
                        if project_profile_summary is not None:
                            updates['project_profile_summary'] = project_profile_summary
                        if project_tags:
                            updates['project_tags'] = project_tags

                        if updates:
                            for field, value in updates.items():
                                setattr(project, field, value)
                            project.save(update_fields=list(updates.keys()))

                        ml_success = True
                    except ValueError:
                        exception_logger.error("Invalid JSON response from Project create ML API")
                        ml_error = "Invalid JSON response from Project create ML API"
                        logger.error(ml_error)
                    except Exception as exc:
                        exception_logger.exception("Error processing Project create ML API response")
                        ml_error = f"Error processing Project create ML API response: {str(exc)}"
                        logger.error(ml_error, exc_info=True)
                else:
                    ml_error = f"Project create ML API returned status code {ml_response.status_code}"
                    logger.error(f"{ml_error}. Response content: {ml_response.text}")

        response.data = {
            'message': 'Project created successfully',
            'ml_success': ml_success,
            'project_profile_summary': project_profile_summary,
            'project_tags': project_tags,
            'data': response.data
        }

        if ml_error:
            response.data['ml_error'] = ml_error

        return response
        
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        
        if response.status_code == status.HTTP_200_OK:
            try:
                project = self.get_object()
                
                ml_api_url = f"{settings.FLIT_AI_URL}/update_project_data/{project.id}"
                ml_payload = {
                    "title": project.title,
                    "description": project.description,
                    "company_name": project.company.company_name if project.company else "",
                    "category": project.category,
                    "skills": project.skills if hasattr(project, 'skills') else [],
                    "paymentType": project.paymentType,
                    "paymentAmount": project.paymentAmount,
                    "estimatedHours": project.estimatedHours,
                    "deadline": project.deadline.isoformat() if project.deadline else None,
                    "status": project.status
                }
                
                max_retries = 2
                timeout_seconds = 30
                
                for attempt in range(max_retries + 1):
                    try:
                        ml_response = requests.patch(
                            ml_api_url,
                            json=ml_payload,
                            headers={"Content-Type": "application/json"},
                            timeout=timeout_seconds
                        )
                        break
                    except requests.exceptions.Timeout:
                        if attempt == max_retries:
                            exception_logger.error("Project ML API timed out after retries")
                            raise
                        time.sleep(1)
                    except requests.exceptions.RequestException as e:
                        exception_logger.exception("Project ML API request failed")
                        raise
                
                if ml_response.status_code == 200:
                    try:
                        ml_data = ml_response.json()
                        if 'project_profile_summary' in ml_data:
                            project.project_profile_summary = ml_data['project_profile_summary']
                        if 'project_tags' in ml_data:
                            project.project_tags = ml_data['project_tags']
                        project.save()
                        
                        response.data = {
                            'message': 'Project updated successfully',
                            'ml_success': True,
                            'project_profile_summary': ml_data.get('project_profile_summary', ''),
                            'project_tags': ml_data.get('project_tags', []),
                            'data': response.data
                        }
                    except Exception as e:
                        exception_logger.exception("Error processing Project ML API response")
                        response.data = {
                            'message': 'Project updated successfully (ML processing failed - invalid response format)',
                            'ml_success': False,
                            'project_profile_summary': None,
                            'project_tags': [],
                            'data': response.data
                        }
                else:
                    response.data = {
                        'message': f'Project updated successfully (ML processing failed - HTTP {ml_response.status_code})',
                        'ml_success': False,
                        'project_profile_summary': None,
                        'project_tags': [],
                        'data': response.data
                    }
                    
            except Exception as e:
                exception_logger.exception("Error calling Project ML API")
                response.data = {
                    'message': f'Project updated successfully (ML processing failed - {str(e)})',
                    'ml_success': False,
                    'project_profile_summary': None,
                    'project_tags': [],
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

        # ==================== APPLICATIONS LIST ====================
    @action(detail=True, methods=['get'], url_path='applications')
    def applications(self, request, pk=None):
        try:
            project = Project.objects.get(
                id=pk,
                company=request.user.employer_profile.company
            )
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or you do not have access'},
                status=status.HTTP_404_NOT_FOUND
            )

        applications = project.applications.all()  # assuming related_name='applications'

        data = {
            'project': ProjectSerializer(project, context={'request': request}).data,
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
            exception_logger.error("Project.DoesNotExist: Project not found")
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
            exception_logger.error("Project.DoesNotExist: Project not found")
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            exception_logger.exception("Application not found")
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
            exception_logger.error("Project.DoesNotExist: Project not found")
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            exception_logger.exception("Application not found")
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        application.is_rejected = True
        application.is_shortlisted = False
        application.status = 'rejected'
        application.rejection_reason = request.data.get('rejection_reason', '')
        application.save()
        return Response({'message': 'Application rejected successfully', 'application': {'id': application.id, 'candidate_name': application.candidate.full_name, 'status': application.status, 'is_rejected': application.is_rejected}}, status=status.HTTP_200_OK)