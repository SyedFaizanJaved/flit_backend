import io
from urllib.parse import urlparse

import requests
from rest_framework import viewsets, mixins, status, permissions
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
import django.db
from utils.remote_file import MAX_BYTES
from .company_mapper import to_form_values
from .models import Company, CompanyImage, CompanyMilestone
from .serializers import (
    CompanySerializer,
    CompanyListSerializer,
    CompanyUpdateSerializer,
    CompanyImageSerializer,
    CompanyImageBulkUploadSerializer,
    CompanyMilestoneSerializer
)
from employers.models import Employer
import logging

logger = logging.getLogger("exceptions")

User = get_user_model()

# Scraping several pages and running them through an LLM is slower than parsing one CV,
# so this sits above candidates' RESUME_PARSE_TIMEOUT rather than matching it.
COMPANY_EXTRACT_TIMEOUT = 180


# Custom Permission: Sirf company ka creator hi update/delete kar sake
class IsCompanyOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.created_by == request.user


class CompanyViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Optimized Company ViewSet
    - Uses GenericViewSet + Mixins for less boilerplate
    - Proper permissions
    - Clean dashboard & custom actions
    """
    queryset = Company.objects.all().prefetch_related('images', 'milestones')
    permission_classes = [permissions.IsAuthenticated]
    # Explicit parsers so gallery uploads (multipart/form-data with multiple files
    # under `uploaded_images`) are always handled, regardless of DRF defaults.
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['industry', 'size', 'is_verified', 'work_mode']
    search_fields = ['company_name', 'industry', 'description']
    ordering_fields = ['created_at', 'company_name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return CompanyListSerializer
        if self.action in ['update', 'partial_update']:
            return CompanyUpdateSerializer
        if self.action == 'upload_image':
            return CompanyImageBulkUploadSerializer
        if self.action == 'add_milestone':
            return CompanyMilestoneSerializer
        return CompanySerializer

    def get_permissions(self):
        """
        Granular permissions:
        - partial_update & destroy: only company owner
        - verify: only staff/admin
        """
        if self.action in ['partial_update', 'update', 'destroy', 'upload_image', 'add_milestone', 'dashboard']:
            return [permissions.IsAuthenticated(), IsCompanyOwner()]
        if self.action == 'verify':
            return [permissions.IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        """
        my_companies action ke liye filtered queryset
        """
        if self.action == 'my_companies':
            return Company.objects.filter(created_by=self.request.user).prefetch_related('images', 'milestones')
        return super().get_queryset()

    def perform_create(self, serializer):
        """
        Create ke time automatically created_by set kar do
        """
        serializer.save(created_by=self.request.user)

    @django.db.transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Consolidated update: handle basic info, images, and milestones
        Returns full company details in response.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # Force re-fetch with prefetches to ensure the response is complete
        instance = self.get_queryset().get(pk=instance.pk)
        full_serializer = CompanySerializer(instance, context={'request': request})
        return Response(full_serializer.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @django.db.transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Override create to handle Employer profile linking and nested data properly.
        Returns full company details in response.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.save()

        # Re-fetch company with prefetched images and milestones for a complete response
        instance = self.get_queryset().get(pk=company.pk)
        full_serializer = CompanySerializer(instance, context={'request': request})
        return Response(full_serializer.data, status=status.HTTP_201_CREATED)

    # ================= COMPANY PROFILE EXTRACT (WIZARD PREFILL) =================
    @action(detail=False, methods=['post'], url_path='extract-profile')
    def extract_profile(self, request):
        """Read a company's website and/or document so the employer wizard opens pre-filled.

        POST /api/companies/extract-profile/
            multipart  company_url=<https://acme.com> and/or company_file=<file>
            or JSON    {"company_url": "https://acme.com"}

        The employer mirror of /candidates/parse-resume/. Best-effort by design: anything
        the service cannot read comes back as 422 and the wizard simply opens empty. It
        must never be able to block someone from creating a company.

        Nothing is persisted -- there is no Company row yet at this point in the flow, so
        the caller holds the values until the employer submits the form.
        """
        company_url = str(request.data.get('company_url') or '').strip()
        upload = request.FILES.get('company_file')

        if not company_url and not upload:
            return Response({'error': 'Provide company_url or company_file.'}, status=400)

        if company_url:
            # ponytail: scheme/host check only. This URL is fetched by the ML service, not
            # from inside our VPC, so utils.remote_file's address guard would be guarding
            # the wrong network -- and it rejects http://, which plenty of company sites
            # still are. Swap it in here if this endpoint ever fetches the page itself.
            if '://' not in company_url:
                company_url = f'https://{company_url}'
            parsed = urlparse(company_url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                return Response({'error': 'Enter a valid website URL.'}, status=400)

        files = None
        if upload:
            content = upload.read()
            if len(content) > MAX_BYTES:
                return Response({'error': 'That file is larger than 10MB.'}, status=400)
            files = {'company_file': (
                upload.name,
                io.BytesIO(content),
                upload.content_type or 'application/octet-stream',
            )}

        def unreadable(reason):
            logger.warning(
                "company extract failed user=%s url=%s file=%s: %s",
                request.user.id, company_url or None, bool(upload), reason,
            )
            return Response(
                {'error': "We couldn't read that. You can fill the form in manually."},
                status=422,
            )

        try:
            # ponytail: no retry. The candidate parser retries a 5xx once because it
            # answers in seconds; here a second attempt is another full scrape on top of
            # a wait the employer is already sitting through.
            response = requests.post(
                f"{settings.FLIT_AI_URL}/extract_company_profile",
                params={'company_url': company_url} if company_url else None,
                files=files,
                timeout=COMPANY_EXTRACT_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            return unreadable(f"request failed: {e}")

        if response.status_code != 200:
            return unreadable(f"HTTP {response.status_code}: {response.text[:200]}")

        try:
            result = response.json()
        except ValueError:
            return unreadable("invalid JSON")

        if not result.get('success'):
            return unreadable("service reported no usable data")

        data = result.get('data') or {}
        # `form_values` is what the wizard consumes; the rest is returned so the client can
        # show anything the mapper had no field for (company_summary, which pages were read).
        return Response({
            'form_values': to_form_values(data),
            'company_data': data,
            'company_summary': result.get('company_summary'),
            'metadata': result.get('metadata'),
        })

    @action(detail=False, methods=['get'], url_path='my-companies')
    def my_companies(self, request):
        """
        Logged-in user ki apni companies list
        """
        queryset = self.get_queryset()  
        serializer = CompanySerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='dashboard')
    def dashboard(self, request, pk=None):
        """
        Company dashboard with stats & recent jobs/projects
        """
        company = get_object_or_404(Company, id=pk, created_by=request.user)

        data = {
            'company': CompanySerializer(company).data,
            'company_name': company.company_name,
            'name': company.name,
            'jobs_count': company.jobs.count() if hasattr(company, 'jobs') else 0,
            'projects_count': company.projects.count() if hasattr(company, 'projects') else 0,
            'applications_count': 0,  
            'hires_count': 0,
            'recent_jobs': [],
            'recent_projects': [],
        }

        # Recent Jobs
        if hasattr(company, 'jobs'):
            recent_jobs = company.jobs.all()[:5]
            data['recent_jobs'] = [
                {
                    'id': job.id,
                    'title': getattr(job, 'title', ''),
                    'status': getattr(job, 'status', ''),
                    'applications_count': job.applications.count() if hasattr(job, 'applications') else 0,
                    'created_at': job.created_at,
                }
                for job in recent_jobs
            ]

        if hasattr(company, 'projects'):
            recent_projects = company.projects.all()[:5]
            data['recent_projects'] = [
                {
                    'id': project.id,
                    'title': getattr(project, 'title', ''),
                    'status': getattr(project, 'status', ''),
                    'applications_count': project.applications.count() if hasattr(project, 'applications') else 0,
                    'created_at': project.created_at,
                }
                for project in recent_projects
            ]

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        """
        Admin/Staff only: Company ko verify karna
        """
        company = get_object_or_404(Company, id=pk)
        company.is_verified = True
        company.save(update_fields=['is_verified'])

        return Response(
            {
                'message': 'Company verified successfully',
                'company': CompanySerializer(company).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='upload-image')
    def upload_image(self, request, pk=None):
        """
        Bulk upload gallery images for the company
        """
        company = self.get_object()
        serializer = CompanyImageBulkUploadSerializer(data=request.data)
        if serializer.is_valid():
            images_data = serializer.validated_data.get('images', [])
            captions_data = serializer.validated_data.get('caption', [])
            
            created_images = []
            # Get the current highest order to append new images
            last_order = CompanyImage.objects.filter(company=company).order_by('-order').values_list('order', flat=True).first() or 0
            
            for index, image_file in enumerate(images_data):
                # Map caption to image by index. If only one caption is sent for multiple images, 
                # apply that single caption to all images in the batch.
                if len(captions_data) == 1 and len(images_data) > 1:
                    curr_caption = captions_data[0]
                else:
                    curr_caption = captions_data[index] if index < len(captions_data) else ""

                img = CompanyImage.objects.create(
                    company=company,
                    image=image_file,
                    caption=curr_caption,
                    order=last_order + index + 1
                )
                created_images.append(img)
            
            # Re-fetch company with prefetched images to ensure the response reflects new additions
            company = self.get_queryset().get(pk=company.pk)
            company_serializer = CompanySerializer(company, context={'request': request})
            return Response(
                {
                    "message": f"Successfully uploaded {len(created_images)} images.",
                    "company": company_serializer.data
                }, 
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='add-milestone')
    def add_milestone(self, request, pk=None):
        """
        Add a milestone to the company history
        """
        company = self.get_object()
        serializer = CompanyMilestoneSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(company=company)
            # Re-fetch company with prefetched milestones to ensure the response reflects new additions
            company = self.get_queryset().get(pk=company.pk)
            company_serializer = CompanySerializer(company, context={'request': request})
            return Response(company_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)