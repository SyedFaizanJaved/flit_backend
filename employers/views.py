import logging
import requests
from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.urls import reverse as drf_reverse
from django.db.models import Q

from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
import time
from accounts.views import BaseRoleRegistrationView
from utils.pagination import CustomPagination

from .models import Employer, EmployerPreference, EmployerCompliance, CandidateAction
from .serializers import (
    EmployerSerializer,
    EmployerListSerializer,
    EmployerProfileUpdateSerializer,
    EmployerPreferenceSerializer,
    EmployerComplianceSerializer,
    CandidateActionSerializer,
    CandidateActionDetailSerializer,
)
from jobs.models import Job
from projects.models import Project
from vr_meet.models import Offer, MeetingRoom
from applications.models import JobApplication, ProjectApplication, InterviewRequest
from chat.models import ChatMessage
from jobs.serializers import JobListSerializer
from projects.serializers import ProjectListSerializer
from vr_meet.serializers import MeetingRoomSerializer, OfferSerializer
from applications.serializers import InterviewRequestSerializer
from candidates.models import Candidate
from utils.email_service import send_flit_pass_notification

User = get_user_model()
from .utils import get_employer_unread_counts
logger = logging.getLogger(__name__)
exception_logger = logging.getLogger("exceptions")


class EmployerDashboardBaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_employer_profile(self, user):
        try:
            return user.employer_profile
        except Employer.DoesNotExist:
            exception_logger.error("Employer profile not found for user %s", user.id)
            raise Http404("Employer profile not found")


class CandidateActionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'shortlisted']:
            return CandidateActionDetailSerializer
        return CandidateActionSerializer
        
    def get_queryset(self):
        return CandidateAction.objects.filter(
            employer__user=self.request.user,
            action='pass'
        ).select_related('employer').order_by('-created_at')

    def create(self, request, *args, **kwargs):
        employer = request.user.employer_profile
        candidate_id = request.data.get('candidate_id') or request.query_params.get('candidate_id')
        requested_action = request.data.get('action')

        if not candidate_id:
            return Response({"detail": "candidate_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not requested_action:
            return Response({"detail": "action is required"}, status=status.HTTP_400_BAD_REQUEST)
        if requested_action not in ['pass', 'reject']:
            return Response({"detail": "action must be 'pass' or 'reject'"}, status=status.HTTP_400_BAD_REQUEST)

        # Get candidate instance for email notification (only for 'pass' action)
        candidate = None
        if requested_action == 'pass':
            try:
                # Convert candidate_id to int if it's a string
                candidate_id_int = int(candidate_id) if isinstance(candidate_id, str) else candidate_id
                candidate = Candidate.objects.filter(Q(id=candidate_id_int) | Q(user_id=candidate_id_int)).first()
            except (ValueError, TypeError) as e:
                logger.warning(f"Candidate with id {candidate_id} not found for flit pass notification: {str(e)}")

        try:
            instance = CandidateAction.objects.get(employer=employer, candidate_id=candidate_id)
            is_new_flit = instance.action != 'pass' and requested_action == 'pass'
            instance.action = requested_action
            instance.save()
            
            # Send email notification only when flitting (pass action) for the first time
            if requested_action == 'pass' and is_new_flit and candidate:
                try:
                    company_name = employer.company.company_name if employer.company else None
                    send_flit_pass_notification(
                        candidate=candidate,
                        employer_name=employer.full_name,
                        company_name=company_name,
                        category=employer.company.industry if employer.company else "Not specified"
                    )
                except Exception as e:
                    logger.error(f"Failed to send flit pass email notification: {str(e)}")
                    # Don't fail the request if email fails

            if requested_action == 'pass' and candidate:
                from utils.broadcaster import broadcast_count_update
                from candidates.utils import get_candidate_unread_counts
                broadcast_count_update(
                    user_id=candidate.user.id,
                    count_type="flit_list",
                    unread_count=get_candidate_unread_counts(candidate.user)
                )

            serializer = CandidateActionDetailSerializer(instance, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CandidateAction.DoesNotExist:
            serializer = self.get_serializer(data={
                'candidate_id': candidate_id,
                'action': requested_action
            })
            serializer.is_valid(raise_exception=True)
            serializer.save(employer=employer)
            
            # Send email notification when flitting (pass action) for the first time
            if requested_action == 'pass' and candidate:
                try:
                    company_name = employer.company.company_name if employer.company else None
                    send_flit_pass_notification(
                        candidate=candidate,
                        employer_name=employer.full_name,
                        company_name=company_name,
                        category=employer.company.industry if employer.company else "Not specified"
                    )
                except Exception as e:
                    logger.error(f"Failed to send flit pass email notification: {str(e)}")
                    # Don't fail the request if email fails

                from utils.broadcaster import broadcast_count_update
                from candidates.utils import get_candidate_unread_counts
                broadcast_count_update(
                    user_id=candidate.user.id,
                    count_type="flit_list",
                    unread_count=get_candidate_unread_counts(candidate.user)
                )

            detail_serializer = CandidateActionDetailSerializer(serializer.instance, context={'request': request})
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def shortlisted(self, request):
        employer_user = request.user

        job_applications = JobApplication.objects.filter(
            employer=employer_user,
            is_shortlisted=True
        ).select_related('candidate__user', 'job', 'company')

        project_applications = ProjectApplication.objects.filter(
            employer=employer_user,
            is_shortlisted=True
        ).select_related('candidate__user', 'project', 'company')

        combined = []

        for app in job_applications:
            combined.append({
                'id': app.id,
                'type': 'job',
                'title': app.job.title,
                'status': 'shortlisted',
                'applied_at': app.applied_at,
                'application': {
                    'id': app.id,
                    'candidate_id': app.candidate.id,
                    'candidate_name': app.candidate.full_name,
                    'candidate_email': app.candidate.user.email,
                    'candidate_user_id': app.candidate.user.id,
                    'job_title': app.job.title,
                    'job_id': app.job.id,
                    'company_name': app.company.name,
                    'status': app.status,
                    'candidate_profile_image': app.candidate.profile_image.url if app.candidate.profile_image else None,
                    'coverLetter': app.coverLetter,
                    'overall_match_score': getattr(app, 'overall_match_score', None),
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected,
                }
            })

        for app in project_applications:
            combined.append({
                'id': app.id,
                'type': 'project',
                'title': app.project.title,
                'status': 'shortlisted',
                'applied_at': app.applied_at,
                'application': {
                    'id': app.id,
                    'candidate_id': app.candidate.id,
                    'candidate_name': app.candidate.full_name,
                    'candidate_email': app.candidate.user.email,
                    'candidate_user_id': app.candidate.user.id,
                    'project_title': app.project.title,
                    'project_id': app.project.id,
                    'company_name': app.company.name,
                    'status': app.status,
                    'candidate_profile_image': app.candidate.profile_image.url if app.candidate.profile_image else None,
                    'coverLetter': app.coverLetter,
                    'overall_match_score': getattr(app, 'overall_match_score', None),
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected,
                }
            })

        combined.sort(key=lambda x: x['applied_at'], reverse=True)

        page = self.paginate_queryset(combined)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(combined)


class EmployerProfileDashboardView(EmployerDashboardBaseView):
    def get(self, request):
        employer = self.get_employer_profile(request.user)
        serializer = EmployerSerializer(employer, context={'request': request})
        return Response({
            'profile': serializer.data,
            'profile_completed': employer.is_profile_complete,
            'jobs_posted': employer.total_jobs_posted,
            'projects_posted': employer.total_projects_posted,
            'applications_received': employer.total_applications_received,
            'hires': employer.total_hires,
        })


class EmployerJobApplicationsView(EmployerDashboardBaseView):
    def get(self, request):
        applications = JobApplication.objects.filter(
            employer=request.user
        ).select_related('candidate__user', 'job', 'company').order_by('-applied_at')

        # Mark all as read when employer views the list
        unread_count = applications.filter(is_read_by_employer=False).count()
        if unread_count > 0:
            applications.filter(is_read_by_employer=False).update(is_read_by_employer=True)
            
            # Broadcast update via WebSocket
            from utils.broadcaster import broadcast_count_update
            broadcast_count_update(
                user_id=request.user.id,
                count_type="global",
                unread_count=get_employer_unread_counts(request.user)
            )

        status_choices = ['pending', 'reviewing', 'shortlisted', 'interviewed', 'hired', 'rejected', 'withdrawn']
        status_counts = {f'{s}_count': applications.filter(status=s).count() for s in status_choices}

        recent = applications[:5]
        data = []
        for app in recent:
            candidate_name = app.candidate.full_name if app.candidate else "Unknown Candidate"
            data.append({
                'id': app.id,
                'candidate_name': candidate_name,
                'job_title': app.job.title if app.job else "Unknown Job",
                'company': app.company.company_name if app.company else "Unknown Company",
                'status': app.status,
                'applied_at': app.applied_at,
                'type': 'job',
                'match_score': getattr(app, 'overall_match_score', None),
            })

        return Response({
            'unread_count': 0,
            'unread_counts': get_employer_unread_counts(request.user),
            'recent_job_applications': data,
            'total_job_applications': applications.count(),
            **status_counts
        })


class EmployerProjectApplicationsView(EmployerDashboardBaseView):
    def get(self, request):
        applications = ProjectApplication.objects.filter(
            employer=request.user
        ).select_related('candidate__user', 'project', 'company').order_by('-applied_at')

        # Mark all as read when employer views the list
        unread_count = applications.filter(is_read_by_employer=False).count()
        if unread_count > 0:
            applications.filter(is_read_by_employer=False).update(is_read_by_employer=True)
            
            # Broadcast update via WebSocket
            from utils.broadcaster import broadcast_count_update
            broadcast_count_update(
                user_id=request.user.id,
                count_type="global",
                unread_count=get_employer_unread_counts(request.user)
            )

        status_choices = ['pending', 'reviewing', 'shortlisted', 'hired', 'rejected', 'withdrawn']
        status_counts = {f'{s}_count': applications.filter(status=s).count() for s in status_choices}

        recent = applications[:5]
        data = []
        for app in recent:
            candidate_name = app.candidate.full_name if app.candidate else "Unknown Candidate"
            data.append({
                'id': app.id,
                'candidate_name': candidate_name,
                'project_title': app.project.title if app.project else "Unknown Project",
                'company': app.company.company_name if app.company else "Unknown Company",
                'status': app.status,
                'applied_at': app.applied_at,
                'type': 'project',
                'match_score': getattr(app, 'overall_match_score', None),
            })

        return Response({
            'unread_count': 0,
            'unread_counts': get_employer_unread_counts(request.user),
            'recent_project_applications': data,
            'total_project_applications': applications.count(),
            **status_counts
        })


class EmployerRegistrationView(BaseRoleRegistrationView):
    fixed_user_type = "employer"


class EmployerViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    def list(self, request):
        queryset = Employer.objects.filter(is_profile_public=True)
        serializer = EmployerListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        employer, _ = Employer.objects.get_or_create(
            user=request.user,
            defaults={'first_name': request.user.first_name, 'last_name': request.user.last_name}
        )

        if request.method == 'GET':
            return Response(EmployerSerializer(employer, context={'request': request}).data)

        serializer = EmployerProfileUpdateSerializer(
            employer, data=request.data, partial=(request.method == 'PATCH')
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(EmployerSerializer(employer, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='unread-counts', permission_classes=[permissions.IsAuthenticated])
    def unread_counts(self, request):
        if not hasattr(request.user, 'employer_profile'):
            return Response(
                {"detail": "You do not have permission to access employer notifications."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        return Response(get_employer_unread_counts(request.user))

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard(self, request):
        user = request.user

        # --- Banner Seen Logic ---
        show_banner = False
        try:
            employer_profile = user.employer_profile
            show_banner = employer_profile.banner_seen
            if show_banner:
                employer_profile.banner_seen = False
                employer_profile.save(update_fields=['banner_seen'])
        except Employer.DoesNotExist:
            exception_logger.error("Employer profile not found for user %s", user.id)

        # 2. Stats — scope by company so the dashboard agrees with the per-tab
        # `my-projects` / `my-jobs` endpoints (Bug #22). Falls back to `employer=user`
        # for users without an employer_profile.company link.
        company = getattr(getattr(user, 'employer_profile', None), 'company', None)
        if company is not None:
            project_qs = Project.objects.filter(company=company)
            job_qs = Job.objects.filter(company=company)
        else:
            project_qs = Project.objects.filter(employer=user)
            job_qs = Job.objects.filter(employer=user)

        stats = {
            'total_projects': project_qs.count(),
            'active_projects': project_qs.filter(status='active').count(),
            'total_jobs': job_qs.count(),
            'active_jobs': job_qs.filter(status='active').count(),
            'total_applications': user.received_job_applications.count() + user.received_project_applications.count(),
            'completed': job_qs.filter(status='completed').count()
                         + project_qs.filter(status='completed').count(),
        }

        # 3. Meet & Greet (Latest 2 each)
        invited_reqs = InterviewRequest.objects.filter(
            Q(job_application__employer=user) | Q(project_application__employer=user),
            status='pending'
        ).select_related('job_application__job', 'project_application__project', 'job_application__candidate', 'project_application__candidate').order_by('-created_at')[:2]
        
        # In this project, scheduled meetings usually have 'active' status
        scheduled_meetings = MeetingRoom.objects.filter(
            employer=user,
            status='active',
            is_deleted=False
        ).select_related('candidate').order_by('-start_time')[:2]

        # 4. Posting (Latest 2 each)
        latest_jobs = Job.objects.filter(employer=user).order_by('-created_at')[:2]
        latest_projects = Project.objects.filter(employer=user).order_by('-created_at')[:2]

        # 5. Hired Candidates (Latest 5 accepted offers)
        hired_candidates = Offer.objects.filter(
            employer=user,
            status__in=['accepted', 'hired']
        ).select_related('candidate', 'meeting').order_by('-updated_at')[:5]

        # 6. Latest Messages with sender images
        latest_msgs = ChatMessage.objects.filter(recipient=user).select_related('sender').order_by('-created_at')[:4]
        latest_messages_data = []
        for m in latest_msgs:
            sender_image = None
            try:
                if hasattr(m.sender, 'candidate_profile') and m.sender.candidate_profile.profile_image:
                    sender_image = request.build_absolute_uri(m.sender.candidate_profile.profile_image.url)
                elif hasattr(m.sender, 'employer_profile') and m.sender.employer_profile.profile_picture:
                    sender_image = request.build_absolute_uri(m.sender.employer_profile.profile_picture.url)
            except Exception:
                pass
                
            latest_messages_data.append({
                'id': m.id,
                'message': m.message,
                'sender_name': m.sender.get_full_name() or m.sender.email,
                'logo': sender_image,
                'created_at': m.created_at,
                'sender_id': m.sender.id,
                'is_read': m.is_read
            })
        
        # Prepare response data
        return Response({
            'banner_seen': show_banner,
            'stats': stats,
            'unread_counts': get_employer_unread_counts(user),
            'meet_and_greet': {
                'invited': InterviewRequestSerializer(invited_reqs, many=True, context={'request': request}).data,
                'scheduled': MeetingRoomSerializer(scheduled_meetings, many=True, context={'request': request}).data
            },
            'postings': {
                'jobs': JobListSerializer(latest_jobs, many=True, context={'request': request}).data,
                'projects': ProjectListSerializer(latest_projects, many=True, context={'request': request}).data
            },
            'hired_candidates': OfferSerializer(hired_candidates, many=True, context={'request': request}).data,
            'latest_messages': latest_messages_data
        })

    @action(detail=False, methods=['post'], url_path='profile/complete/(?P<section>[^/.]+)', permission_classes=[permissions.IsAuthenticated])
    def complete_profile_section(self, request, section=None):
        employer = get_object_or_404(Employer, user=request.user)

        section_map = {
            'basic_info': 'basic_info_completed',
            'company_info': 'company_info_completed',
        }
        if section not in section_map:
            return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)

        setattr(employer, section_map[section], True)
        employer.save(update_fields=[section_map[section]])

        if employer.is_profile_complete:
            request.user.profile_completed = True
            request.user.save(update_fields=['profile_completed'])

        return Response({
            'message': f'{section.replace("_", " ").title()} section marked as complete',
            'profile_completed': employer.is_profile_complete
        })

    @action(detail=False, methods=['delete'], permission_classes=[permissions.IsAuthenticated])
    def delete_profile(self, request):
        """
        Sirf Employer profile delete karta hai (user account safe rahega)
        """
        try:
            employer = request.user.employer_profile

            # Related data delete
            if hasattr(employer, 'preferences'):
                employer.preferences.delete()
            if hasattr(employer, 'compliance'):
                employer.compliance.delete()

            CandidateAction.objects.filter(employer=employer).delete()

            employer.delete()

            request.user.profile_completed = False
            if hasattr(request.user, 'user_type'):
                request.user.user_type = None 
            request.user.save(update_fields=['profile_completed', 'user_type'])

            return Response({
                'message': 'Employer profile successfully deleted. You can now switch to candidate role if needed.'
            }, status=status.HTTP_200_OK)

        except Employer.DoesNotExist:
            return Response({'error': 'Employer profile not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            exception_logger.exception("Error deleting employer profile for user %s", request.user.id)
            return Response({'error': 'Failed to delete profile'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['delete'], url_path='delete-account', permission_classes=[permissions.IsAuthenticated])
    def delete_account(self, request):
        """
        Pura account delete (soft delete - recommended for safety & compliance)
        User login nahi kar payega baad mein
        """
        user = request.user

        try:
            # Employer profile aur related data delete
            if hasattr(user, 'employer_profile'):
                employer = user.employer_profile
                if hasattr(employer, 'preferences'):
                    employer.preferences.delete()
                if hasattr(employer, 'compliance'):
                    employer.compliance.delete()
                CandidateAction.objects.filter(employer=employer).delete()
                employer.delete()

            # Soft delete user (industry standard)
            user.is_active = False
            user.email = f"deleted_{user.id}_{timezone.now().timestamp()}@deleted.com"
            user.username = f"deleted_user_{user.id}"
            user.first_name = "Deleted"
            user.last_name = "User"
            user.set_unusable_password()
            user.save()

            return Response({
                'message': 'Your account has been permanently deleted. You have been logged out.'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            exception_logger.exception("Critical error deleting account for user %s", user.id)
            return Response({'error': 'Failed to delete account'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EmployerPreferenceView(generics.RetrieveUpdateAPIView):
    serializer_class = EmployerPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        pref, _ = EmployerPreference.objects.get_or_create(employer=self.request.user.employer_profile)
        return pref


class EmployerComplianceView(generics.RetrieveUpdateAPIView):
    serializer_class = EmployerComplianceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        comp, _ = EmployerCompliance.objects.get_or_create(employer=self.request.user.employer_profile)
        return comp


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])  
def get_flitpass_data(request, company_id):
    """
    Fetch FlitPass data for a specific company from the ML API.
    
    Args:
        request: The HTTP request object
        company_id: ID of the company to fetch FlitPass data for
        
    Returns:
        Response: JSON response containing FlitPass data or error message
    """
    try:
        ml_api_url = f"{settings.FLIT_AI_URL}/flitpass/{company_id}"
        
        # Make a single request 
        response = requests.get(ml_api_url)
        response.raise_for_status()
        
        data = response.json()
        
        # Collect candidate items to update (item_dict, candidate_id)
        items_to_update = []
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    cid = item.get('candidate_id') or item.get('id')
                    if cid:
                        items_to_update.append((item, cid))
        elif isinstance(data, dict):
            # Check if 'candidates' is a dictionary {candidate_id: candidate_data}
            candidates_val = data.get('candidates')
            if isinstance(candidates_val, dict):
                for cid, c_data in candidates_val.items():
                    if isinstance(c_data, dict):
                        items_to_update.append((c_data, cid))
            else:
                # Fallback to lists in 'candidates', 'results', or 'data'
                for key in ['candidates', 'results', 'data']:
                    target = data.get(key)
                    if isinstance(target, list):
                        for item in target:
                            if isinstance(item, dict):
                                cid = item.get('candidate_id') or item.get('id')
                                if cid:
                                    items_to_update.append((item, cid))
                        break
        
        if items_to_update:
            # Collect unique IDs (convert to string for mapping)
            unique_ids = list(set([str(it[1]) for it in items_to_update]))
            
            # Fetch candidates to get their actual S3 URLs
            candidates_qs = Candidate.objects.filter(id__in=unique_ids)
            image_url_map = {}
            for candidate in candidates_qs:
                if candidate.profile_image:
                    try:
                        image_url_map[str(candidate.id)] = candidate.profile_image.url
                    except Exception:
                        pass
            
            s3_base = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/"
            
            # Update each item with the actual URL from DB or fallback construction
            for item, cid in items_to_update:
                cid_str = str(cid)
                if cid_str in image_url_map:
                    item['profile_image'] = image_url_map[cid_str]
                elif 'profile_image' in item and item['profile_image'] and not str(item['profile_image']).startswith('http'):
                    item['profile_image'] = s3_base + str(item['profile_image']).lstrip('/')
        
        # Return the processed response
        return Response(data)
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return Response(
                {"error": "No FlitPass data available for this company"},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(
            {"error": f"ML API error: {str(e)}"},
            status=e.response.status_code
        )
        
    except requests.exceptions.RequestException as e:
        return Response(
            {"error": f"Failed to fetch data from ML API: {str(e)}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )