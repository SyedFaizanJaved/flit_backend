from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
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
from django.core.exceptions import PermissionDenied
from datetime import timedelta , datetime
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from vr_meet.views import create_google_event
from vr_meet.models import MeetingRoom
import logging
from utils.pagination import CustomPagination

logger = logging.getLogger("exceptions")


class JobApplicationListView(generics.ListCreateAPIView):
    """
    Job application list and create view
    """
    pagination_class = CustomPagination
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
    pagination_class = CustomPagination
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

    # Create interview request
    def perform_create(self, serializer):
        user = self.request.user
        data = self.request.data
        role = getattr(getattr(user, 'role', None), 'name', None)

        # Only employers can create interview requests
        if role != "employer":
            raise PermissionDenied("Only employers can create interview requests.")

        # Save interview request
        interview_request = serializer.save(status="pending")

        # Determine candidate and job/project title
        if interview_request.job_application:
            candidate = interview_request.job_application.candidate.user
            title = interview_request.job_application.job.title
        elif interview_request.project_application:
            candidate = interview_request.project_application.candidate.user
            title = interview_request.project_application.project.title
        else:
            raise ValidationError('Interview request must be for either a job or project application.')

        # Meeting time
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        if start_time:
            start_time = timezone.make_aware(datetime.fromisoformat(start_time))
        if end_time:
            end_time = timezone.make_aware(datetime.fromisoformat(end_time))
        
        if start_time and end_time:
            now = timezone.now()
            if start_time < now:
                raise ValidationError('Start time cannot be in the past.')
            if end_time <= start_time:
                raise ValidationError('End time must be greater than start time.')
            
        elif start_time and not end_time:
            end_time = start_time + timedelta(minutes=30)
        elif end_time and not start_time:
            start_time = end_time - timedelta(minutes=30)
        else:
            start_time = timezone.now()
            end_time = start_time + timedelta(minutes=30)

        # Create Google Meet event
        try:
            meet_link, event_id = create_google_event(
                user=user,
                title=f"Interview for {title}",
                description="Auto-generated interview room",
                start_time=start_time,
                end_time=end_time,
                attendees=[candidate.email, user.email]
            )
        except Exception as e:
            logger.exception("Google Calendar event creation failed")
            print("GOOGLE CALENDAR ERROR:", e)
            meet_link = None

        if not meet_link:
            logger.error("Failed to generate Google Meet link. Interview request not created.")
            raise ValidationError("Failed to generate Google Meet link. Interview request not created.")
        # Create MeetingRoom entry
        room=MeetingRoom.objects.create(
            meeting_title=f"Interview for {title}",
            employer=user,
            candidate=candidate,
            candidate_email=candidate.email,
            room_type="interview",
            purpose="interview",
            environment="office",
            start_time=start_time,
            end_time=end_time,
            meet_link=meet_link,
            description="Auto-generated interview room",
            privacy="private"
        )

        # attach Meet link to interview request
        interview_request.meetLink = meet_link
        interview_request.proposedTime = start_time
        interview_request.save()
        return interview_request

# Update interview request
class InterviewRequestupdateView(generics.RetrieveUpdateAPIView):
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
    
    def perform_update(self, serializer):
        user = self.request.user
        role = getattr(getattr(user, 'role', None),'name', None)

        # Only candidates can update interview requests
        if role != "candidate":
            raise PermissionDenied("You do not have permission to update interview requests")
        
        # Allowed status changes
        allowed_status = ["accepted", "declined"]
        new_status = serializer.validated_data.get('status')
        if new_status not in allowed_status:
            raise PermissionDenied("Invalid status change by candidate.")
        instance = serializer.save()
        return instance

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
        logger.error("Job.DoesNotExist: Job not found while applying")
        return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Unexpected error in job apply flow")
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
        logger.error("Project.DoesNotExist: Project not found while applying")
        return Response(
            {"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception("Unexpected error in project apply flow")
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
        logger.exception("Unexpected error while fetching application")
        return Response(
            {"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND
        )
