import io
import json
import logging
import os
import re
import time
import threading
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q, F, Count, Case, When, Value, IntegerField, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, generics, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied, NotFound
from utils.pagination import CustomPagination
from utils.file_validators import (
    resume_upload_path, video_upload_path, image_upload_path, document_upload_path
)
from utils.pdf_generator import generate_pdf_from_cv_data
from .serializers import AchievementSerializer
from .models import Education, Experience, Achievement        
from projects.models import Project
from projects.serializers import ProjectListSerializer
from jobs.models import Job
from jobs.serializers import JobListSerializer
from applications.models import JobApplication as Application, ProjectApplication, InterviewRequest
from vr_meet.models import Offer
from django.db.models import Q, Value, IntegerField, Case, When, F

from accounts.views import BaseRoleRegistrationView

from .models import Candidate, ReferenceRequest, WorkDNAQuestion
from .serializers import (
    CandidateSerializer,
    CandidateListSerializer,
    ReferenceRequestSerializer,
    WorkDNAQuestionSerializer,
    DiscoverTalentSerializer,
    AchievementSerializer,
)
from employers.models import CandidateAction
from employers.serializers import CandidateFlittedCompanySerializer

logger = logging.getLogger(__name__)
exception_logger = logging.getLogger("exceptions")


class CandidateAccessMixin:
    def get_candidate(self):
        try:
            return self.request.user.candidate_profile
        except AttributeError:
            raise PermissionDenied("Authentication required.")
        except Candidate.DoesNotExist:
            raise NotFound("Candidate profile not found.")


class PublicJobListAPIView(generics.ListAPIView):
    queryset = Job.objects.filter(status='active')
    serializer_class = JobListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = CustomPagination  
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title']
    ordering_fields = ['created_at', 'salary_min', 'salary_max']
    filterset_fields = {
        'job_type': ['exact'],
        'work_style': ['exact'],
        'education_level': ['exact'],
        'is_remote': ['exact'],
    }


class PublicProjectListAPIView(generics.ListAPIView):
    queryset = Project.objects.filter(status='active')
    serializer_class = ProjectListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = CustomPagination  
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title']
    ordering_fields = ['created_at', 'budget', 'deadline']
    filterset_fields = {
        'project_type': ['exact'],
        'complexity': ['exact'],
        'work_style': ['exact'],
        'collaboration_style': ['exact'],
    }

class CandidateRegistrationView(BaseRoleRegistrationView):
    fixed_user_type = "candidate"


# ==================== REFERENCE REQUEST VIEWSET ====================
class ReferenceRequestViewSet(CandidateAccessMixin, viewsets.ModelViewSet):
    serializer_class = ReferenceRequestSerializer
    pagination_class = CustomPagination

    def get_permissions(self):
        if self.action == 'retrieve':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        unread_count = queryset.filter(is_read=False).count()
        queryset.filter(is_read=False).update(is_read=True)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response({
                'count': self.paginator.page.paginator.count,
                'unread_count': unread_count,
                'next': self.paginator.get_next_link(),
                'previous': self.paginator.get_previous_link(),
                'total_pages': self.paginator.page.paginator.num_pages,
                'current_page': self.paginator.page.number,
                'results': serializer.data
            })
            
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'unread_count': unread_count,
            'results': serializer.data
        })

    def perform_create(self, serializer):
        serializer.save(candidate=self.get_candidate())


# ==================== MAIN CANDIDATE VIEWSET ====================
# ========================= BACKGROUND FILE + ML PROCESSOR =========================

def _process_files_and_ml_in_background(
    candidate_id,
    resume_info=None,     # dict: {bytes, name, content_type, upload_path}
    video_info=None,      # dict: {bytes, name, content_type, upload_path, user_id}
    profile_image_info=None,  # dict: {bytes, name, content_type}
    old_resume_path=None,
    old_video_path=None,
    old_profile_image_path=None,
    ml_payload=None,
    build_absolute_uri_base=None,
):
    """
    Single background thread that handles ALL heavy I/O:
      1. Upload files to S3
      2. Parse resume via ML
      3. Analyze video via ML
      4. Sync candidate data to ML
    Updates candidate fields as each step completes.
    """
    from .models import Candidate
    from django.utils import timezone as tz
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django.core.cache import cache

    errors = []
    candidate_updates = {}
    cache_key = f"candidate_processing_{candidate_id}"

    def _delete_old_file(file_path):
        """Delete old file from S3 if it exists."""
        if file_path:
            try:
                name = file_path.name if hasattr(file_path, 'name') else str(file_path)
                if name and default_storage.exists(name):
                    default_storage.delete(name)
                    logger.info(f"[BG] Deleted old file from S3: {name}")
            except Exception as e:
                logger.error(f"[BG] Failed to delete old file {file_path}: {e}")

    try:
        # Mark as processing in cache (10 min TTL)
        cache.set(cache_key, {'status': 'processing', 'error': None}, timeout=600)

        # ---------- STEP 1: S3 File Uploads ----------

        # 1a. Profile image upload
        if profile_image_info:
            try:
                _delete_old_file(old_profile_image_path)
                from utils.file_validators import image_upload_path
                path = image_upload_path(None, profile_image_info['name'])
                default_storage.save(path, ContentFile(profile_image_info['bytes']))
                candidate_updates['profile_image'] = path
                logger.info(f"[BG] Profile image uploaded to S3 for candidate {candidate_id}")
            except Exception as e:
                errors.append(f"Profile image upload: {e}")
                logger.error(f"[BG] Profile image upload failed for candidate {candidate_id}: {e}", exc_info=True)

        # 1b. Resume upload
        resume_s3_path = None
        if resume_info:
            try:
                _delete_old_file(old_resume_path)
                path = resume_info['upload_path']
                default_storage.save(path, ContentFile(resume_info['bytes']))
                candidate_updates['resume_url'] = path
                candidate_updates['portfolio_completed'] = True
                resume_s3_path = path
                logger.info(f"[BG] Resume uploaded to S3 for candidate {candidate_id}")
            except Exception as e:
                errors.append(f"Resume upload: {e}")
                logger.error(f"[BG] Resume upload failed for candidate {candidate_id}: {e}", exc_info=True)

        # 1c. Video upload
        video_s3_path = None
        if video_info:
            try:
                _delete_old_file(old_video_path)
                path = video_info['upload_path']
                default_storage.save(path, ContentFile(video_info['bytes']))
                candidate_updates['video_intro_url'] = path
                candidate_updates['portfolio_completed'] = True
                video_s3_path = path
                logger.info(f"[BG] Video uploaded to S3 for candidate {candidate_id}")
            except Exception as e:
                errors.append(f"Video upload: {e}")
                logger.error(f"[BG] Video upload failed for candidate {candidate_id}: {e}", exc_info=True)

        # Flush S3 paths to DB so they're visible immediately
        if candidate_updates:
            candidate_updates['updated_at'] = tz.now()
            Candidate.objects.filter(id=candidate_id).update(**candidate_updates)
            logger.info(f"[BG] S3 paths saved to DB for candidate {candidate_id}")

        # ---------- STEP 2: ML Resume Parse ----------
        if resume_info:
            try:
                files_ml = {
                    'resume_file': (
                        resume_info['name'],
                        io.BytesIO(resume_info['bytes']),
                        resume_info['content_type'],
                    )
                }
                parse_url = f"{settings.FLIT_AI_URL}/parse_cv"
                resp = requests.post(parse_url, files=files_ml, timeout=120)
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get('success'):
                        Candidate.objects.filter(id=candidate_id).update(
                            resume_data=result.get('data', {})
                        )
                        logger.info(f"[BG] Resume parsed successfully for candidate {candidate_id}")
                    else:
                        logger.warning(f"[BG] Resume parse returned success=False for candidate {candidate_id}")
                else:
                    logger.error(f"[BG] Resume parsing failed with status {resp.status_code} for candidate {candidate_id}")
            except Exception as e:
                errors.append(f"Resume parse: {e}")
                logger.error(f"[BG] Resume parsing exception for candidate {candidate_id}: {e}", exc_info=True)

        # ---------- STEP 3: ML Video Analysis ----------
        if video_info:
            try:
                analyze_url = f"{settings.FLIT_AI_URL}/analyze_intro_video"
                files_video = {
                    'video_file': (
                        video_info['name'],
                        io.BytesIO(video_info['bytes']),
                        video_info['content_type'],
                    )
                }
                video_url = ''
                if build_absolute_uri_base and video_s3_path:
                    try:
                        video_url = f"{build_absolute_uri_base}{default_storage.url(video_s3_path)}"
                    except Exception:
                        video_url = video_s3_path or ''

                video_payload = {
                    'user_id': str(video_info['user_id']),
                    'candidate_id': str(candidate_id),
                    'video_url': video_url,
                }
                headers = {}
                if hasattr(settings, 'ML_API_KEY'):
                    headers["Authorization"] = f"Bearer {settings.ML_API_KEY}"
                resp = requests.post(analyze_url, files=files_video, data=video_payload, headers=headers, timeout=180)
                if resp.status_code == 200:
                    analysis = resp.json().get('analysis', {})
                    update_fields = {}
                    if transcription := analysis.get('video_transcript'):
                        update_fields['video_transcription'] = transcription
                    if analysis:
                        update_fields['intro_video_description'] = analysis
                    if update_fields:
                        Candidate.objects.filter(id=candidate_id).update(**update_fields)
                        logger.info(f"[BG] Video analyzed successfully for candidate {candidate_id}")
                else:
                    logger.error(f"[BG] Video analysis failed with status {resp.status_code} for candidate {candidate_id}")
            except Exception as e:
                errors.append(f"Video analysis: {e}")
                logger.error(f"[BG] Video analysis exception for candidate {candidate_id}: {e}", exc_info=True)

        # ---------- STEP 4: ML Sync ----------
        if ml_payload:
            try:
                # Refresh URLs in payload if we just uploaded new files
                if resume_s3_path:
                    try:
                        ml_payload['resume_url'] = f"{build_absolute_uri_base}{default_storage.url(resume_s3_path)}" if build_absolute_uri_base else resume_s3_path
                    except Exception:
                        ml_payload['resume_url'] = resume_s3_path or ''
                if video_s3_path:
                    try:
                        ml_payload['video_intro_url'] = f"{build_absolute_uri_base}{default_storage.url(video_s3_path)}" if build_absolute_uri_base else video_s3_path
                    except Exception:
                        ml_payload['video_intro_url'] = video_s3_path or ''

                headers = {"Content-Type": "application/json"}
                if hasattr(settings, 'ML_API_KEY'):
                    headers["Authorization"] = f"Bearer {settings.ML_API_KEY}"

                update_url = f"{settings.FLIT_AI_URL}/update_candidate_data/{candidate_id}"
                create_url = f"{settings.FLIT_AI_URL}/create_candidates/{candidate_id}"

                resp = requests.patch(update_url, json=ml_payload, headers=headers)

                if resp.status_code == 404:
                    logger.info(f"[BG] Candidate {candidate_id} not in ML, creating new")
                    resp = requests.post(create_url, json=ml_payload, headers=headers)

                if resp.status_code not in (200, 201):
                    logger.error(f"[BG] ML sync failed: {resp.status_code} - {resp.text[:500]}")
                else:
                    logger.info(f"[BG] ML sync successful ({resp.status_code}) for candidate {candidate_id}")
                    ml_data = resp.json()
                    ml_updates = {}
                    if ml_data.get('candidate_profile_summary'):
                        ml_updates['candidate_profile_summary'] = ml_data['candidate_profile_summary']
                    if ml_data.get('candidate_tags'):
                        ml_updates['candidate_tags'] = ml_data['candidate_tags']
                    if ml_updates:
                        ml_updates['updated_at'] = tz.now()
                        Candidate.objects.filter(id=candidate_id).update(**ml_updates)
            except Exception as e:
                errors.append(f"ML sync: {e}")
                logger.error(f"[BG] ML sync exception for candidate {candidate_id}: {e}", exc_info=True)

        # ---------- DONE — mark status in cache ----------
        if errors:
            cache.set(cache_key, {'status': 'failed', 'error': '; '.join(errors)}, timeout=600)
            logger.warning(f"[BG] Processing completed with errors for candidate {candidate_id}: {errors}")
        else:
            cache.set(cache_key, {'status': 'completed', 'error': None}, timeout=600)
            logger.info(f"[BG] All processing completed successfully for candidate {candidate_id}")

    except Exception as e:
        logger.error(f"[BG] Fatal processing error for candidate {candidate_id}: {e}", exc_info=True)
        try:
            cache.set(cache_key, {'status': 'failed', 'error': str(e)}, timeout=600)
        except Exception:
            pass


# =======================================================================

class CandidateViewSet(CandidateAccessMixin, viewsets.ModelViewSet):
    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    pagination_class = CustomPagination

    def get_object(self):
        if self.request.parser_context.get('kwargs', {}).get('pk') == 'profile':
            return self.get_candidate()
        return super().get_object()

    def _save_file(self, file_obj, upload_path_func):
        try:
            path = upload_path_func(None, file_obj.name)
            default_storage.save(path, file_obj)
            return path
        except Exception as e:
            exception_logger.exception(f"File save failed: {e}")
            return None

    # ====================== RETRIEVE (public/private profile view) ======================
    def retrieve(self, request, pk=None):
        try:
            if not pk:
                return Response({"error": "Candidate ID is required"}, status=400)

            candidate = Candidate.objects.filter(
                Q(pk=pk) &
                (Q(profile_visibility="public") | Q(user=request.user))
            ).select_related('user').first()

            if not candidate:
                candidate = Candidate.objects.filter(
                    Q(user__id=pk) &
                    (Q(profile_visibility="public") | Q(user=request.user))
                ).select_related('user').first()

            if not candidate:
                return Response({
                    "error": "Candidate not found or you don't have permission to view this profile"
                }, status=404)

            # Track profile view
            try:
                if (hasattr(request.user, 'employer_profile') and
                    (not hasattr(request.user, 'candidate_profile') or candidate.user_id != request.user.id)):
                    with transaction.atomic():
                        candidate.refresh_from_db()
                        viewer_ids = list(candidate.viewers or [])
                        if request.user.employer_profile.id not in viewer_ids:
                            viewer_ids.append(request.user.employer_profile.id)
                            candidate.viewers = viewer_ids
                            candidate.profile_views = (candidate.profile_views or 0) + 1
                            candidate.save(update_fields=['profile_views', 'viewers', 'updated_at'])
            except Exception as view_error:
                exception_logger.error(f"Error updating profile views: {str(view_error)}", exc_info=True)

            serializer = CandidateSerializer(candidate, context={'request': request})
            return Response(serializer.data)

        except Exception as e:
            exception_logger.error(f"Unexpected error in candidate retrieve: {str(e)}", exc_info=True)
            return Response({"error": "An unexpected error occurred"}, status=500)

    # ====================== PROFILE (own profile GET/PATCH/PUT) ======================
    @action(detail=False, methods=['get', 'patch', 'put'], url_path='profile')
    def profile(self, request):
        candidate = self.get_candidate()

        if request.method == 'GET':
            serializer = self.get_serializer(candidate)
            return Response(serializer.data)

        data = request.data
        files = request.FILES
        updated_fields = []
        
        # Debug logging for files
        logger.info(f"Received files: {list(files.keys())}")
        for key, file_obj in files.items():
            logger.info(f"File key: {key}, name: {file_obj.name}, size: {file_obj.size}")
        
        # Debug logging for request data
        logger.info(f"Request data keys: {list(data.keys())}")
        for key, value in data.items():
            if key in ['education', 'experience', 'achievements']:
                logger.info(f"Data key: {key}, value type: {type(value)}, first 100 chars: {str(value)[:100]}")
            elif key.startswith('achievement_image_'):
                logger.info(f"Data key: {key}, value: {value}")
            else:
                logger.info(f"Data key: {key}, value: {value}")

        def to_boolean(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                cleaned = value.strip().lower().replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
                if cleaned in ('true', '1', 'yes', 'on', 't', '"true"', "'true'"):
                    return True
                if cleaned in ('false', '0', 'no', 'off', 'f', '"false"', "'false'"):
                    return False
            logger.warning(f"Invalid boolean value received: {value}")
            return None

        def parse_json_list(value):
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                    return [parsed]
                except json.JSONDecodeError:
                    logger.warning(f"JSON parse failed for list field: {value}")
                    cleaned = value.strip()
                    if cleaned.startswith('[') and cleaned.endswith(']'):
                        cleaned = cleaned[1:-1]
                    items = [item.strip().strip('"').strip("'") for item in cleaned.split(',') if item.strip()]
                    return items if items else []
            return []

        def get_file_url(field):
            if field and hasattr(field, 'url'):
                try:
                    return request.build_absolute_uri(field.url)
                except:
                    return field.url if field.url else ""
            return ""

        def delete_old_file(old_field):
            if old_field and hasattr(old_field, 'name') and old_field.name:
                try:
                    if default_storage.exists(old_field.name):
                        default_storage.delete(old_field.name)
                        logger.info(f"Deleted old file from S3: {old_field.name}")
                except Exception as e:
                    logger.error(f"Failed to delete old file {old_field.name}: {e}")

        list_fields = ['skills', 'superpowers', 'preferred_roles', 'portfolio_links']
        boolean_fields = ['is_available']

        # Video deletion (keep synchronous — it's just a DB field clear + S3 delete)
        if data.get('remove_old_video') == 'true':
            if candidate.video_intro_url:
                delete_old_file(candidate.video_intro_url)
                candidate.video_intro_url = None
                candidate.video_transcription = None
                candidate.intro_video_description = {}
                updated_fields.extend(['video_intro_url', 'video_transcription', 'intro_video_description'])

        # ---- Capture file bytes into memory (instant) — actual S3 upload deferred to background ----
        bg_resume_info = None
        bg_video_info = None
        bg_profile_image_info = None
        old_resume_path = None
        old_video_path = None
        old_profile_image_path = None
        has_file_uploads = False

        if 'profile_image' in files:
            profile_img = files['profile_image']
            old_profile_image_path = candidate.profile_image.name if candidate.profile_image and hasattr(candidate.profile_image, 'name') else None
            bg_profile_image_info = {
                'bytes': profile_img.read(),
                'name': profile_img.name,
                'content_type': profile_img.content_type,
            }
            has_file_uploads = True
            logger.info(f"Profile image bytes captured ({len(bg_profile_image_info['bytes'])} bytes) for background upload")

        if 'resume_file' in files or 'resume' in files:
            resume_file = files.get('resume_file') or files.get('resume')
            old_resume_path = candidate.resume_url.name if candidate.resume_url and hasattr(candidate.resume_url, 'name') else None
            upload_path = resume_upload_path(None, resume_file.name)
            resume_file.seek(0)
            bg_resume_info = {
                'bytes': resume_file.read(),
                'name': resume_file.name,
                'content_type': resume_file.content_type,
                'upload_path': upload_path,
            }
            # Set completion flag now (S3 upload happens in background)
            candidate.portfolio_completed = True
            updated_fields.append('portfolio_completed')
            has_file_uploads = True
            logger.info(f"Resume bytes captured ({len(bg_resume_info['bytes'])} bytes) for background upload")

        if 'video_file' in files:
            video_file = files['video_file']
            old_video_path = candidate.video_intro_url.name if candidate.video_intro_url and hasattr(candidate.video_intro_url, 'name') else None
            upload_path = video_upload_path(None, video_file.name)
            video_file.seek(0)
            bg_video_info = {
                'bytes': video_file.read(),
                'name': video_file.name,
                'content_type': video_file.content_type,
                'upload_path': upload_path,
                'user_id': request.user.id,
            }
            # Set completion flag now (S3 upload happens in background)
            candidate.portfolio_completed = True
            updated_fields.append('portfolio_completed')
            has_file_uploads = True
            logger.info(f"Video bytes captured ({len(bg_video_info['bytes'])} bytes) for background upload")

        # Text & list fields
        text_fields = [
            'full_name', 'title', 'bio', 'location', 'work_style', 'availability_type', 'is_available',
            'skills', 'superpowers', 'preferred_roles', 'portfolio_links', 'profile_visibility',
            'min_salary', 'max_salary', 'salary_currency', 'seniority_level', 'passion_projects','candidate_profile_summary'
        ]
        for field in text_fields:
            if field in data:
                value = data[field]
                if field in list_fields:
                    cleaned = parse_json_list(value)
                    setattr(candidate, field, cleaned)
                    updated_fields.append(field)
                elif field in boolean_fields:
                    converted = to_boolean(value)
                    if converted is not None:
                        setattr(candidate, field, converted)
                        updated_fields.append(field)
                else:
                    if field in ['min_salary', 'max_salary']:
                        try:
                            value = float(value) if value and '.' in str(value) else int(value) if value else None
                        except:
                            value = None
                    setattr(candidate, field, value)
                    updated_fields.append(field)

        # Completion flags
        if any(k in data for k in ['full_name', 'title', 'bio', 'location']):
            candidate.basic_info_completed = True
            updated_fields.append('basic_info_completed')
        if any(k in data for k in ['work_style', 'availability_type', 'is_available']):
            candidate.work_preferences_completed = True
            updated_fields.append('work_preferences_completed')
        if any(k in data for k in ['skills', 'superpowers', 'preferred_roles']):
            candidate.skills_completed = True
            updated_fields.append('skills_completed')
        if files or 'portfolio_links' in data:
            candidate.portfolio_completed = True
            updated_fields.append('portfolio_completed')
        if any(k in data for k in ['profile_visibility', 'video_visibility', 'contact_visibility', 'salary_visibility']):
            candidate.privacy_completed = True
            updated_fields.append('privacy_completed')

        # Handle user_timezone update on the User model
        if 'user_timezone' in data:
            tz_value = data['user_timezone'].strip() if isinstance(data['user_timezone'], str) else data['user_timezone']
            try:
                import zoneinfo
                zoneinfo.ZoneInfo(tz_value)  # Validate timezone
                request.user.user_timezone = tz_value
                request.user.save(update_fields=['user_timezone'])
                logger.info(f"Updated user timezone to {tz_value}")
            except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                logger.warning(f"Invalid timezone value: {tz_value}")

        def _payload_for_model(item, exclude=('id', 'pk', 'created_at', 'updated_at', 'candidate')):
            """Build kwargs for create/update from payload, excluding meta keys."""
            return {k: v for k, v in item.items() if k not in exclude}

        with transaction.atomic():
            candidate.save(update_fields=list(set(updated_fields + ['updated_at'])))

            # Handle Education – upsert by id to avoid duplicate key after dump/restore
            if 'education' in data:
                edu_sync_start = time.time()
                education_data = data['education']
                if isinstance(education_data, str):
                    try:
                        education_data = json.loads(education_data)
                    except json.JSONDecodeError:
                        education_data = []
                if isinstance(education_data, list):
                    kept_edu_ids = []
                    for edu_data in education_data:
                        if not (edu_data and edu_data.get('institution') and edu_data.get('start_date')):
                            continue
                        item_id = edu_data.get('id') or edu_data.get('pk')
                        payload = _payload_for_model(edu_data)
                        existing = Education.objects.filter(candidate=candidate, id=item_id).first() if item_id else None
                        if existing:
                            for k, v in payload.items():
                                setattr(existing, k, v)
                            existing.save()
                            kept_edu_ids.append(existing.id)
                        else:
                            obj = Education.objects.create(candidate=candidate, **payload)
                            kept_edu_ids.append(obj.id)
                    if kept_edu_ids:
                        candidate.education.exclude(id__in=kept_edu_ids).delete()
                    else:
                        candidate.education.all().delete()
                logger.info(f"Education processing took {time.time() - edu_sync_start:.2f}s")

            # Handle Experience – upsert by id to avoid duplicate key after dump/restore
            if 'experience' in data:
                exp_sync_start = time.time()
                experience_data = data['experience']
                if isinstance(experience_data, str):
                    try:
                        experience_data = json.loads(experience_data)
                    except json.JSONDecodeError:
                        experience_data = []
                if isinstance(experience_data, list):
                    kept_exp_ids = []
                    for exp_data in experience_data:
                        if not (exp_data and exp_data.get('company_name') and exp_data.get('position') and exp_data.get('start_date')):
                            continue
                        item_id = exp_data.get('id') or exp_data.get('pk')
                        payload = _payload_for_model(exp_data)
                        existing = Experience.objects.filter(candidate=candidate, id=item_id).first() if item_id else None
                        if existing:
                            for k, v in payload.items():
                                setattr(existing, k, v)
                            existing.save()
                            kept_exp_ids.append(existing.id)
                        else:
                            obj = Experience.objects.create(candidate=candidate, **payload)
                            kept_exp_ids.append(obj.id)
                    if kept_exp_ids:
                        candidate.experience.exclude(id__in=kept_exp_ids).delete()
                    else:
                        candidate.experience.all().delete()
                logger.info(f"Experience processing took {time.time() - exp_sync_start:.2f}s")
        
            # Handle Achievements - UPSERT logic with proper validation and image handling
            if 'achievements' in data:
                start_total = time.time()
                achievements_data = data['achievements']
                logger.info(f"Processing achievements data: {achievements_data}")
                
                # Parse JSON string if needed
                if isinstance(achievements_data, str):
                    try:
                        achievements_data = json.loads(achievements_data)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse achievements JSON")
                        achievements_data = []
                
                if isinstance(achievements_data, list):
                    # Apply soft limit of max 30 achievements
                    if len(achievements_data) > 30:
                        logger.warning(f"Too many achievements ({len(achievements_data)}), limiting to 30")
                        achievements_data = achievements_data[:30]
                    
                    logger.info(f"Processing {len(achievements_data)} achievements")
                    
                    kept_achievement_ids = []
                    validation_errors = []
                    
                    # Pre-fetch existing achievements for robust matching
                    existing_achievements = list(candidate.achievements.all())

                    # Smart Image Mapping: Find which achievements should get generic 'image' files
                    generic_images = request.FILES.getlist('image')
                    generic_image_index = 0
                    
                    for index, ach_data in enumerate(achievements_data):
                        ach_start = time.time()
                        if not ach_data:
                            continue
                        
                        # Prepare achievement data copy
                        achievement_data = ach_data.copy()
                        
                        # Handle image field if it's a string (URL or empty)
                        current_image = achievement_data.get('image')
                        if isinstance(current_image, str):
                            if current_image.startswith('http'):
                                achievement_data.pop('image')
                                # logger.info(f"Removed image URL from achievement {index} payload")
                            elif current_image == "":
                                achievement_data['image'] = None
                                current_image = None # Treat as needing an image

                        # Get achievement ID for upsert logic
                        item_id = achievement_data.get('id') or achievement_data.get('pk')
                        
                        # Robust matching fallback: match by normalized title and issuer
                        if not item_id:
                            title_norm = str(achievement_data.get('title') or "").strip().lower()
                            issuer_norm = str(achievement_data.get('issuer') or "").strip().lower()
                            
                            if title_norm:
                                for ex in existing_achievements:
                                    if (str(ex.title or "").strip().lower() == title_norm and 
                                        str(ex.issuer or "").strip().lower() == issuer_norm):
                                        item_id = ex.id
                                        logger.info(f"Matched existing achievement {item_id} by normalized title/issuer")
                                        break

                        logger.info(f"Processing achievement {index}, ID: {item_id}")
                        
                        # Handle image attachments
                        image_key = f'achievement_image_{index}'
                        if image_key in request.FILES:
                            achievement_data['image'] = request.FILES[image_key]
                            logger.info(f"Found specific image for achievement {index} with key {image_key}")
                        elif (not current_image or current_image == "") and generic_image_index < len(generic_images):
                             # If no specific image and no URL, try to use next available generic image
                            achievement_data['image'] = generic_images[generic_image_index]
                            logger.info(f"Assigning generic image {generic_image_index} to achievement {index}")
                            generic_image_index += 1
                        
                        payload = _payload_for_model(achievement_data)
                        
                        try:
                            if item_id:
                                existing = candidate.achievements.filter(id=item_id).first()
                                if existing:
                                    serializer = AchievementSerializer(existing, data=payload, partial=True)
                                    if serializer.is_valid():
                                        obj = serializer.save()
                                        kept_achievement_ids.append(obj.id)
                                        logger.info(f"Updated achievement {item_id} in {time.time() - ach_start:.2f}s")
                                    else:
                                        # Flatten errors to a simple list of strings
                                        for field, errors in serializer.errors.items():
                                            msg = errors[0] if isinstance(errors, list) else str(errors)
                                            validation_errors.append(f"Achievement {index + 1} ({field}): {msg}")
                                else:
                                    item_id = None # Force creation if ID not found
                            
                            if not item_id:
                                serializer = AchievementSerializer(data=payload)
                                if serializer.is_valid():
                                    obj = serializer.save(candidate=candidate)
                                    kept_achievement_ids.append(obj.id)
                                    logger.info(f"Created achievement {obj.id} in {time.time() - ach_start:.2f}s")
                                else:
                                    # Flatten errors to a simple list of strings
                                    for field, errors in serializer.errors.items():
                                        msg = errors[0] if isinstance(errors, list) else str(errors)
                                        validation_errors.append(f"Achievement {index + 1} ({field}): {msg}")
                        except Exception as e:
                            logger.error(f"Error processing achievement {index}: {e}", exc_info=True)
                            validation_errors.append(f"Achievement {index + 1} Error: {str(e)}")
                    
                    # If any achievement failed validation, raise error to rollback transaction
                    if validation_errors:
                        logger.warning(f"Achievement validation errors: {validation_errors}")
                        # Raise as a single flat message if there's only one, otherwise a list
                        if len(validation_errors) == 1:
                            raise serializers.ValidationError({"achievements": validation_errors[0]})
                        raise serializers.ValidationError({"achievements": validation_errors})

                    # Deletion
                    deleted_ids = []
                    to_delete = candidate.achievements.exclude(id__in=kept_achievement_ids)
                    deleted_count = to_delete.count()
                    if deleted_count > 0:
                        deleted_ids = list(to_delete.values_list('id', flat=True))
                        to_delete.delete()
                        logger.info(f"Deleted {deleted_count} achievements: {deleted_ids}")
                    
                    logger.info(f"Total achievements processing time: {time.time() - start_total:.2f}s")
                else:
                    logger.error(f"Achievements data is not a list")
            else:
                logger.info("No achievements data in request")
        
        # ---- SINGLE BACKGROUND THREAD: S3 uploads + ML calls ----
        # Build ML payload and spawn one thread for ALL heavy I/O
        try:
            ml_payload = {
                "full_name": candidate.full_name or "",
                "title": candidate.title or "",
                "bio": candidate.bio or "",
                "location": candidate.location or "",
                "work_style": candidate.work_style or "",
                "skills": candidate.skills or [],
                "superpowers": candidate.superpowers or [],
                "preferred_roles": candidate.preferred_roles or [],
                "is_available": candidate.is_available or False,
                "min_salary": candidate.min_salary if candidate.min_salary is not None else None,
                "max_salary": candidate.max_salary if candidate.max_salary is not None else None,
                "seniority_level": candidate.seniority_level or "",
                "passion_projects": candidate.passion_projects or "",
                "resume_url": get_file_url(candidate.resume_url),
                "video_intro_url": get_file_url(candidate.video_intro_url),
                "resume_data": candidate.resume_data or {},
                "user_id": str(candidate.user.id),
                "email": candidate.user.email or "",
                "candidate_profile_summary": candidate.candidate_profile_summary or "",
            }

            # Extract origin base for building absolute URIs in background thread
            build_absolute_uri_base = request.build_absolute_uri('/').rstrip('/')

            t = threading.Thread(
                target=_process_files_and_ml_in_background,
                kwargs={
                    'candidate_id': candidate.id,
                    'resume_info': bg_resume_info,
                    'video_info': bg_video_info,
                    'profile_image_info': bg_profile_image_info,
                    'old_resume_path': old_resume_path,
                    'old_video_path': old_video_path,
                    'old_profile_image_path': old_profile_image_path,
                    'ml_payload': ml_payload,
                    'build_absolute_uri_base': build_absolute_uri_base,
                },
                daemon=True,
            )
            t.start()
            logger.info(f"[BG] Background processing started for candidate {candidate.id} "
                        f"(files: resume={bg_resume_info is not None}, video={bg_video_info is not None}, "
                        f"image={bg_profile_image_info is not None})")
        except Exception as e:
            logger.error(f"Failed to start background processing thread: {e}", exc_info=True)

        response_data = CandidateSerializer(candidate, context={'request': request}).data
        response_data['processing_status'] = 'processing' if has_file_uploads else 'idle'
        return Response(response_data)

    # ====================== PROCESSING STATUS POLLING ======================
    @action(detail=False, methods=['get'], url_path='processing-status')
    def processing_status(self, request):
        """
        Lightweight polling endpoint for frontend to check if background
        file processing (S3 upload + ML) is complete.
        Usage: GET /candidates/processing-status/
        Returns:
          - processing_status: 'idle' | 'processing' | 'completed' | 'failed'
          - processing_error: error string if failed, else null
          - profile: full profile data when completed (so frontend can refresh)
        """
        candidate = self.get_candidate()
        cache_key = f"candidate_processing_{candidate.id}"
        cached = cache.get(cache_key)

        if cached:
            status = cached.get('status', 'idle')
            error = cached.get('error')
            response_data = {
                'processing_status': status,
                'processing_error': error,
            }
            # If completed/failed, include fresh profile and clear cache
            if status in ('completed', 'failed'):
                candidate.refresh_from_db()
                response_data['profile'] = CandidateSerializer(candidate, context={'request': request}).data
                cache.delete(cache_key)
            return Response(response_data)

        return Response({
            'processing_status': 'idle',
            'processing_error': None,
        })

    # ====================== DOWNLOAD RESUME ACTION ======================
    @action(detail=False, methods=['get'], url_path='download-resume')
    def download_resume(self, request):
        candidate = self.get_candidate()

        base_url = settings.FLIT_AI_URL.rstrip('/')
        make_cv_url = f"{base_url}/make_cv/{candidate.id}"

        headers = {}
        if hasattr(settings, 'ML_API_KEY'):
            headers["Authorization"] = f"Bearer {settings.ML_API_KEY}"

        try:
            # make_cv endpoint expects POST (GET returns 405 Method Not Allowed)
            # Add timeout to prevent long hanging requests
            resp = requests.post(
                make_cv_url, 
                headers=headers, 
                json={}, 
                timeout=(30, 60)  # (connection_timeout, read_timeout) in seconds
            )
            resp.raise_for_status()
            cv_data = resp.json()
            
            if not cv_data.get('name') and not cv_data.get('professional_summary'):
                return Response({
                    "error": "AI service returned empty or invalid CV data"
                }, status=503)

        except requests.exceptions.Timeout:
            logger.error(f"make_cv API timeout for candidate {candidate.id}")
            return Response({
                "error": "Resume generation is taking too long. Please try again in a few minutes."
            }, status=504)
        except requests.RequestException as e:
            logger.error(f"make_cv API failed for candidate {candidate.id}: {e}")
            return Response({
                "error": "We're having trouble generating your resume right now. Please try again in a few minutes."
            }, status=503)

        except ValueError:
            logger.error(f"Invalid JSON from make_cv for candidate {candidate.id}")
            return Response({"error": "Service returned invalid data"}, status=500)

        try:
            pdf_bytes = generate_pdf_from_cv_data(cv_data)
        except Exception as e:
            logger.exception(f"PDF generation failed for candidate {candidate.id}")
            return Response({
                "error": "Could not create PDF resume at this moment. Our team has been notified."
            }, status=500)

        # 4. Save file
        try:
            filename = f"ai_resume_{candidate.id}_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
            path = resume_upload_path(candidate, filename) 

            default_storage.save(path, ContentFile(pdf_bytes))

            candidate.ai_resume_url = path
            candidate.portfolio_completed = True
            candidate.save(update_fields=['ai_resume_url', 'portfolio_completed', 'updated_at'])

            resume_url = request.build_absolute_uri(default_storage.url(path))

            return Response({
                'resume_url': resume_url,
                'message': 'Your professional resume has been generated successfully!',
                'generated': True
            })

        except Exception as save_error:
            logger.error(f"Failed to save resume file for {candidate.id}: {save_error}", exc_info=True)
            return Response({
                "error": "Resume generated but could not be saved. Please contact support."
            }, status=500)
        
    # ====================== DASHBOARD ACTIONS ======================
    @action(detail=False, methods=['get'], url_path='dashboard')
    def dashboard(self, request):
        candidate = self.get_candidate()
        return Response({
            'profile': CandidateSerializer(candidate, context={'request': request}).data,
            'applications': self._get_applications_summary(candidate),
            'latest_jobs': self._get_latest_jobs_data(candidate),
            'latest_projects': self._get_latest_projects_data(candidate),
        })


    @action(detail=False, methods=['get'], url_path='dashboard/applications')
    def applications(self, request):
            candidate = self.get_candidate()
            app_type = request.query_params.get('type')
            search_query = request.query_params.get('search')

            formatted = []
            
            if not app_type or app_type == 'job':
                job_apps = Application.objects.filter(candidate=candidate).select_related('job__company').order_by('-applied_at')
                if search_query:
                    job_apps = job_apps.filter(
                        Q(job__title__istartswith=search_query) | 
                        Q(job__title__icontains=' ' + search_query) |
                        Q(job__company__company_name__istartswith=search_query) |
                        Q(job__company__company_name__icontains=' ' + search_query)
                    )
                for app in job_apps:
                    formatted.append(self._format_application(app, 'job'))
            
            if not app_type or app_type == 'project':
                project_apps = ProjectApplication.objects.filter(candidate=candidate).select_related('project__company').order_by('-applied_at')
                if search_query:
                    project_apps = project_apps.filter(
                        Q(project__title__istartswith=search_query) | 
                        Q(project__title__icontains=' ' + search_query) |
                        Q(project__company__company_name__istartswith=search_query) |
                        Q(project__company__company_name__icontains=' ' + search_query)
                    )
                for app in project_apps:
                    formatted.append(self._format_application(app, 'project'))

            # Sort newest first only if both types are present
            if not app_type:
                formatted.sort(key=lambda x: x['applied_at'], reverse=True)

            # Calculate unread counts before marking as read
            unread_job_count = Application.objects.filter(candidate=candidate, is_read=False).count()
            unread_project_count = ProjectApplication.objects.filter(candidate=candidate, is_read=False).count()
            
            # Mark all as read when list is accessed
            Application.objects.filter(candidate=candidate, is_read=False).update(is_read=True)
            ProjectApplication.objects.filter(candidate=candidate, is_read=False).update(is_read=True)

            # Use CustomPagination properly
            page = self.paginate_queryset(formatted)
            
            counts = {
                'job': Application.objects.filter(candidate=candidate).count(),
                'project': ProjectApplication.objects.filter(candidate=candidate).count(),
            }

            data = {
                'total_applications': counts['job'] + counts['project'],
                'job_applications_count': counts['job'],
                'project_applications_count': counts['project'],
                'unread_job_count': unread_job_count,
                'unread_project_count': unread_project_count,
                'applications': page if page is not None else formatted,
            }

            if page is not None:
                # Custom order for paginated response
                return Response({
                    'total_applications': data['total_applications'],
                    'job_applications_count': data['job_applications_count'],
                    'project_applications_count': data['project_applications_count'],
                    'unread_job_count': data['unread_job_count'],
                    'unread_project_count': data['unread_project_count'],
                    'count': self.paginator.page.paginator.count,
                    'next': self.paginator.get_next_link(),
                    'previous': self.paginator.get_previous_link(),
                    'total_pages': self.paginator.page.paginator.num_pages,
                    'current_page': self.paginator.page.number,
                    'results': data['applications']
                })
            
            return Response(data)

    def _format_application(self, app, app_type):
        if app_type == 'job':
            return {
                'app_id': app.id,
                'id': app.job.id if app.job else None,
                'title': app.job.title if app.job else 'Unknown',
                'company': app.job.company.name if app.job and app.job.company else 'Unknown',
                'status': app.status,
                'applied_at': app.applied_at,
                'type': 'job'
            }
        return {
            'app_id': app.id,
            'id': app.project.id if app.project else None,
            'title': app.project.title if app.project else 'Unknown',
            'company': app.project.company.name if app.project and app.project.company else 'Unknown',
            'status': app.status,
            'applied_at': app.applied_at,
            'type': 'project'
        }

    def _get_applications_summary(self, candidate):
        counts = Application.objects.filter(
            candidate=candidate,
            status__in=['pending', 'in_review', 'shortlisted', 'interview', 'offer']
        ).aggregate(
            total=Count('id'),
            job_apps=Count('id', filter=Q(job__isnull=False)),
            project_apps=Count('id', filter=Q(project__isnull=False))
        )
        return {
            'total_applications': counts['total'] or 0,
            'job_applications_count': counts['job_apps'] or 0,
            'project_applications_count': counts['project_apps'] or 0,
            'references_count': ReferenceRequest.objects.filter(candidate=candidate, status='completed').count(),
        }

    def _get_latest_jobs_data(self, candidate, limit=5):
        jobs = Job.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]
        return JobListSerializer(jobs, many=True, context={'request': self.request}).data

    def _get_latest_projects_data(self, candidate, limit=5):
        projects = Project.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]
        return ProjectListSerializer(projects, many=True, context={'request': self.request}).data

    def _format_category(self, category):
        """Convert category slug to human-readable format"""
        category_mapping = {
            'business_office': 'Business & Office',
            'finance_accounting': 'Finance & Accounting',
            'marketing_sales_communication': 'Marketing, Sales & Communication',
            'technology': 'Technology',
            'education_training': 'Education and Training',
            'healthcare_wellness': 'Healthcare & Wellness',
            'skilled_trades_labor': 'Skilled Trades & Labor',
            'transportation_logistics': 'Transportation & Logistics',
            'creative_design': 'Creative & Design',
            'legal_government': 'Legal & Government',
            'science_engineering_research': 'Science, Engineering & Research',
            'hospitality_service': 'Hospitality & Service',
            'retail_consumer_services': 'Retail & Consumer Services',
            'nonprofit_social_impact': 'Nonprofit & Social Impact',
            'other': 'Other',
        }
        return category_mapping.get(category, category.replace('_', ' ').title())
    
    def _format_project_category(self, category):
        """Convert project category slug to human-readable format"""
        category_mapping = {
            'engineering': 'Engineering',
            'design': 'Design',
            'marketing': 'Marketing',
            'development': 'Development',
            'consulting': 'Consulting',
            'writing': 'Writing',
            'research': 'Research',
            'data_science': 'Data Science',
            'management': 'Management',
            'other': 'Other',
        }
        return category_mapping.get(category, category.replace('_', ' ').title())

    # ====================== LATEST JOBS & PROJECTS (ML version) ======================

    @action(detail=False, methods=['get'], url_path='dashboard/latest-jobs')
    def latest_jobs(self, request):
        candidate = self.get_candidate()
        from django.core.cache import cache
        cache_key = f'candidate_{candidate.id}_latest_jobs'
        cached = cache.get(cache_key)
    
        if cached and cached.get('ml_success'):
            # Use cached data but update has_applied status from database and format fields
            jobs = cached.get('jobs', [])
            job_ids = [j['id'] for j in jobs if 'id' in j]
            if job_ids:
                applied_job_ids = set(
                    Application.objects.filter(
                        candidate=candidate,
                        job_id__in=job_ids
                    ).values_list('job_id', flat=True)
                )
                for job in jobs:
                    job['has_applied'] = job['id'] in applied_job_ids
                    # Format cached data fields
                    if 'workStyle' in job:
                        job['workStyle'] = job['workStyle'].replace('-', ' ').title()
                    if 'category' in job:
                        job['category'] = self._format_category(job['category'])
                    if 'experienceLevel' in job:
                        job['experienceLevel'] = job['experienceLevel'].title()
                    if 'employmentType' in job:
                        job['employmentType'] = job['employmentType'].replace('-', ' ').title()
                    if 'status' in job:
                        job['status'] = job['status'].title()
            queryset = jobs
        else:
            queryset = []
            try:
                ml_url = f"{settings.FLIT_AI_URL.rstrip('/')}/show_jobs_for_candidate/{candidate.id}"
                response = requests.get(ml_url)
                if response.status_code == 200:
                    ranked = response.json().get('ranked_opportunities', [])
                    jobs = []
                    job_ids = []  # For bulk query

                    for item in ranked:
                        job_id = item.get('job_id') or item.get('id')
                        if not job_id:
                            continue
                            
                        # Only include active jobs
                        if item.get('status') != 'active':
                            continue
                            
                        company = item.get('company', {})
                        job_data = {
                            'id': job_id,
                            'title': item.get('title', 'No Title'),
                            'description': item.get('description', ''),
                            'workStyle': item.get('work_style', 'remote').replace('-', ' ').title(),
                            'category': self._format_category(item.get('category', 'other')),
                            'experienceLevel': item.get('experience_level', 'mid').title(),
                            'employmentType': item.get('employment_type', 'full-time').replace('-', ' ').title(),
                            'salaryRangeMin': item.get('salary_range', {}).get('min'),
                            'salaryRangeMax': item.get('salary_range', {}).get('max'),
                            'status': item.get('status', 'active').title(),
                            'created_at': item.get('created_at', timezone.now().isoformat()),
                            'location': item.get('location'),
                            'skills': [skill.title() if isinstance(skill, str) else skill for skill in item.get('skills', [])],
                            'company_name': company.get('company_name', 'Unknown'),
                            'company_logo': company.get('company_logo'),
                            'company_id': company.get('id'),
                            'has_applied': False  
                        }
                        jobs.append(job_data)
                        job_ids.append(job_id)

                    # Bulk check for job applications
                    if job_ids:
                        applied_job_ids = set(
                            Application.objects.filter(
                                candidate=candidate,
                                job_id__in=job_ids
                            ).values_list('job_id', flat=True)
                        )
                        for job in jobs:
                            job['has_applied'] = job['id'] in applied_job_ids

                    if jobs:
                        cache.set(cache_key, {'jobs': jobs, 'ml_success': True}, timeout=300)
                    queryset = jobs
            except Exception as e:
                logger.warning(f"ML jobs fetch failed: {e}")

        page = self.paginate_queryset(queryset)
        data = {
            'ml_success': bool(queryset),
            'latest_jobs': page if page is not None else queryset
        }
        if page is not None:
            return self.get_paginated_response(data)
        return Response({**data, 'count': len(queryset)})

    @action(detail=False, methods=['get'], url_path='dashboard/latest-projects')
    def latest_projects(self, request):
        candidate = self.get_candidate()
        cache_key = f'candidate_{candidate.id}_latest_projects'
        cached = cache.get(cache_key)
        if cached:
            # Use cached data but update has_applied status from database and format fields
            project_ids = [p['id'] for p in cached if 'id' in p]
            if project_ids:
                applied_project_ids = set(
                    ProjectApplication.objects.filter(
                        candidate=candidate,
                        project_id__in=project_ids
                    ).values_list('project_id', flat=True)
                )
                for proj in cached:
                    proj['has_applied'] = proj['id'] in applied_project_ids
                    # Format cached data fields
                    if 'status' in proj:
                        proj['status'] = proj['status'].title()
                    if 'category' in proj:
                        proj['category'] = self._format_project_category(proj['category'])
                    if 'paymentType' in proj:
                        proj['paymentType'] = proj['paymentType'].replace('-', ' ').title()
                    if 'work_style' in proj:
                        proj['work_style'] = proj['work_style'].replace('-', ' ').title()
                    if 'skills' in proj:
                        proj['skills'] = [skill.title() if isinstance(skill, str) else skill for skill in proj['skills']]
            queryset = cached
        else:
            queryset = []
            try:
                ml_url = f"{settings.FLIT_AI_URL.rstrip('/')}/show_projects_for_candidate/{candidate.id}"
                response = requests.get(ml_url)
                if response.status_code == 200:
                    data = response.json()
                    projects = data.get('ranked_projects') or data.get('opportunities') or []
                    formatted = []
                    project_ids = []  # Collect IDs for bulk query

                    for item in projects:
                        pid = item.get('id') or item.get('project_id')
                        if not pid:
                            continue
                        project = Project.objects.filter(
                            id=pid,
                            status__in=['active', 'open']
                        ).select_related('company').first()
                        if not project:
                            continue

                        company_name = project.company.company_name if project.company else 'Unknown'
                        company_id = project.company.id if project.company else None

                        project_data = {
                            'id': project.id,
                            'title': project.title,
                            'description': project.description,
                            'category': self._format_project_category(project.category),
                            'status': project.status.title(),
                            'created_at': project.created_at.isoformat(),
                            'skills': [skill.title() if isinstance(skill, str) else skill for skill in (list(project.skills) if hasattr(project, 'skills') else [])],
                            'estimatedHours': project.estimatedHours if hasattr(project, 'estimatedHours') else '1-2 weeks',
                            'paymentType': project.get_paymentType_display(),
                            'paymentAmount': project.paymentAmount,
                            'work_style': project.get_work_style_display(),
                            'deadline': project.deadline.isoformat() if project.deadline else None,
                            'company_name': company_name,
                            'company_id': company_id,
                            'company_logo': project.company.logo.url if project.company.logo else None,
                            'has_applied': False  
                        }
                        formatted.append(project_data)
                        project_ids.append(project.id)

                    # Bulk check for applications
                    if project_ids:
                        applied_project_ids = set(
                            ProjectApplication.objects.filter(
                                candidate=candidate,
                                project_id__in=project_ids
                            ).values_list('project_id', flat=True)
                        )
                        for proj in formatted:
                            proj['has_applied'] = proj['id'] in applied_project_ids

                    cache.set(cache_key, formatted, timeout=300)
                    queryset = formatted
            except Exception as e:
                logger.warning(f"ML projects fetch failed: {e}")

        class DictSerializer(serializers.Serializer):
            id = serializers.IntegerField()
            title = serializers.CharField()
            description = serializers.CharField()
            category = serializers.CharField()
            status = serializers.CharField()
            created_at = serializers.CharField()
            skills = serializers.ListField(child=serializers.CharField())
            estimatedHours = serializers.CharField()
            paymentType = serializers.CharField()
            paymentAmount = serializers.IntegerField()
            work_style = serializers.CharField()
            company_name = serializers.CharField()
            company_id = serializers.IntegerField(allow_null=True)
            company_logo = serializers.CharField(allow_null=True)
            deadline = serializers.CharField(allow_null=True)
            has_applied = serializers.BooleanField()  

        page = self.paginate_queryset(queryset)
        serializer = DictSerializer(queryset if page is None else page, many=True)
        data = {
            'ml_success': bool(queryset),
            'latest_projects': serializer.data
        }
        if page is not None:
            return self.get_paginated_response(data)
        return Response({**data, 'count': len(queryset), 'next': None, 'previous': None})

    @action(detail=False, methods=['get'], url_path='flit-list')
    def flit_list(self, request):
        """
        Returns a list of companies/employers that have 'flitted' (action='pass') the candidate.
        Includes unread count and marks them as read.
        """
        candidate = self.get_candidate()
        
        # Get CandidateAction records where this candidate was 'flitted'
        actions_qs = CandidateAction.objects.filter(
            candidate_id=str(candidate.id),
            action='pass'
        ).select_related('employer__company').order_by('-created_at')
        
        # Calculate unread count BEFORE marking as read
        unread_count = actions_qs.filter(is_read=False).count()
        
        # Mark all as read when the list is accessed
        actions_qs.filter(is_read=False).update(is_read=True)
        
        employers = [action.employer for action in actions_qs]
        
        # Paginate results
        page = self.paginate_queryset(employers)
        if page is not None:
            serializer = CandidateFlittedCompanySerializer(page, many=True, context={'request': request})
            
            # Manually construct response to control field order
            return Response({
                'count': self.paginator.page.paginator.count,
                'unread_count': unread_count,
                'next': self.paginator.get_next_link(),
                'previous': self.paginator.get_previous_link(),
                'total_pages': self.paginator.page.paginator.num_pages,
                'current_page': self.paginator.page.number,
                'results': serializer.data
            })
        
        serializer = CandidateFlittedCompanySerializer(employers, many=True, context={'request': request})
        return Response({
            'count': len(employers),
            'unread_count': unread_count,
            'results': serializer.data
        })


    @action(detail=False, methods=['post'], url_path='mark-as-read')
    def mark_as_read(self, request):
        """
        Marks all items of a specific type as read for the candidate.
        Expected data: {'type': 'flit' | 'job_application' | 'project_application' | 'offer' | 'reference' | 'interview'}
        """
        candidate = self.get_candidate()
        category = request.data.get('type')
        
        if not category:
            return Response({"error": "Type is required"}, status=400)
            
        if category == 'flit':
            CandidateAction.objects.filter(candidate_id=str(candidate.id), action='pass', is_read=False).update(is_read=True)
        elif category == 'job_application':
            Application.objects.filter(candidate=candidate, is_read=False).update(is_read=True)
        elif category == 'project_application':
            ProjectApplication.objects.filter(candidate=candidate, is_read=False).update(is_read=True)
        elif category == 'offer':
            Offer.objects.filter(candidate=candidate.user, is_read=False).update(is_read=True)
        elif category == 'reference':
            ReferenceRequest.objects.filter(candidate=candidate, is_read=False).update(is_read=True)
        elif category == 'interview':
            InterviewRequest.objects.filter(
                Q(job_application__candidate=candidate) | Q(project_application__candidate=candidate),
                is_read=False
            ).update(is_read=True)
        else:
            return Response({"error": "Invalid type"}, status=400)
            
        return Response({"message": f"All {category} marked as read"})

    # ====================== AI MATCHING ======================
    @action(detail=True, methods=['get'], url_path='ai-matching', permission_classes=[permissions.AllowAny])
    def ai_matching(self, request, pk=None):
        candidate_id = pk
        total = request.query_params.get('total')
        params = {'total': total} if total else {}
        try:
            resp = requests.get(f"{settings.FLIT_AI_URL}/ai_matching/{candidate_id}", params=params)
            resp.raise_for_status()
            data = resp.json()

            # Data enrichment with company_image
            # The AI service typically returns a dict with 'matches' or 'ranked_opportunities'
            # or a list directly. We handle common patterns.
            if isinstance(data, dict):
                matches = data.get('matches', []) or data.get('ranked_opportunities', []) or data.get('opportunities', [])
            elif isinstance(data, list):
                matches = data
            else:
                matches = []

            if matches and isinstance(matches, list):
                # 1. Collect all job and project IDs to perform bulk lookups
                job_ids = []
                project_ids = []
                for item in matches:
                    if not isinstance(item, dict): continue
                    
                    # Try to determine if it's a job or project
                    # ML service usually provides 'type' or use specific ID keys
                    item_type = item.get('type', 'job').lower()
                    jid = item.get('job_id')
                    pid = item.get('project_id')
                    oid = item.get('id')

                    if jid:
                        job_ids.append(jid)
                    elif pid:
                        project_ids.append(pid)
                    elif oid:
                        if item_type == 'project':
                            project_ids.append(oid)
                        else:
                            job_ids.append(oid)

                # 2. Bulk fetch logos from database
                logo_map = {} # Map ID -> Logo URL
                
                if job_ids:
                    jobs = Job.objects.filter(id__in=job_ids).select_related('company')
                    for job in jobs:
                        if job.company and job.company.logo:
                            logo_map[f"job_{job.id}"] = request.build_absolute_uri(job.company.logo.url)
                
                if project_ids:
                    projects = Project.objects.filter(id__in=project_ids).select_related('company')
                    for project in projects:
                        if project.company and project.company.logo:
                            logo_map[f"project_{project.id}"] = request.build_absolute_uri(project.company.logo.url)

                # 3. Inject company_image into the response items
                for item in matches:
                    if not isinstance(item, dict): continue
                    
                    item_type = item.get('type', 'job').lower()
                    jid = item.get('job_id')
                    pid = item.get('project_id')
                    oid = item.get('id')
                    
                    logo_url = None
                    if jid and f"job_{jid}" in logo_map:
                        logo_url = logo_map[f"job_{jid}"]
                    elif pid and f"project_{pid}" in logo_map:
                        logo_url = logo_map[f"project_{pid}"]
                    elif oid:
                        key = f"{item_type}_{oid}"
                        logo_url = logo_map.get(key)
                    
                    # Add the field as requested by Team Lead
                    item['company_image'] = logo_url

            return Response(data)
        except requests.RequestException:
            return Response({'error': 'AI service unavailable'}, status=503)


    # ====================== WORK DNA ======================
    @action(detail=False, methods=['get', 'post'], url_path='work-dna/questions')
    def work_dna_questions(self, request):
        candidate = self.get_candidate()

        if request.method == 'GET':
            work_dna = WorkDNAQuestion.objects.filter(candidate=candidate).first()
            if work_dna:
                return Response(WorkDNAQuestionSerializer(work_dna).data)

            try:
                resp = requests.get(f"{settings.FLIT_AI_URL}/generate_work_dna_questions/{candidate.id}")
                if resp.status_code == 200:
                    questions = resp.json().get('questions', [])
                    work_dna = WorkDNAQuestion.objects.create(
                        candidate=candidate,
                        candidate_name=candidate.full_name,
                        questions=questions,
                        total_questions=len(questions)
                    )
                    return Response(WorkDNAQuestionSerializer(work_dna).data)
            except Exception as e:
                logger.error(f"Work DNA fetch failed: {e}")
            return Response({'error': 'Failed to fetch questions'}, status=503)

        # POST - save answers
        answers = request.data.get('answers', {})
        work_dna = WorkDNAQuestion.objects.filter(candidate=candidate).first()
        if not work_dna:
            return Response({'error': 'No questions found'}, status=404)

        current = work_dna.answers or {}
        for q_id, answer in answers.items():
            if str(q_id).isdigit() and int(q_id) <= len(work_dna.questions):
                q_text = work_dna.questions[int(q_id)-1].get('question', f'Question {q_id}')
                current[q_text] = answer

        work_dna.answers = current
        work_dna.save()
        return Response(WorkDNAQuestionSerializer(work_dna).data)

    @action(detail=True, methods=['get'], url_path='evaluate-work-dna-answers')
    def evaluate_work_dna(self, request, pk=None):
        try:
            candidate = Candidate.objects.get(id=pk)
            work_dna = WorkDNAQuestion.objects.get(candidate=candidate)
            if not work_dna.answers:
                return Response({'error': 'No answers'}, status=400)

            resp = requests.get(f"{settings.FLIT_AI_URL}/evaluate_work_dna_questions/{candidate.id}")
            if resp.status_code == 200:
                result = resp.json()
                work_dna.evaluation_result = result
                work_dna.save()
                return Response(result)
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
        return Response({'error': 'Evaluation failed'}, status=503)


