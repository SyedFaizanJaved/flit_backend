import logging
import requests
import time
import re  
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from applications.models import ProjectApplication
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, permissions, mixins
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import action, authentication_classes, permission_classes
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from accounts.permissions import IsEmployer
from utils.pagination import CustomPagination
from utils.email_service import send_shortlist_notification, send_rejection_notification
from utils.ml_client import delete_from_ml_index
from rest_framework_simplejwt.authentication import JWTAuthentication
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

class ProjectMLMixin:
    """
    Mixin to handle ML API integrations for Projects
    """
    def _get_ml_payload(self, project):
        return {
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

    def _call_ml_create_api(self, project):
        return self._call_ml_api(f"{settings.FLIT_AI_URL}/create_projects/{project.id}", project, is_create=True)

    def _call_ml_update_api(self, project):
        # PATCH first, create on 404. Closing a posting now removes it from the ML
        # index, so an employer who reopens or edits a closed one would otherwise be
        # PATCHing a record that no longer exists -- it would never be re-indexed and
        # could never be recommended again. Same fallback as the candidate sync in
        # candidates/views.py.
        return self._call_ml_api(
            f"{settings.FLIT_AI_URL}/update_project_data/{project.id}",
            project,
            is_create=False,
            create_url=f"{settings.FLIT_AI_URL}/create_projects/{project.id}",
        )

    def _call_ml_metadata_api(self, project):
        """
        New API for updating project metadata, specifically used when status changes (e.g., auto-closed)
        """
        return self._call_ml_api(f"{settings.FLIT_AI_URL}/update_project_metadata/{project.id}", project, is_create=False)

    def _call_ml_delete_api(self, project):
        """Drop the project from the ML vector store. Returns (ok, error).

        See the matching note on JobMLMixin._call_ml_delete_api.
        """
        return delete_from_ml_index(f"/delete_projects/{project.id}")

    def _call_ml_api(self, url, project, is_create=True, create_url=None):
        payload = self._get_ml_payload(project)
        method = requests.post if is_create else requests.patch
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                ml_response = method(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                break
            except requests.exceptions.Timeout:
                if attempt == max_retries:
                    return False, None, [], "ML API timed out after retries"
                time.sleep(1)
            except requests.exceptions.RequestException as e:
                return False, None, [], f"ML API request failed: {str(e)}"

        if ml_response.status_code == 404 and create_url:
            # Not in the index (deleted on close). Put it back rather than failing.
            return self._call_ml_api(create_url, project, is_create=True)

        if ml_response.status_code in (200, 201):
            try:
                data = ml_response.json()
                summary = data.get('project_profile_summary')
                tags = data.get('project_tags', [])

                updates = {}
                if summary is not None:
                    updates['project_profile_summary'] = summary
                if tags:
                    updates['project_tags'] = tags
                
                if updates:
                    for field, value in updates.items():
                        setattr(project, field, value)
                    project.save(update_fields=updates.keys())

                return True, summary, tags, None
            except Exception as e:
                exception_logger.exception("Error processing ML response")
                return False, None, [], "Invalid ML response format"
        else:
            return False, None, [], f"ML API error: {ml_response.status_code}"

class PublicProjectViewSet(ProjectMLMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectListSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    authentication_classes = [JWTAuthentication]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'paymentType', 'company']
    search_fields = ['title']
    ordering_fields = ['created_at', 'budget_min', 'budget_max']
    ordering = ['-created_at']
    pagination_class = CustomPagination

    def get_queryset(self):
        # Auto-close moved to `manage.py close_expired_projects` (Bug #23), so this
        # filters expired rows out without mutating them. The rule itself lives in
        # ProjectQuerySet.open() so this, the apply guard, the serializers and the
        # command can't drift apart.
        # ponytail: select_related('company') — the jobs equivalent had it, this
        # didn't, so company_name/company_logo cost a query per row.
        queryset = Project.objects.open().select_related('company')

        # ponytail: ProjectListSerializer asked the DB per row (is_applied,
        # application_count, application_details). These annotations answer them up
        # front, so the query count stops scaling with page size.
        queryset = queryset.annotate(
            active_application_count=Count(
                'applications', filter=Q(applications__is_withdrawn=False)
            )
        ).prefetch_related(
            # ponytail: get_skills read required_skills per row. order_by keeps the
            # output stable; ProjectSkill has no Meta.ordering.
            Prefetch('required_skills', queryset=ProjectSkill.objects.order_by('id'))
        )
        user = self.request.user
        if user.is_authenticated and hasattr(user, 'candidate_profile'):
            candidate = user.candidate_profile
            mine = ProjectApplication.objects.filter(
                candidate=candidate, is_withdrawn=False
            )
            queryset = queryset.annotate(
                is_applied_annotated=Exists(mine.filter(project=OuterRef('pk')))
            ).prefetch_related(
                Prefetch(
                    'applications',
                    queryset=mine.select_related('candidate__user'),
                    to_attr='my_applications',
                )
            )

        # Apply search with partial word matching
        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    queryset = queryset.filter(title__icontains=term)

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

class ProjectViewSet(ProjectMLMixin, viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'paymentType', 'company']
    search_fields = ['title']
    ordering = ['-created_at']
    pagination_class = CustomPagination

    def get_queryset(self):
        # NOTE: Auto-closing of past-deadline projects used to live here as a
        # side effect of every read. That made reads racy and caused Bug #23
        # (Draft -> Active save was reverted to Closed on the next read because
        # the deadline was already in the past). The auto-close logic now lives
        # in `python manage.py close_expired_projects`; schedule it via cron or
        # Celery beat. Active-with-past-deadline updates are now blocked by
        # `ProjectUpdateSerializer.validate()`.
        queryset = super().get_queryset()

        # For retrieve action: candidates should be able to view any project
        # they've applied to, even if it's closed/expired.
        if self.action == 'retrieve':
            # Pure employers (no candidate profile) can only see their company's projects
            if hasattr(self.request.user, 'employer_profile') and not hasattr(self.request.user, 'candidate_profile'):
                queryset = queryset.filter(company=self.request.user.employer_profile.company)
            # Candidates (including dual-role users) can retrieve any project
            return queryset.distinct()

        # Restriction: Employers can only manage/see their own items,
        # but dual-role users (who are also candidates) should be able to browse all active ones.
        if hasattr(self.request.user, 'employer_profile'):
            if not hasattr(self.request.user, 'candidate_profile'):
                queryset = queryset.filter(company=self.request.user.employer_profile.company)
            else:
                # Dual role: allow viewing any active project or their own company's projects
                queryset = queryset.filter(
                    Q(company=self.request.user.employer_profile.company) | Q(status='active')
                )

        search = self.request.query_params.get('search', None)
        if search:
            search_terms = search.strip().split()
            for term in search_terms:
                if term:
                    queryset = queryset.filter(title__icontains=term)

        # Browsing lists show only open projects. `retrieve` deliberately stays
        # unfiltered above so a candidate can still view a posting they applied to
        # after its deadline.
        if self.action == 'list':
            queryset = queryset.filter(pk__in=Project.objects.open().values('pk'))
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

        # Get company for scoping per-tab counts
        company = None
        if hasattr(request.user, 'employer_profile'):
            company = request.user.employer_profile.company

        # Per-tab counts must be scoped to the Project model only — never mixed
        # with Job counts (Bug #22).
        total_projects_count = 0
        active_projects_count = 0
        if company:
            company_projects = Project.objects.filter(company=company)
            total_projects_count = company_projects.count()
            active_projects_count = company_projects.filter(status='active').count()

        page = self.paginate_queryset(queryset)
        serializer = ProjectListSerializer(
            page if page is not None else queryset,
            many=True,
            context={'request': request}
        )

        if page is not None:
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                'count': paginated_response.data['count'],
                'next': paginated_response.data['next'],
                'previous': paginated_response.data['previous'],
                'total_pages': paginated_response.data['total_pages'],
                'current_page': paginated_response.data['current_page'],
                'total_projects': total_projects_count,
                'active_projects': active_projects_count,
                'results': paginated_response.data['results']
            })

        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'total_projects': total_projects_count,
            'active_projects': active_projects_count,
            'results': serializer.data
        })

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code != status.HTTP_201_CREATED:
            return response

        project = Project.objects.get(id=response.data['id'])
        ml_success, project_profile_summary, project_tags, ml_error = self._call_ml_create_api(project)

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
        if response.status_code != status.HTTP_200_OK:
            return response

        project = self.get_object()
        ml_success, project_profile_summary, project_tags, ml_error = self._call_ml_update_api(project)

        updated_data = ProjectSerializer(project).data
        response.data = {
            'message': 'Project updated successfully',
            'ml_success': ml_success,
            'project_profile_summary': project_profile_summary,
            'project_tags': project_tags,
            'data': updated_data
        }
        if ml_error:
            response.data['ml_error'] = ml_error
            response.data['message'] += f' (ML processing failed: {ml_error})'

        return response
        
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

        # Keep the ML index in step with the employer's choice. This action used to call
        # ML not at all, so manually closed postings stayed indexed and went on being
        # recommended -- the same staleness the deadline sweep fixes, through a different
        # door. Re-index only when the posting is genuinely open: reactivating one whose
        # deadline has already passed must not put it back in front of candidates.
        # Best-effort; candidate reads filter on ProjectQuerySet.open() either way.
        try:
            if project.status == 'active' and not project.is_expired:
                self._call_ml_update_api(project)
            else:
                self._call_ml_delete_api(project)
        except Exception:
            logger.exception("ML index sync failed after status change for project %s", project.id)
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
        
        # Send email notification to candidate
        try:
            send_shortlist_notification(
                candidate=application.candidate,
                job_or_project_title=project.title,
                application_type='project',
                company_name=project.company.company_name if project.company else None
            )
        except Exception as e:
            logger.error(f"Failed to send shortlist email notification: {str(e)}")
            # Don't fail the request if email fails
            
        # Notify Candidate via WebSocket
        if application.candidate and application.candidate.user:
            from utils.broadcaster import broadcast_count_update
            from candidates.utils import get_candidate_unread_counts
            broadcast_count_update(
                user_id=application.candidate.user.id,
                count_type="applications",
                unread_count=get_candidate_unread_counts(application.candidate.user)
            )
        
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
        
        # Send email notification to candidate
        try:
            send_rejection_notification(
                candidate=application.candidate,
                job_or_project_title=project.title,
                application_type='project',
                rejection_reason=application.rejection_reason,
                company_name=project.company.company_name if project.company else None
            )
        except Exception as e:
            logger.error(f"Failed to send rejection email notification: {str(e)}")
            # Don't fail the request if email fails
            
        # Notify Candidate via WebSocket
        if application.candidate and application.candidate.user:
            from utils.broadcaster import broadcast_count_update
            from candidates.utils import get_candidate_unread_counts
            broadcast_count_update(
                user_id=application.candidate.user.id,
                count_type="applications",
                unread_count=get_candidate_unread_counts(application.candidate.user)
            )
        
        return Response({'message': 'Application rejected successfully', 'application': {'id': application.id, 'candidate_name': application.candidate.full_name, 'status': application.status, 'is_rejected': application.is_rejected}}, status=status.HTTP_200_OK)