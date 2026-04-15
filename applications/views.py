from rest_framework import viewsets, mixins, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q, Count
from .models import JobApplication, ProjectApplication
from .serializers import (
    JobApplicationSerializer,
    ProjectApplicationSerializer,
    JobApplicationListSerializer,
    ProjectApplicationListSerializer,
)
from jobs.models import Job
from django.core.cache import cache
from projects.models import Project
import logging
from utils.pagination import CustomPagination

from employers.utils import get_employer_unread_counts
logger = logging.getLogger("exceptions")

class CombinedApplicationsView(generics.ListAPIView):
    """
    Combined view for job and project applications with pagination
    """
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        from applications.models import JobApplication, ProjectApplication
        
        # Get query parameters
        company_id = self.request.query_params.get('company_id')
        job_id = self.request.query_params.get('job_id')
        project_id = self.request.query_params.get('project_id')
        
        # Base querysets with select_related/prefetch_related for performance
        job_apps = JobApplication.objects.select_related('job', 'candidate__user')
        project_apps = ProjectApplication.objects.select_related('project', 'candidate__user')
        
        # Filter by specific Job or Project
        if job_id:
            job_apps = job_apps.filter(job_id=job_id)
            project_apps = project_apps.none()  # Clear project apps if filtering specifically for a job
        elif project_id:
            project_apps = project_apps.filter(project_id=project_id)
            job_apps = job_apps.none()  # Clear job apps if filtering specifically for a project

        # Apply company filter if company_id is provided
        if company_id:
            job_apps = job_apps.filter(job__company_id=company_id)
            project_apps = project_apps.filter(project__company_id=company_id)
        
        # Apply search filter if search is provided
        search_query = self.request.query_params.get('search')
        if search_query:
            # Match if it starts the title/name OR if it's the start of a word (preceded by space)
            job_apps = job_apps.filter(
                Q(job__title__istartswith=search_query) | 
                Q(job__title__icontains=' ' + search_query) |
                Q(candidate__full_name__istartswith=search_query) |
                Q(candidate__full_name__icontains=' ' + search_query)
            )
            project_apps = project_apps.filter(
                Q(project__title__istartswith=search_query) | 
                Q(project__title__icontains=' ' + search_query) |
                Q(candidate__full_name__istartswith=search_query) |
                Q(candidate__full_name__icontains=' ' + search_query)
            )
        
        # Filter by user role
        user_role = getattr(getattr(self.request.user, 'role', None), 'name', None)
        if user_role == "candidate":
            job_apps = job_apps.filter(candidate__user=self.request.user)
            project_apps = project_apps.filter(candidate__user=self.request.user)
        elif user_role == "employer":
            job_apps = job_apps.filter(employer=self.request.user)
            project_apps = project_apps.filter(employer=self.request.user)
        else:
            return []
        
        # Convert to list of dicts for combined sorting
        combined = []
        
        # Add job applications
        for app in job_apps:
            app_data = JobApplicationListSerializer(app, context={'request': self.request}).data
            combined.append({
                'id': app.id,
                'type': 'job',
                'title': getattr(app.job, 'title', 'No Job'),
                'status': app.status,
                'applied_at': app.applied_at,
                'candidate_id': app.candidate.id,  # Add candidate_id
                'application': app_data
            })
            
        # Add project applications
        for app in project_apps:
            app_data = ProjectApplicationListSerializer(app, context={'request': self.request}).data
            combined.append({
                'id': app.id,
                'type': 'project',
                'title': getattr(app.project, 'title', 'No Project'),
                'status': app.status,
                'applied_at': app.applied_at,
                'candidate_id': app.candidate.id,  # Add candidate_id
                'application': app_data
            })
        
        # Sort by applied_at in descending order (newest first)
        combined.sort(key=lambda x: x['applied_at'], reverse=True)
        return combined
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            unread_count = 0
            
            # Handle unread count for employer
            user_role = getattr(getattr(request.user, 'role', None), 'name', None)
            if user_role == "employer":
                company_id = self.request.query_params.get('company_id')
                job_id = self.request.query_params.get('job_id')
                project_id = self.request.query_params.get('project_id')
                
                # IMPORTANT: Count EXACTLY like the dashboard does
                all_unread_jobs = JobApplication.objects.filter(employer=request.user, is_read_by_employer=False)
                all_unread_projects = ProjectApplication.objects.filter(employer=request.user, is_read_by_employer=False)
                
                if job_id:
                    # Mark only this job's applications as read
                    jobs_to_mark = all_unread_jobs.filter(job_id=job_id)
                    unread_count = jobs_to_mark.count()
                    if unread_count > 0:
                        jobs_to_mark.update(is_read_by_employer=True)
                elif project_id:
                    # Mark only this project's applications as read
                    projects_to_mark = all_unread_projects.filter(project_id=project_id)
                    unread_count = projects_to_mark.count()
                    if unread_count > 0:
                        projects_to_mark.update(is_read_by_employer=True)
                elif company_id:
                    # Filter for specific company if ID is provided
                    jobs_to_mark = all_unread_jobs.filter(job__company_id=company_id)
                    projects_to_mark = all_unread_projects.filter(project__company_id=company_id)
                    unread_count = jobs_to_mark.count() + projects_to_mark.count()
                    
                    if unread_count > 0:
                        jobs_to_mark.update(is_read_by_employer=True)
                        projects_to_mark.update(is_read_by_employer=True)
                else:
                    # Mark EVERYTHING as read for this employer
                    unread_count = all_unread_jobs.count() + all_unread_projects.count()
                    if unread_count > 0:
                        all_unread_jobs.update(is_read_by_employer=True)
                        all_unread_projects.update(is_read_by_employer=True)
            elif user_role == "candidate":
                # Mark as read for candidate
                all_unread_jobs = JobApplication.objects.filter(candidate__user=request.user, is_read_by_candidate=False)
                all_unread_projects = ProjectApplication.objects.filter(candidate__user=request.user, is_read_by_candidate=False)
                
                unread_count = all_unread_jobs.count() + all_unread_projects.count()
                if unread_count > 0:
                    all_unread_jobs.update(is_read_by_candidate=True)
                    all_unread_projects.update(is_read_by_candidate=True)

            if unread_count > 0:
                # Broadcast update via WebSocket
                from utils.broadcaster import broadcast_count_update
                if user_role == "employer":
                    from employers.utils import get_employer_unread_counts
                    broadcast_count_update(
                        user_id=request.user.id,
                        count_type="global",
                        unread_count=get_employer_unread_counts(request.user)
                    )
                else:
                    from candidates.utils import get_candidate_unread_counts
                    broadcast_count_update(
                        user_id=request.user.id,
                        count_type="applications",
                        unread_count=get_candidate_unread_counts(request.user)
                    )
            
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                response = self.get_paginated_response(page)
                # Put unread_counts at the top for frontend sync
                ordered_data = {
                    'unread_count': 0,
                    'unread_counts': get_employer_unread_counts(request.user)
                }
                ordered_data.update(response.data)
                response.data = ordered_data
                return response
                
            # Mark all as read logic above updates the DB.
            # We return 0 as requested by the user for frontend synchronization.
            return Response({
                'unread_count': 0,
                'unread_counts': get_employer_unread_counts(request.user),
                'results': queryset
            })
        except Exception as e:
            logger.error(f"Error in CombinedApplicationsView: {str(e)}", exc_info=True)
            return Response(
                {"error": "An error occurred while fetching applications"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class JobApplicationViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "is_shortlisted", "is_rejected"]
    search_fields = ["job__title", "candidate__full_name"]
    ordering_fields = ["applied_at", "overall_match_score"]
    ordering = ["-applied_at"]

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return JobApplicationListSerializer
        return JobApplicationSerializer

    def get_queryset(self):
        user_role = getattr(getattr(self.request.user, 'role', None), 'name', None)
        if user_role == "candidate":
            return JobApplication.objects.filter(candidate__user=self.request.user).select_related(
                'job', 'candidate', 'company'
            )
        elif user_role == "employer":
            return JobApplication.objects.filter(employer=self.request.user).select_related(
                'job', 'candidate', 'company'
            )
        return JobApplication.objects.none()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user_role = getattr(getattr(request.user, 'role', None), 'name', None)
        if user_role == "employer":
            unread_count = queryset.filter(is_read_by_employer=False).count()
            if unread_count > 0:
                queryset.filter(is_read_by_employer=False).update(is_read_by_employer=True)
                
                # Broadcast update via WebSocket
                from utils.broadcaster import broadcast_count_update
                from employers.utils import get_employer_unread_counts
                broadcast_count_update(
                    user_id=request.user.id,
                    count_type="global",
                    unread_count=get_employer_unread_counts(request.user)
                )
            
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ProjectApplicationViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "is_shortlisted", "is_rejected"]
    search_fields = ["project__title", "candidate__full_name"]
    ordering_fields = ["applied_at", "overall_match_score"]
    ordering = ["-applied_at"]

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ProjectApplicationListSerializer
        return ProjectApplicationSerializer

    def get_queryset(self):
        user_role = getattr(getattr(self.request.user, 'role', None), 'name', None)
        if user_role == "candidate":
            return ProjectApplication.objects.filter(candidate__user=self.request.user).select_related(
                'project', 'candidate', 'company'
            )
        elif user_role == "employer":
            return ProjectApplication.objects.filter(employer=self.request.user).select_related(
                'project', 'candidate', 'company'
            )
        return ProjectApplication.objects.none()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user_role = getattr(getattr(request.user, 'role', None), 'name', None)
        if user_role == "employer":
            unread_count = queryset.filter(is_read_by_employer=False).count()
            if unread_count > 0:
                queryset.filter(is_read_by_employer=False).update(is_read_by_employer=True)
                
                # Broadcast update via WebSocket
                from utils.broadcaster import broadcast_count_update
                from employers.utils import get_employer_unread_counts
                broadcast_count_update(
                    user_id=request.user.id,
                    count_type="global",
                    unread_count=get_employer_unread_counts(request.user)
                )
            
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def apply_to_job(request, job_id):
    try:
        job = Job.objects.get(id=job_id, status="active")

        if JobApplication.objects.filter(candidate__user=request.user, job=job).exists():
            return Response(
                {"error": "You have already applied for this job"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application = JobApplication.objects.create(
            candidate=request.user.candidate_profile,
            job=job,
            employer=job.employer,
            company=job.company,
            coverLetter=request.data.get("coverLetter", ""),
            resumeUrl=request.data.get("resumeUrl", ""),
            interestedInTemp=request.data.get("interestedInTemp", False),
        )

        from utils.broadcaster import broadcast_count_update
        from employers.utils import get_employer_unread_counts
        broadcast_count_update(
            user_id=job.employer.id,
            count_type="global",
            unread_count=get_employer_unread_counts(job.employer)
        )

        return Response(
            {
                "message": "Application submitted successfully",
                "application": JobApplicationSerializer(application).data,
            },
            status=status.HTTP_201_CREATED,
        )
    except Job.DoesNotExist:
        return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Error in apply_to_job")
        return Response({"error": "Failed to apply"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def apply_to_project(request, project_id):
    try:
        project = Project.objects.get(id=project_id, status="active")

        if ProjectApplication.objects.filter(candidate__user=request.user, project=project).exists():
            return Response(
                {"error": "You have already applied for this project"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application = ProjectApplication.objects.create(
            candidate=request.user.candidate_profile,
            project=project,
            employer=project.employer,
            company=project.company,
            coverLetter=request.data.get("coverLetter", ""),
        )

        from utils.broadcaster import broadcast_count_update
        from employers.utils import get_employer_unread_counts
        broadcast_count_update(
            user_id=project.employer.id,
            count_type="global",
            unread_count=get_employer_unread_counts(project.employer)
        )
        
        cache_key = f'candidate_{request.user.candidate_profile.id}_latest_projects'
        cache.delete(cache_key)

        return Response(
            {
                "message": "Application submitted successfully",
                "application": ProjectApplicationSerializer(application).data,
            },
            status=status.HTTP_201_CREATED,
        )
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Error in apply_to_project")
        return Response({"error": "Failed to apply"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def withdraw_application(request, application_id, application_type):
    try:
        if application_type == "job":
            application = JobApplication.objects.get(id=application_id, candidate__user=request.user)
        elif application_type == "project":
            application = ProjectApplication.objects.get(id=application_id, candidate__user=request.user)
        else:
            return Response({"error": "Invalid application type"}, status=status.HTTP_400_BAD_REQUEST)

        application.is_withdrawn = True
        application.status = "withdrawn"
        application.save()

        # Notify Employer via WebSocket
        if application.employer:
            from utils.broadcaster import broadcast_count_update
            from employers.utils import get_employer_unread_counts
            broadcast_count_update(
                user_id=application.employer.id,
                count_type="applications",
                unread_count=get_employer_unread_counts(application.employer)
            )

        return Response({"message": "Application withdrawn successfully"})
    except JobApplication.DoesNotExist:
        return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
    except ProjectApplication.DoesNotExist:
        return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Error in withdraw_application")

class ActivePostingsListView(generics.ListAPIView):
    """
    Returns a list of unique Jobs and Projects that have received applications.
    Useful for filtering applications by posting on the frontend.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        user_role = getattr(getattr(user, 'role', None), 'name', None)
        
        if user_role != "employer":
            return Response({"detail": "Only employers can access this list."}, status=status.HTTP_403_FORBIDDEN)
            
        results = []
        
        # 1. Get unique Jobs with applications
        jobs_with_apps = Job.objects.filter(
            applications__employer=user
        ).annotate(
            app_count=Count('applications')
        ).filter(app_count__gt=0).distinct()
        
        for job in jobs_with_apps:
            results.append({
                'id': job.id,
                'title': job.title,
                'type': 'job',
                'application_count': job.app_count
            })
            
        # 2. Get unique Projects with applications
        projects_with_apps = Project.objects.filter(
            applications__employer=user
        ).annotate(
            app_count=Count('applications')
        ).filter(app_count__gt=0).distinct()
        
        for project in projects_with_apps:
            results.append({
                'id': project.id,
                'title': project.title,
                'type': 'project',
                'application_count': project.app_count
            })
            
        # Sort by title for easy lookup
        results.sort(key=lambda x: x['title'])
        
        return Response({"results": results})