from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models
from .models import (
    JobApplication,
    ProjectApplication,
    Interview,
    ApplicationMessage,
    InterviewRequest,
)
from .serializers import (
    JobApplicationSerializer,
    ProjectApplicationSerializer,
    InterviewSerializer,
    ApplicationMessageSerializer,
    InterviewRequestSerializer,
    JobApplicationListSerializer,
    ProjectApplicationListSerializer,
)
from jobs.models import Job
from projects.models import Project

class JobApplicationListView(generics.ListCreateAPIView):
    """
    Job application list and create view
    """

    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "is_shortlisted", "is_rejected"]
    search_fields = ["job__title", "candidate__full_name"]
    ordering_fields = ["applied_at", "overall_match_score"]
    ordering = ["-applied_at"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return JobApplicationSerializer
        return JobApplicationListSerializer

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return JobApplication.objects.filter(candidate__user=self.request.user)
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return JobApplication.objects.filter(employer=self.request.user)
        return JobApplication.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            {"message": "Application submitted successfully", "application": serializer.data},
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class ProjectApplicationListView(generics.ListCreateAPIView):
    """
    Project application list and create view
    """

    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "is_shortlisted", "is_rejected"]
    search_fields = ["project__title", "candidate__full_name"]
    ordering_fields = ["applied_at", "overall_match_score"]
    ordering = ["-applied_at"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectApplicationSerializer
        return ProjectApplicationListSerializer
        
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return ProjectApplication.objects.filter(candidate__user=self.request.user)
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return ProjectApplication.objects.filter(employer=self.request.user)
        return ProjectApplication.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            {"message": "Application submitted successfully", "application": serializer.data},
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class JobApplicationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Job application detail view
    """

    serializer_class = JobApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return JobApplication.objects.filter(candidate__user=self.request.user)
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return JobApplication.objects.filter(employer=self.request.user)
        return JobApplication.objects.none()


class ProjectApplicationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Project application detail view
    """

    serializer_class = ProjectApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return ProjectApplication.objects.filter(candidate__user=self.request.user)
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return ProjectApplication.objects.filter(employer=self.request.user)
        return ProjectApplication.objects.none()


class InterviewListView(generics.ListCreateAPIView):
    """
    Interview list and create view
    """

    serializer_class = InterviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return Interview.objects.filter(
                models.Q(job_application__candidate__user=self.request.user)
                | models.Q(project_application__candidate__user=self.request.user)
            )
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return Interview.objects.filter(
                models.Q(job_application__employer=self.request.user)
                | models.Q(project_application__employer=self.request.user)
            )
        return Interview.objects.none()


class InterviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Interview detail view
    """

    serializer_class = InterviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return Interview.objects.filter(
                models.Q(job_application__candidate__user=self.request.user)
                | models.Q(project_application__candidate__user=self.request.user)
            )
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return Interview.objects.filter(
                models.Q(job_application__employer=self.request.user)
                | models.Q(project_application__employer=self.request.user)
            )
        return Interview.objects.none()


class ApplicationMessageListView(generics.ListCreateAPIView):
    """
    Application message list and create view
    """

    serializer_class = ApplicationMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return ApplicationMessage.objects.filter(
                models.Q(job_application__candidate__user=self.request.user)
                | models.Q(project_application__candidate__user=self.request.user)
            )
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return ApplicationMessage.objects.filter(
                models.Q(job_application__employer=self.request.user)
                | models.Q(project_application__employer=self.request.user)
            )
        return ApplicationMessage.objects.none()


class InterviewRequestListView(generics.ListCreateAPIView):
    """
    Interview request list and create view
    """

    serializer_class = InterviewRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(getattr(self.request.user, 'role', None), 'name', None) == "candidate":
            return InterviewRequest.objects.filter(
                models.Q(job_application__candidate__user=self.request.user)
                | models.Q(project_application__candidate__user=self.request.user)
            )
        elif getattr(getattr(self.request.user, 'role', None), 'name', None) == "employer":
            return InterviewRequest.objects.filter(
                models.Q(job_application__employer=self.request.user)
                | models.Q(project_application__employer=self.request.user)
            )
        return InterviewRequest.objects.none()


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def apply_to_job(request, job_id):
    """
    Apply to a job
    """
    try:

        job = Job.objects.get(id=job_id, status="active")

        # Check if already applied
        if JobApplication.objects.filter(
            candidate__user=request.user, job=job
        ).exists():
            return Response(
                {"error": "You have already apply for this job"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create application
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
        return Response(
            {"error": "Failed to apply"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def apply_to_project(request, project_id):
    """
    Apply to a project
    """
    try:
        project = Project.objects.get(id=project_id, status="active")

        # Check if already applied
        if ProjectApplication.objects.filter(
            candidate__user=request.user, project=project
        ).exists():
            return Response(
                {"error": "You have already apply for this project"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create application
        application = ProjectApplication.objects.create(
            candidate=request.user.candidate_profile,
            project=project,
            employer=project.employer,
            company=project.company,
            coverLetter=request.data.get("coverLetter", ""),
        )

        return Response(
            {
                "message": "Application submitted successfully",
                "application": ProjectApplicationSerializer(application).data,
            },
            status=status.HTTP_201_CREATED,
        )
    except Project.DoesNotExist:
        return Response(
            {"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": "Failed to apply"}, status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def withdraw_application(request, application_id, application_type):
    """
    Withdraw an application
    """
    try:
        if application_type == "job":
            application = JobApplication.objects.get(
                id=application_id, candidate__user=request.user
            )
        elif application_type == "project":
            application = ProjectApplication.objects.get(
                id=application_id, candidate__user=request.user
            )
        else:
            return Response(
                {"error": "Invalid application type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.is_withdrawn = True
        application.status = "withdrawn"
        application.save()

        return Response(
            {
                "message": "Application withdrawn successfully",
                "application": {
                    "id": application.id,
                    "status": application.status,
                    "is_withdrawn": application.is_withdrawn,
                },
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND
        )