class DiscoverTalentView(generics.ListAPIView):
    """
    Discover Talent — employer-facing search for public candidate profiles.
    Supports search by name, job title, or both with sophisticated relevance scoring.
    
    Query params:
        search       – free-text search term
        search_type  – 'name' | 'title' | 'both' (default: 'both')
        skills       – repeatable list; filters candidates whose skills overlap
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination
    serializer_class = DiscoverTalentSerializer

    # ── helpers ───────────────────────────────────────────────────────
    def _base_qs(self):
        """Base queryset: active, public, completed-profile candidates."""
        return Candidate.objects.select_related('user').filter(
            user__is_active=True,
            profile_visibility='public',
            basic_info_completed=True,
        )

    @staticmethod
    def _build_field_query(field, phrase, words):
        """
        Build a Q filter for a single field using word-start matching.
        Uses PostgreSQL \\m (word-start boundary) to ensure queries only
        match at the beginning of words — prevents mid-word false positives
        like 'alik' matching 'Malik' or 'evel' matching 'Developer'.
          • full phrase word-start match  OR
          • all individual words word-start matched (AND-ed together)
        """
        safe = re.escape(phrase)
        q = Q(**{f'{field}__iregex': rf'\m{safe}'})

        if len(words) > 1:
            word_q = Q()
            for w in words:
                safe_w = re.escape(w)
                word_q &= Q(**{f'{field}__iregex': rf'\m{safe_w}'})
            q |= word_q
        return q

    # ── main queryset ─────────────────────────────────────────────────
    def get_queryset(self):
        qs = self._base_qs()

        q = self.request.query_params.get('search', '').strip().lower()
        search_type = self.request.query_params.get('search_type', 'both').lower()

        if q:
            words = [w.strip() for w in q.split() if w.strip()]
            if not words:
                return qs

            # ── 1. FILTERING — narrow down candidates ─────────────
            name_q = Q()
            title_q = Q()

            if search_type in ('name', 'both'):
                # Phase 1: prefix match — first/last name STARTS with query (most precise)
                name_prefix_q = (
                    Q(user__first_name__istartswith=q)
                    | Q(user__last_name__istartswith=q)
                )
                # For multi-word, also try: first word starts first_name AND second starts last_name
                if len(words) > 1:
                    name_prefix_q |= (
                        Q(user__first_name__istartswith=words[0])
                        & Q(user__last_name__istartswith=words[-1])
                    )

                # Phase 2: substring match — full_name contains query anywhere (broader)
                name_contains_q = self._build_field_query('full_name', q, words)

                # Try prefix first; if results exist, use only those (cleaner results)
                prefix_exists = self._base_qs().filter(name_prefix_q).exists()
                name_q = name_prefix_q if prefix_exists else name_contains_q

            if search_type in ('title', 'both'):
                title_q = self._build_field_query('title', q, words)

            if search_type == 'name':
                qs = qs.filter(name_q)
            elif search_type == 'title':
                qs = qs.filter(title_q)
            else:  # both
                qs = qs.filter(name_q | title_q)

            # Fallback: only for 'both' search — relax to OR individual words
            # Uses word-start regex to avoid mid-word false positives
            # No fallback for name-only: if no name matched, return empty (correct UX)
            if not qs.exists() and search_type == 'both':
                fallback_q = Q()
                for w in words:
                    safe_w = re.escape(w)
                    fallback_q |= (
                        Q(full_name__iregex=rf'\m{safe_w}')
                        | Q(title__iregex=rf'\m{safe_w}')
                    )
                if fallback_q:
                    qs = self._base_qs().filter(fallback_q)

            # ── 2. RELEVANCE SCORING — rank the filtered set ──────
            full_phrase = ' '.join(words)

            # 2a. High-level match signals (annotated once)
            qs = qs.annotate(
                # Name prefix match — first/last name STARTS with query → +700
                _name_prefix=Case(
                    When(
                        Q(user__first_name__istartswith=q)
                        | Q(user__last_name__istartswith=q),
                        then=Value(700),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                # Exact title match → highest priority (+1000)
                _title_exact=Case(
                    When(title__iexact=q, then=Value(1000)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                # Full name exact / first-name / last-name exact → +800
                # Full name contains phrase → +400
                _name_match=Case(
                    When(
                        Q(full_name__iexact=full_phrase)
                        | Q(user__first_name__iexact=full_phrase)
                        | Q(user__last_name__iexact=full_phrase),
                        then=Value(800),
                    ),
                    When(
                        Q(full_name__icontains=full_phrase),
                        then=Value(400),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                # Title contains ALL individual words → +500
                _title_all_words=Case(
                    When(
                        self._all_words_q('title', words),
                        then=Value(500),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )

            # 2b. Per-word granular signals (first word weighted 3×, rest 2×)
            for i, word in enumerate(words):
                wt = 3 if i == 0 else 2  # first word gets higher weight
                qs = qs.annotate(**{
                    # ─ title ─
                    f'_tw_exact_{i}': Case(
                        When(title__iexact=word, then=Value(wt * 4)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_tw_start_{i}': Case(
                        When(title__istartswith=word, then=Value(wt * 3)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_tw_has_{i}': Case(
                        When(title__icontains=word, then=Value(wt * 2)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    # ─ full_name ─
                    f'_fn_exact_{i}': Case(
                        When(full_name__iexact=word, then=Value(wt * 4)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_fn_start_{i}': Case(
                        When(full_name__istartswith=word, then=Value(wt * 3)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_fn_has_{i}': Case(
                        When(full_name__icontains=word, then=Value(wt * 2)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    # ─ user.first_name (slightly lower: ×3 / ×2 / ×1) ─
                    f'_ufn_exact_{i}': Case(
                        When(user__first_name__iexact=word, then=Value(wt * 3)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_ufn_start_{i}': Case(
                        When(user__first_name__istartswith=word, then=Value(wt * 2)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_ufn_has_{i}': Case(
                        When(user__first_name__icontains=word, then=Value(wt)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    # ─ user.last_name ─
                    f'_uln_exact_{i}': Case(
                        When(user__last_name__iexact=word, then=Value(wt * 3)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_uln_start_{i}': Case(
                        When(user__last_name__istartswith=word, then=Value(wt * 2)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                    f'_uln_has_{i}': Case(
                        When(user__last_name__icontains=word, then=Value(wt)),
                        default=Value(0), output_field=IntegerField(),
                    ),
                })

            # 2c. Sum all signals into total_score
            score = Value(0, output_field=IntegerField())

            # High-level signals
            for fld in ('_name_prefix', '_title_exact', '_name_match', '_title_all_words'):
                score = score + F(fld)

            # Per-word signals (12 annotations per word)
            per_word_prefixes = (
                '_tw_exact_', '_tw_start_', '_tw_has_',
                '_fn_exact_', '_fn_start_', '_fn_has_',
                '_ufn_exact_', '_ufn_start_', '_ufn_has_',
                '_uln_exact_', '_uln_start_', '_uln_has_',
            )
            for i in range(len(words)):
                for prefix in per_word_prefixes:
                    score = score + F(f'{prefix}{i}')

            # Small popularity boost: +1 per 1000 profile views
            qs = qs.annotate(
                total_score=score + (F('profile_views') / 1000)
            ).order_by('-total_score')

        # ── 3. SKILLS FILTER (independent of search) ──────────────
        skills = self.request.query_params.getlist('skills')
        if skills:
            qs = qs.filter(skills__overlap=skills)

        return qs

    # ── tiny utility ──────────────────────────────────────────────────
    @staticmethod
    def _all_words_q(field, words):
        """Return Q that requires *field* to icontains every word."""
        combined = Q()
        for w in words:
            combined &= Q(**{f'{field}__icontains': w})
        return combined


class AchievementViewSet(CandidateAccessMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing candidate achievements
    """
    serializer_class = AchievementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        candidate = self.get_candidate()
        return Achievement.objects.filter(candidate=candidate).order_by('-date_achieved')
    
    def perform_create(self, serializer):
        candidate = self.get_candidate()
        serializer.save(candidate=candidate).distinct()
