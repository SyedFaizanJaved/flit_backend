from rest_framework import viewsets, mixins, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions
from rest_framework.filters import SearchFilter, OrderingFilter
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

logger = logging.getLogger("exceptions")

class CombinedApplicationsView(generics.ListAPIView):
    """
    Combined view for job and project applications with pagination
    """
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        from applications.models import JobApplication, ProjectApplication
        
        # Get the company_id from query params if provided
        company_id = self.request.query_params.get('company_id')
        
        # Base querysets with select_related/prefetch_related for performance
        job_apps = JobApplication.objects.select_related('job', 'candidate__user')
        project_apps = ProjectApplication.objects.select_related('project', 'candidate__user')
        
        # Apply company filter if company_id is provided
        if company_id:
            job_apps = job_apps.filter(job__company_id=company_id)
            project_apps = project_apps.filter(project__company_id=company_id)
        
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
            
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                return self.get_paginated_response(page)
                
            return Response(queryset)
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

        return Response({"message": "Application withdrawn successfully"})
    except JobApplication.DoesNotExist:
        return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
    except ProjectApplication.DoesNotExist:
        return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Error in withdraw_application")
        return Response({"error": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST)