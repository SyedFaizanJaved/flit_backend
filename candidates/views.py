from rest_framework import generics, status, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Candidate, WorkDNA, Reference, ReferenceRequest
from .serializers import (
    CandidateSerializer, CandidateListSerializer, WorkDNASerializer,
    ReferenceSerializer, ReferenceRequestSerializer, CandidateProfileUpdateSerializer
)
from rest_framework.exceptions import PermissionDenied
from accounts.views import BaseRoleRegistrationView
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename
from jobs.models import Job
from projects.models import Project
from jobs.serializers import JobListSerializer
from projects.serializers import ProjectListSerializer
from django.conf import settings
import requests
import os


class CandidateRegistrationView(BaseRoleRegistrationView):
    """Register a new candidate user (role is forced to candidate)."""
    fixed_user_type = "candidate"


class CandidateViewSet(viewsets.ViewSet):
    """ViewSet consolidating candidate endpoints (list, profile, dashboard)."""

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        queryset = Candidate.objects.filter(profile_visibility="public")
        # Apply filters/search/order if the integration is configured on router level
        serializer = CandidateListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard(self, request):
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'profile': CandidateSerializer(candidate).data,
            'profile_completed': candidate.is_profile_complete,
            'applications_count': candidate.job_applications.count() + candidate.project_applications.count(),
            'job_applications_count': candidate.job_applications.count(),
            'project_applications_count': candidate.project_applications.count(),
            'references_count': candidate.references.count(),
            'reference_requests_count': candidate.reference_requests.count(),
        }

        recent_job_apps = list(candidate.job_applications.all())
        recent_project_apps = list(candidate.project_applications.all())
        recent_applications = sorted(
            recent_job_apps + recent_project_apps,
            key=lambda a: a.applied_at,
            reverse=True
        )[:5]
        data['recent_applications'] = [
            {
                'id': app.id,
                'title': app.job.title if getattr(app, 'job', None) else app.project.title,
                'company': app.company.company_name,
                'status': app.status,
                'applied_at': app.applied_at
            }
            for app in recent_applications
        ]

        # Include latest active jobs and projects across all companies
        try:
            limit_param = request.query_params.get('limit')
            limit = int(limit_param) if limit_param is not None else 12
        except ValueError:
            limit = 12

        jobs_qs = Job.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]
        projects_qs = Project.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]

        data['latest_jobs'] = JobListSerializer(jobs_qs, many=True).data
        data['latest_projects'] = ProjectListSerializer(projects_qs, many=True).data

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        # Ensure correct role and fetch/create profile
        if request.user.userType != "candidate":
            raise PermissionDenied("Only candidates can access this endpoint.")

        candidate, _ = Candidate.objects.get_or_create(
            user=request.user,
            defaults={
                'full_name': f"{request.user.first_name} {request.user.last_name}"}
        )

        # For GET requests, return the profile directly
        if request.method == 'GET':
            data = CandidateSerializer(candidate).data
            return Response(data, status=status.HTTP_200_OK)

        # For PUT and PATCH requests
        # Handle uploaded files (multipart/form-data) for resume and video
        data = request.data.copy() if hasattr(request, 'data') else {}

        # Save resume_file if provided and set resume_url
        resume_file = request.FILES.get('resume_file')
        if resume_file:
            try:
                filename = get_valid_filename(resume_file.name)
                storage_path = default_storage.save(f'candidates/resumes/{filename}', resume_file)
                public_url = default_storage.url(storage_path)
                # Build absolute URL so ML services can fetch
                data['resume_url'] = request.build_absolute_uri(public_url)
            except Exception:
                # If saving fails, continue without blocking update
                pass

        # Save video_file if provided and set video_intro_url
        video_file = request.FILES.get('video_file')
        if video_file:
            try:
                filename = get_valid_filename(video_file.name)
                storage_path = default_storage.save(f'candidates/videos/{filename}', video_file)
                public_url = default_storage.url(storage_path)
                data['video_intro_url'] = request.build_absolute_uri(public_url)
            except Exception:
                pass

        serializer = CandidateProfileUpdateSerializer(
            candidate, data=data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # refresh candidate from DB to pick up any changes made by serializer
        try:
            candidate = Candidate.objects.get(pk=candidate.pk)
        except Exception:
            # fallback to existing object if refresh fails
            pass
            
        # Handle video transcription if video was uploaded
        if request.FILES.get('video_file'):
            try:
                # Request transcription from ML service
                transcribe_url = getattr(settings, 'ML_TRANSCRIBE_VIDEO_URL', None) or 'https://dev-flit-ai.neurooceans.com/transcribe_video'
                print(f"Using transcription URL: {transcribe_url}")

                # Set up the headers with API key if available
                headers = {}
                api_key = getattr(settings, 'ML_API_KEY', None) or os.environ.get('ML_API_KEY')
                if api_key:
                    headers['Authorization'] = f'Bearer {api_key}'
                    print("API key is configured")
                else:
                    print("Warning: No API key found")
                
                # Open and read the video file
                try:
                    video_file.seek(0)  # Reset file pointer to beginning
                    video_content = video_file.read()
                    print(f"Read video file content, size: {len(video_content)} bytes")
                except Exception as e:
                    print(f"Error reading video file: {str(e)}")
                    video_content = None
                
                # Create the multipart form data
                files = {
                    'video_file': (video_file.name, video_content if video_content else video_file, video_file.content_type)
                }
                data = {
                    'user_id': str(getattr(request.user, 'id', '')),
                    'transcription_only': 'true',  # Tell the service we only want transcription
                    'video_url': request.build_absolute_uri(candidate.video_intro_url)  # Backup URL in case needed
                }
                
                print(f"Requesting transcription for video: {video_file.name}")
                print(f"Request data: {data}")
                
                try:
                    resp = requests.post(transcribe_url, files=files, data=data, headers=headers, timeout=60)
                    print(f"Request headers: {resp.request.headers}")
                    print(f"Response status: {resp.status_code}")
                    print(f"Response content: {resp.text[:1000]}")
                except requests.RequestException as e:
                    print(f"Error making request: {str(e)}")
                    resp = None
                
                if resp and resp.ok:
                    try:
                        resp_json = resp.json()
                        print(f"Parsed JSON response: {resp_json}")
                        
                        # Get transcription text
                        transcription = None
                        if isinstance(resp_json.get('transcription'), str):
                            transcription = resp_json.get('transcription')
                        elif isinstance(resp_json.get('text'), str):
                            transcription = resp_json.get('text')
                        
                        print(f"Extracted transcription: {transcription[:100] if transcription else 'None'}")
                        
                        if transcription:
                            update_fields = ['updated_at', 'video_transcription']
                            candidate.video_transcription = transcription
                            candidate.intro_video_description = None  # Clear any existing description
                            update_fields.append('intro_video_description')
                            candidate.save(update_fields=update_fields)
                            print(f"Saved updates with fields: {update_fields}")
                        else:
                            print("No transcription or description found in response")
                    except ValueError as e:
                        print(f"Error parsing JSON response: {str(e)}")
                        print(f"Raw response: {resp.text[:1000]}")
                else:
                    if resp:
                        print(f"Transcription failed with status {resp.status_code}")
                        print(f"Response headers: {resp.headers}")
                        print(f"Response body: {resp.text}")
                    else:
                        print("Request failed to complete")
            except Exception as e:
                print(f"Unexpected error during transcription: {str(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")

        data = CandidateSerializer(candidate).data
        return Response(data, status=status.HTTP_200_OK)

    

    @action(detail=False, methods=['get', 'post'], url_path='match', permission_classes=[permissions.AllowAny])
    def match(self, request):
        """
        Return candidates matched by title/search text using the external ML service.
        Accepts:
        - GET params: ?title=... or ?search_text=..., optional repeated params for seniority_list and job_types_list
        - POST JSON: { "search_text": "...", "seniority_list": [..], "job_types_list": [..] }
        """
        if request.method.lower() == 'get':
            search_text = request.query_params.get('search_text') or request.query_params.get(
                'title') or request.query_params.get('q')
            seniority_list = request.query_params.getlist(
                'seniority_list') or None
            job_types_list = request.query_params.getlist(
                'job_types_list') or None
        else:
            data = request.data or {}
            search_text = data.get('search_text') or data.get('title')
            seniority_list = data.get('seniority_list')
            job_types_list = data.get('job_types_list')
            # Fallback to query params if body was not parsed (e.g., missing Content-Type)
            if not search_text:
                search_text = request.query_params.get('search_text') or request.query_params.get(
                    'title') or request.query_params.get('q')
            if not seniority_list:
                seniority_list = request.query_params.getlist(
                    'seniority_list') or None
            if not job_types_list:
                job_types_list = request.query_params.getlist(
                    'job_types_list') or None

        if not search_text:
            return Response({'error': 'search_text or title is required'}, status=status.HTTP_400_BAD_REQUEST)

        ml_success, ml_resp, sent_payload, matched_qs = self._match_candidates_with_ml(
            search_text=search_text,
            seniority_list=seniority_list,
            job_types_list=job_types_list,
        )

        # Fallback to simple title search if ML didn't return identifiable candidates
        if matched_qs.count() == 0:
            matched_qs = Candidate.objects.filter(
                profile_visibility="public", title__icontains=search_text)

        serializer = CandidateListSerializer(matched_qs, many=True)
        response = {
            'results': serializer.data,
            'ml_success': ml_success,
        }

        # Optional debug
        debug_flag = request.query_params.get('ml_debug') or (
            request.data.get('ml_debug') if hasattr(request, 'data') else None)
        ml_debug = str(debug_flag).lower() in [
            '1', 'true', 'yes'] if debug_flag is not None else False
        if ml_debug:
            response['ml_response'] = ml_resp
            response['ml_payload'] = sent_payload

        return Response(response, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='profile/complete/(?P<section>[^/.]+)', permission_classes=[permissions.IsAuthenticated])
    def complete_profile_section(self, request, section=None):
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

        section_fields = {
            'basic_info': 'basic_info_completed',
            'work_preferences': 'work_preferences_completed',
            'skills': 'skills_completed',
            'portfolio': 'portfolio_completed',
            'privacy': 'privacy_completed',
        }

        if section not in section_fields:
            return Response({'error': 'Invalid section'}, status=status.HTTP_400_BAD_REQUEST)

        setattr(candidate, section_fields[section], True)
        candidate.save()

        # Ensure the user's profile_completed flag reflects the candidate profile state
        try:
            user = candidate.user
            if candidate.is_profile_complete != getattr(user, 'profile_completed', False):
                user.profile_completed = candidate.is_profile_complete
                user.save(update_fields=['profile_completed'])
        except Exception:
            # Do not block the response if user sync fails
            pass

        return Response({
            'message': f'{section} section marked as complete',
            'profile_completed': candidate.is_profile_complete
        }, status=status.HTTP_200_OK)


class WorkDNAView(generics.RetrieveUpdateAPIView):
    """
    Work DNA assessment view
    """
    serializer_class = WorkDNASerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        try:
            return self.request.user.candidate_profile.work_dna
        except WorkDNA.DoesNotExist:
            return None
    
    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)


class ReferenceListView(generics.ListCreateAPIView):
    """
    Reference list and create view
    """
    serializer_class = ReferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Reference.objects.filter(candidate__user=self.request.user)
    
    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)


class ReferenceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Reference detail view
    """
    serializer_class = ReferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Reference.objects.filter(candidate__user=self.request.user)


class ReferenceRequestListView(generics.ListCreateAPIView):
    """
    Reference request list and create view
    """
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)
    
    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)


class ReferenceRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Reference request detail view
    """
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)
