import json
import logging
import os
import requests
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Case, Q, When, F
from django.utils.text import get_valid_filename
from rest_framework import generics, permissions, status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from accounts.views import BaseRoleRegistrationView
from jobs.models import Job
from jobs.serializers import JobListSerializer
from projects.models import Project
from projects.serializers import ProjectListSerializer
from companies.models import Company
from employers.models import Employer
from .models import Candidate, Reference, ReferenceRequest, WorkDNA
from .serializers import (
    CandidateListSerializer,
    CandidateProfileUpdateSerializer,
    CandidateSerializer,
    ReferenceRequestSerializer,
    ReferenceSerializer,
    WorkDNASerializer,
    CompanyWithOpeningsSerializer,
)

class CandidateRegistrationView(BaseRoleRegistrationView):
    """Register a new candidate user (role is forced to candidate)."""
    fixed_user_type = "candidate"

class CandidateViewSet(viewsets.ViewSet):
    """ViewSet consolidating candidate endpoints (list, profile, dashboard)."""
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    permission_classes = [permissions.AllowAny]

    def _get_candidate_profile(self, user):
        try:
            return user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

    def _save_file(self, file_obj, storage_path_prefix, request):
        try:
            filename = get_valid_filename(file_obj.name)
            storage_path = default_storage.save(f'{storage_path_prefix}/{filename}', file_obj)
            public_url = default_storage.url(storage_path)
            return request.build_absolute_uri(public_url)
        except Exception:
            return None

    def retrieve(self, request, pk=None):
        try:
            candidate = Candidate.objects.get(pk=pk, profile_visibility="public")
        except Candidate.DoesNotExist:
            return Response(
                {"detail": "Candidate not found or profile is not public"},
                status=status.HTTP_404_NOT_FOUND
            )
        if hasattr(request.user, 'employer_profile'):
            employer = request.user.employer_profile
            viewers_list = list(candidate.viewers or [])
            if employer.id not in viewers_list:
                candidate.profile_views = (candidate.profile_views or 0) + 1
                viewers_list.append(employer.id)
                candidate.viewers = viewers_list
                candidate.save(update_fields=['profile_views', 'viewers', 'updated_at'])
        serializer = CandidateSerializer(candidate, context={'request': request})
        return Response(serializer.data)

    def list(self, request):
        queryset = Candidate.objects.filter(profile_visibility="public")
        serializer = CandidateListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='views')
    def record_view(self, request, pk=None):
        try:
            employer = request.user.employer_profile
        except Exception:
            raise PermissionDenied("Only employers can record candidate profile views.")
        try:
            candidate = Candidate.objects.get(pk=pk)
        except Candidate.DoesNotExist:
            return Response({"error": "Candidate not found"}, status=status.HTTP_404_NOT_FOUND)
        candidate.refresh_from_db(fields=['profile_views', 'viewers'])
        viewers_list = list(candidate.viewers or [])
        already_viewed = employer.id in viewers_list
        if not already_viewed:
            Candidate.objects.filter(pk=candidate.pk).update(profile_views=F('profile_views') + 1)
            candidate.refresh_from_db(fields=['profile_views'])
            viewers_list.append(employer.id)
            candidate.viewers = viewers_list
            candidate.save(update_fields=['viewers', 'updated_at'])
        return Response({
            'candidate_id': candidate.id,
            'profile_views': candidate.profile_views,
            'viewers_count': len(candidate.viewers or []),
            'already_viewed': already_viewed
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard(self, request):
        candidate = self._get_candidate_profile(request.user)
        if isinstance(candidate, Response):
            return candidate
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
        if getattr(getattr(request.user, 'role', None), 'name', None) != "candidate":
            raise PermissionDenied("Only candidates can access this endpoint.")
        candidate, _ = Candidate.objects.get_or_create(
            user=request.user,
            defaults={'full_name': f"{request.user.first_name} {request.user.last_name}"}
        )
        if request.method == 'GET':
            data = CandidateSerializer(candidate).data
            return Response(data, status=status.HTTP_200_OK)
        try:
            if hasattr(request, 'data') and hasattr(request.data, 'dict'):
                data = request.data.dict()
            else:
                data = request.data if hasattr(request, 'data') else {}
        except Exception:
            data = request.POST.copy() if hasattr(request, 'POST') else {}
        def parse_bool(v):
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ['true', '1', 'yes']
            return bool(v)
        def parse_int(v):
            try:
                return int(v)
            except Exception:
                return None
        def parse_json_list(v):
            if v is None:
                return []
            if isinstance(v, (list, tuple)):
                return list(v)
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    return parsed if isinstance(parsed, list) else []
                except Exception:
                    return []
            return []
        for key in ['skills', 'superpowers', 'preferred_roles', 'portfolio_links']:
            if key in data:
                data[key] = parse_json_list(data.get(key))
        for key in ['is_remote', 'is_available']:
            if key in data:
                data[key] = parse_bool(data.get(key))
        for key in ['min_salary', 'max_salary']:
            if key in data and data.get(key) not in [None, '']:
                parsed = parse_int(data.get(key))
                if parsed is not None:
                    data[key] = parsed
        resume_file = request.FILES.get('resume_file')
        if resume_file:
            data['resume_url'] = self._save_file(resume_file, 'candidates/resumes', request)
        video_file = request.FILES.get('video_file')
        if video_file:
            data['video_intro_url'] = self._save_file(video_file, 'candidates/videos', request)
        serializer = CandidateProfileUpdateSerializer(
            candidate, data=data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        try:
            candidate = Candidate.objects.get(pk=candidate.pk)
        except Exception:
            pass
        if request.FILES.get('video_file'):
            try:
                transcribe_url = getattr(settings, 'ML_TRANSCRIBE_VIDEO_URL', 'https://dev-flit-ai.neurooceans.com/transcribe_video')
                headers = {}
                api_key = getattr(settings, 'ML_API_KEY', None) or os.environ.get('ML_API_KEY')
                if api_key:
                    headers['Authorization'] = f'Bearer {api_key}'
                video_file.seek(0)
                video_content = video_file.read()
                files = {
                    'video_file': (video_file.name, video_content, video_file.content_type)
                }
                data = {
                    'user_id': str(getattr(request.user, 'id', '')),
                    'transcription_only': 'true',
                    'video_url': request.build_absolute_uri(candidate.video_intro_url)
                }
                resp = requests.post(transcribe_url, files=files, data=data, headers=headers, timeout=60)
                if resp and resp.ok:
                    resp_json = resp.json()
                    transcription = None
                    if isinstance(resp_json.get('transcription'), str):
                        transcription = resp_json.get('transcription')
                    elif isinstance(resp_json.get('text'), str):
                        transcription = resp_json.get('text')
                    if transcription:
                        update_fields = ['updated_at', 'video_transcription']
                        candidate.video_transcription = transcription
                        candidate.intro_video_description = None
                        update_fields.append('intro_video_description')
                        candidate.save(update_fields=update_fields)
            except Exception as e:
                print(f"Unexpected error during transcription: {str(e)}")
        data = CandidateSerializer(candidate).data
        return Response(data, status=status.HTTP_200_OK)

    def _match_candidates(self, search_text, seniority_list, job_types_list):
        sent_payload = {
            'search_text': search_text,
            'seniority_list': seniority_list or [],
            'job_types_list': job_types_list or []
        }
        payload = {
            'search_text': search_text,
            'filters': {}
        }
        if seniority_list:
            payload['filters']['seniority'] = seniority_list
        if job_types_list:
            payload['filters']['job_types'] = job_types_list
        success = False
        ml_resp = {}
        matched_qs = Candidate.objects.none()
        try:
            ml_service_url = 'https://dev-flit-ai.neurooceans.com/match_candidates_for_job'
            headers = {'Content-Type': 'application/json'}
            response = requests.post(ml_service_url, data=json.dumps(payload), headers=headers)
            ml_resp = response.json()
            success = response.status_code == 200
            matched_candidate_ids = []
            if success and 'matches' in ml_resp:
                matched_candidate_ids = [match.get('candidate_id') for match in ml_resp['matches'] if match.get('candidate_id')]
            base_qs = Candidate.objects.filter(profile_visibility="public")
            if matched_candidate_ids:
                preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(matched_candidate_ids)])
                matched_qs = base_qs.filter(id__in=matched_candidate_ids).order_by(preserved)
            else:
                matched_qs = base_qs.filter(
                    Q(title__icontains=search_text) |
                    Q(skills__icontains=search_text) |
                    Q(bio__icontains=search_text) |
                    Q(experience__description__icontains=search_text)
                ).distinct()
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error calling ML service: {str(e)}")
            matched_qs = Candidate.objects.filter(profile_visibility="public").filter(
                Q(title__icontains=search_text) |
                Q(skills__icontains=search_text) |
                Q(bio__icontains=search_text) |
                Q(experience__description__icontains=search_text)
            ).distinct()
            ml_resp = {'error': str(e)}
        return matched_qs, success, ml_resp, sent_payload

    @action(detail=False, methods=['get', 'post'], url_path='match', permission_classes=[permissions.AllowAny])
    def match(self, request):
        if request.method.lower() == 'get':
            search_text = request.query_params.get('search_text') or request.query_params.get('title') or request.query_params.get('q')
            seniority_list = request.query_params.getlist('seniority_list') or None
            job_types_list = request.query_params.getlist('job_types_list') or None
        else:
            data = request.data or {}
            search_text = data.get('search_text') or data.get('title')
            seniority_list = data.get('seniority_list')
            job_types_list = data.get('job_types_list')
            if not search_text:
                search_text = request.query_params.get('search_text') or request.query_params.get('title') or request.query_params.get('q')
            if not seniority_list:
                seniority_list = request.query_params.getlist('seniority_list') or None
            if not job_types_list:
                job_types_list = request.query_params.getlist('job_types_list') or None
        if not search_text:
            return Response({'error': 'search_text or title is required'}, status=status.HTTP_400_BAD_REQUEST)
        matched_qs, success, ml_resp, sent_payload = self._match_candidates(search_text, seniority_list, job_types_list)
        if matched_qs.count() == 0:
            matched_qs = Candidate.objects.filter(profile_visibility="public", title__icontains=search_text)
        serializer = CandidateListSerializer(matched_qs, many=True)
        response_data = {
            'results': serializer.data,
            'ml_success': success,
        }
        debug_flag = request.query_params.get('ml_debug') or (request.data.get('ml_debug') if hasattr(request, 'data') else None)
        ml_debug = str(debug_flag).lower() in ['1', 'true', 'yes'] if debug_flag is not None else False
        if ml_debug:
            response_data['ml_response'] = ml_resp
            response_data['ml_payload'] = sent_payload
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='companies/openings')
    def companies_with_openings(self, request):
        q = request.query_params.get('q', '').strip()
        industry = request.query_params.get('industry')
        company_id = request.query_params.get('company_id')
        companies_qs = Company.objects.filter(is_active=True)
        if industry:
            companies_qs = companies_qs.filter(industry__iexact=industry)
        if q:
            companies_qs = companies_qs.filter(
                Q(company_name__icontains=q) | Q(industry__icontains=q) | Q(location__icontains=q)
            )
        user = request.user if hasattr(request, 'user') else None
        if getattr(user, 'is_authenticated', False):
            role = getattr(getattr(user, 'role', None), 'name', None)
            if role == getattr(settings, 'USER_ROLE_EMPLOYER', 'employer'):
                try:
                    employer = user.employer_profile
                    if employer.company_id:
                        companies_qs = companies_qs.filter(id=employer.company_id)
                    else:
                        companies_qs = Company.objects.none()
                except Employer.DoesNotExist:
                    companies_qs = Company.objects.none()
        companies_qs = companies_qs.distinct().order_by('-created_at')
        serializer = CompanyWithOpeningsSerializer(companies_qs, many=True, context={'request': request})
        return Response({
            'count': companies_qs.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='profile/complete/(?P<section>[^/.]+)', permission_classes=[permissions.IsAuthenticated])
    def complete_profile_section(self, request, section=None):
        candidate = self._get_candidate_profile(request.user)
        if isinstance(candidate, Response):
            return candidate
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
        try:
            user = candidate.user
            if candidate.is_profile_complete != getattr(user, 'profile_completed', False):
                user.profile_completed = candidate.is_profile_complete
                user.save(update_fields=['profile_completed'])
        except Exception:
            pass
        return Response({
            'message': f'{section} section marked as complete',
            'profile_completed': candidate.is_profile_complete
        }, status=status.HTTP_200_OK)

class WorkDNAView(APIView):
    """Work DNA assessment view."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            obj = request.user.candidate_profile.work_dna
        except WorkDNA.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)

        serializer = WorkDNASerializer(obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Upsert: create if missing, otherwise partial update
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            obj = candidate.work_dna
        except WorkDNA.DoesNotExist:
            obj = None

        if obj is None:
            serializer = WorkDNASerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save(candidate=candidate)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            serializer = WorkDNASerializer(obj, data=request.data, partial=True, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        # Upsert on PATCH as well
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request):
        try:
            obj = request.user.candidate_profile.work_dna
        except WorkDNA.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)

        serializer = WorkDNASerializer(obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Upsert: create if missing, otherwise partial update
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            obj = candidate.work_dna
        except WorkDNA.DoesNotExist:
            obj = None

        if obj is None:
            serializer = WorkDNASerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save(candidate=candidate)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            serializer = WorkDNASerializer(obj, data=request.data, partial=True, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        # Upsert on PATCH as well
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            obj = candidate.work_dna
        except WorkDNA.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)
        serializer = WorkDNASerializer(obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        try:
            candidate = request.user.candidate_profile
        except Candidate.DoesNotExist:
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            obj = candidate.work_dna
        except WorkDNA.DoesNotExist:
            obj = None
        if obj is None:
            serializer = WorkDNASerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save(candidate=candidate)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            serializer = WorkDNASerializer(obj, data=request.data, partial=True, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

class ReferenceListView(generics.ListCreateAPIView):
    """Reference list and create view."""
    serializer_class = ReferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reference.objects.filter(candidate__user=self.request.user)

    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)

class ReferenceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Reference detail view."""
    serializer_class = ReferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reference.objects.filter(candidate__user=self.request.user)

class ReferenceRequestListView(generics.ListCreateAPIView):
    """Reference request list and create view."""
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)

    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)

class ReferenceRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Reference request detail view."""
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)