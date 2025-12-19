
import json
import logging
import os
import requests
from django.http import Http404
from rest_framework.exceptions import PermissionDenied
import boto3
# Set up logging
logger = logging.getLogger(__name__)
from django.conf import settings
from projects.models import Project, ProjectSkill  # Add ProjectSkill import
from projects.serializers import ProjectListSerializer
from jobs.serializers import JobListSerializer
from django.utils import timezone
import time
from django.db import transaction, models, IntegrityError
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Case, Q, When, F, OuterRef, Subquery, Count
from django.db.models.functions import Coalesce
from django.utils.text import get_valid_filename
from applications.models import JobApplication as Application
from rest_framework import status, permissions, viewsets, filters, mixins, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework import permissions


class IsCandidateUser(permissions.BasePermission):
    """
    Custom permission to only allow candidate users to access the view.
    """
    def has_permission(self, request, view):
        # Check if the user is authenticated and has a candidate profile
        return bool(request.user and hasattr(request.user, 'candidate_profile'))

    def has_object_permission(self, request, view, obj):
        # For object-level permission, check if the object belongs to the user's candidate profile
        return obj.candidate.user == request.user
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from utils.pagination import CustomPagination
from accounts.views import BaseRoleRegistrationView
from jobs.models import Job
from .models import ReferenceRequest
from .serializers import CandidateSerializer, CandidateProfileUpdateSerializer
from jobs.serializers import JobListSerializer
from projects.serializers import ProjectListSerializer
from companies.models import Company
from employers.models import Employer
from .models import Candidate, ReferenceRequest, WorkDNAQuestion
from .serializers import (
    CandidateListSerializer,
    CandidateProfileUpdateSerializer,
    CandidateSerializer,
    ReferenceRequestSerializer,
    WorkDNAQuestionSerializer,
    CompanyWithOpeningsSerializer,
    CandidateSerializer,
    DiscoverTalentSerializer,
)
from employers.serializers import EmployerCompanyConversationSummarySerializer
from chat.models import ChatMessage
from rest_framework.pagination import PageNumberPagination
from rest_framework.generics import ListAPIView
from jobs.models import Job
from projects.models import Project
from jobs.serializers import JobListSerializer
from projects.serializers import ProjectListSerializer
from django.urls import reverse
from django.http import JsonResponse
import requests
from rest_framework.reverse import reverse as drf_reverse
from applications.models import ProjectApplication
exception_logger = logging.getLogger("exceptions")


class PublicProjectListAPIView(ListAPIView):
    """
    Public API endpoint for listing all active projects
    No authentication required
    """
    queryset = Project.objects.filter(status='active')
    serializer_class = ProjectListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'budget', 'deadline']
    filterset_fields = {
        'project_type': ['exact'],
        'complexity': ['exact'],
        'work_style': ['exact'],
        'collaboration_style': ['exact'],
    }


class PublicJobListAPIView(ListAPIView):
    """
    Public API endpoint for listing all active jobs
    No authentication required
    """
    queryset = Job.objects.filter(status='active')
    serializer_class = JobListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title', 'description', 'company__name']
    ordering_fields = ['created_at', 'salary_min', 'salary_max', 'application_deadline']
    filterset_fields = {
        'job_type': ['exact'],
        'work_style': ['exact'],
        'education_level': ['exact'],
        'is_remote': ['exact'],
    }


class CandidateRegistrationView(BaseRoleRegistrationView):
    """Register a new candidate user (role is forced to candidate)."""
    fixed_user_type = "candidate"

class DashboardBaseView(APIView):
    """Base view for dashboard endpoints with common functionality."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_candidate_profile(self, user):
        try:
            return user.candidate_profile
        except Candidate.DoesNotExist:
            exception_logger.error(f"User {user.id} tried to access candidate endpoint but has no candidate profile")
            raise PermissionDenied('You must be logged in as a candidate to access this resource.')


class CandidateDashboardView(DashboardBaseView):
    """Legacy dashboard endpoint that combines all dashboard data."""
    def get(self, request):
        # This is the original dashboard endpoint that combines all data
        # It's kept for backward compatibility but can be deprecated later
  
        base_url = request.build_absolute_uri('/')
        
        # Get profile data
        profile_url = base_url.rstrip('/') + drf_reverse('candidate-profile-dashboard')
        profile_response = requests.get(
            profile_url,
            headers={'Authorization': request.META.get('HTTP_AUTHORIZATION', '')}
        )
        
        if profile_response.status_code != 200:
            return Response(
                {'error': 'Could not fetch profile data'}, 
                status=profile_response.status_code
            )
            
        response_data = profile_response.json()
        
        # Add other dashboard data
        endpoints = [
            ('applications', 'candidate-applications'),
            ('latest_jobs', 'candidate-latest-jobs'),
            ('latest_projects', 'candidate-latest-projects')
        ]
        
        for key, url_name in endpoints:
            endpoint_url = base_url.rstrip('/') + drf_reverse(url_name)
            endpoint_response = requests.get(
                endpoint_url,
                headers={'Authorization': request.META.get('HTTP_AUTHORIZATION', '')}
            )
            
            if endpoint_response.status_code == 200:
                response_data.update(endpoint_response.json())
        
        return Response(response_data)


class CandidateProfileDashboardView(DashboardBaseView):
    """Endpoint for candidate profile data in dashboard."""
    def get(self, request):
        candidate = self.get_candidate_profile(request.user)
        serializer = CandidateSerializer(candidate, context={'request': request})
        
        # Get counts for dashboard
        applications_count = Application.objects.filter(
            candidate=candidate, 
            status__in=['pending', 'in_review', 'shortlisted', 'interview', 'offer']
        ).count()
        
        job_applications_count = Application.objects.filter(
            candidate=candidate,
            job__isnull=False,
            status__in=['pending', 'in_review', 'shortlisted', 'interview', 'offer']
        ).count()
        
        project_applications_count = applications_count - job_applications_count
        
        references_count = Reference.objects.filter(
            candidate=candidate,
            is_public=True
        ).count()
        
        reference_requests_count = ReferenceRequest.objects.filter(
            candidate=candidate
        ).count()
        
        return Response({
            'profile': serializer.data,
            'profile_completed': candidate.is_profile_complete,
            'applications_count': applications_count,
            'job_applications_count': job_applications_count,
            'project_applications_count': project_applications_count,
            'references_count': references_count,
            'reference_requests_count': reference_requests_count,
        })


class CandidateApplicationsView(DashboardBaseView):
    """Endpoint for candidate's recent applications."""
    def get(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            candidate = self.get_candidate_profile(request.user)
            
            # Get job applications
            job_applications = list(Application.objects.filter(
                candidate=candidate
            ).select_related('job', 'job__company').order_by('-applied_at'))
            
            # Get project applications
            project_applications = list(ProjectApplication.objects.filter(
                candidate=candidate
            ).select_related('project', 'project__company').order_by('-applied_at'))
            
            # Log counts for debugging
            logger.info(f"Found {len(job_applications)} job applications and {len(project_applications)} project applications")
            
            # Combine and sort all applications by applied_at
            all_applications = []
            
            for app in job_applications:
                all_applications.append({
                    'type': 'job',
                    'object': app,
                    'applied_at': app.applied_at
                })
                
            for app in project_applications:
                all_applications.append({
                    'type': 'project',
                    'object': app,
                    'applied_at': app.applied_at
                })
            
            # Sort by applied_at in descending order
            all_applications.sort(key=lambda x: x['applied_at'], reverse=True)
            
            # Prepare response data - using all applications now
            applications_data = []
            for app in all_applications:
                app_obj = app['object']
                if app['type'] == 'job':
                    applications_data.append({
                        'app_id': app_obj.id,
                        'id': app_obj.job.id,
                        'title': app_obj.job.title if hasattr(app_obj, 'job') and app_obj.job else 'Unknown Job',
                        'company': app_obj.job.company.name if hasattr(app_obj, 'job') and hasattr(app_obj.job, 'company') and app_obj.job.company else 'Unknown Company',
                        'status': app_obj.status,
                        'applied_at': app_obj.applied_at,
                        'type': 'job'
                    })
                else:  # project application
                    applications_data.append({
                        'app_id': app_obj.id,
                        'id': app_obj.project.id,
                        'title': app_obj.project.title if hasattr(app_obj, 'project') and app_obj.project else 'Unknown Project',
                        'company': app_obj.project.company.name if hasattr(app_obj, 'project') and hasattr(app_obj.project, 'company') and app_obj.project.company else 'Unknown Company',
                        'status': app_obj.status,
                        'applied_at': app_obj.applied_at,
                        'type': 'project'
                    })
            
            return Response({
                'applications': applications_data,
                'total_applications': len(job_applications) + len(project_applications),
                'job_applications_count': len(job_applications),
                'project_applications_count': len(project_applications)
            })
            
        except Exception as e:
            exception_logger.exception("Error fetching applications")
            logger.error(f"Error fetching applications: {str(e)}", exc_info=True)
            return Response(
                {'error': 'An error occurred while fetching applications'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        


class CandidateLatestJobsView(ListAPIView):
    """Endpoint for latest jobs relevant to candidate."""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination
    serializer_class = JobListSerializer
    
    def get_candidate_profile(self, user):
        """Get the candidate profile for the authenticated user."""
        try:
            return user.candidate_profile
        except Candidate.DoesNotExist:
            raise NotFound("Candidate profile not found for this user.")
            
    def get_queryset(self):
        candidate = self.get_candidate_profile(self.request.user)
        logger = logging.getLogger(__name__)
        
        # Try to get personalized jobs from ML endpoint
        self.ml_success = False
        latest_jobs = []
        
        try:
            # Get ML URL from environment variable with fallback
            ml_base_url = f"{settings.FLIT_AI_URL}/"
                
            ml_url = f"{ml_base_url.rstrip('/')}/show_jobs_for_candidate/{candidate.id}"
            logger.info(f"Calling ML service at: {ml_url}")
            
            # Increased timeout to 5 minutes (300 seconds)
            ml_response = requests.get(ml_url, timeout=300)
            logger.info(f"ML service response status: {ml_response.status_code}")
            logger.debug(f"ML service response content: {ml_response.text}")
            
            if ml_response.status_code == 200:
                try:
                    ml_data = ml_response.json()
                    logger.info(f"ML service response data: {json.dumps(ml_data, indent=2)}")
                    
                    # Check for 'ranked_opportunities' key and that it's a list
                    ranked_opportunities = ml_data.get('ranked_opportunities')
                    if isinstance(ranked_opportunities, list) and ranked_opportunities:
                        logger.info(f"Found {len(ranked_opportunities)} job opportunities in ML response")
                        
                        # Process each job in the ML response
                        for job_data in ranked_opportunities:
                            try:
                                job_id = job_data.get('job_id') or job_data.get('id')
                                if job_id is None:
                                    logger.warning("Skipping job without job_id")
                                    continue
                                
                                # Create a dictionary with the transformed job data
                                job = {
                                    'id': job_id,
                                    'title': job_data.get('title', 'No Title'),
                                    'description': job_data.get('description', ''),
                                    'workStyle': job_data.get('work_style', 'remote'),
                                    'category': job_data.get('category', 'other'),
                                    'experienceLevel': job_data.get('experience_level', 'mid'),
                                    'employmentType': job_data.get('employment_type', 'full-time'),
                                    'salaryRangeMin': job_data.get('salary_range', {}).get('min'),
                                    'salaryRangeMax': job_data.get('salary_range', {}).get('max'),
                                    'status': job_data.get('status', 'active'),
                                    'created_at': job_data.get('created_at', timezone.now().isoformat()),
                                    'location': job_data.get('location'),
                                    'skills': job_data.get('skills', [])
                                }
                                
                                # Add company information if available
                                company_data = job_data.get('company', {})
                                if company_data:
                                    job.update({
                                        'company_name': company_data.get('company_name', 'Unknown Company'),
                                        'company_id': company_data.get('id')
                                    })
                                
                                latest_jobs.append(job)
                                logger.info(f"Added job from ML data: {job_id} - {job['title']}")
                                
                                # Limit to 10 jobs
                                if len(latest_jobs) >= 10:
                                    break
                                    
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Invalid job ID format: {job_data.get('job_id') or job_data.get('id')}")
                                logger.error(f"Error processing job data: {str(e)}", exc_info=True)
                        
                        if latest_jobs:
                            self.ml_success = True
                            logger.info(f"Successfully got {len(latest_jobs)} jobs from ML service")
                            return latest_jobs
                        else:
                            logger.warning("No valid jobs processed from ML response")
                    else:
                        logger.warning("No ranked_opportunities found or empty in ML response")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse ML service response: {e}")
            else:
                logger.warning(f"ML service returned status code: {ml_response.status_code}")
                logger.warning(f"Response content: {ml_response.text}")
                
        except requests.RequestException as e:
            logger.error(f"Request to ML service failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error calling ML service: {str(e)}", exc_info=True)
        
        # Fallback to original logic if ML fails or no results
        if not ml_success:
            logger.info("Falling back to database query for latest jobs")
            # Get candidate's skills for filtering (original logic) - but you're not using skills filter here?
            # candidate_skills = candidate.skills or []  # Unused in fallback?
            
            # Get latest active jobs, ordered by creation date
            latest_jobs = Job.objects.filter(
                status='active'
            ).select_related('company').order_by('-created_at')[:10]
        
        return latest_jobs or []
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Check if we have Job objects or dictionaries
        if not queryset:
            return self.get_paginated_response({
                'latest_jobs': [],
                'ml_success': getattr(self, 'ml_success', False)
            })
            
        if isinstance(queryset[0], dict):
            # For dictionaries from ML service
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                return self.get_paginated_response({
                    'latest_jobs': page,
                    'ml_success': getattr(self, 'ml_success', False)
                })
                
            # Fallback if pagination is not applied
            return Response({
                'count': len(queryset),
                'next': None,
                'previous': None,
                'total_pages': 1,
                'current_page': 1,
                'latest_jobs': queryset,
                'ml_success': getattr(self, 'ml_success', False)
            })
        else:
            # For Job objects from database, use the standard list method
            return super().list(request, *args, **kwargs)

class CandidateLatestProjectsView(ListAPIView):
    """Endpoint for latest projects relevant to candidate."""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination
    serializer_class = ProjectListSerializer
    
    def get_queryset(self):
        candidate = self.get_candidate_profile(self.request.user)
        logger = logging.getLogger(__name__)
        
        # Try to get personalized projects from ML endpoint
        self.ml_success = False
        latest_projects = []
        
        try:
            # Get ML URL from environment variable with fallback
            ml_base_url = f"{settings.FLIT_AI_URL}/"
            ml_url = f"{ml_base_url.rstrip('/')}/show_projects_for_candidate/{candidate.id}"
            logger.info(f"Calling ML service at: {ml_url}")
            
            # Increased timeout to 5 minutes (300 seconds)
            ml_response = requests.get(ml_url, timeout=300)
            logger.info(f"ML service response status: {ml_response.status_code}")
            
            if ml_response.status_code == 200:
                try:
                    ml_data = ml_response.json()
                    ranked_projects = ml_data.get('ranked_projects', [])
                    
                    if isinstance(ranked_projects, list) and ranked_projects:
                        logger.info(f"Found {len(ranked_projects)} project opportunities in ML response")
                        
                        for project_data in ranked_projects:
                            try:
                                project_id = project_data.get('id')
                                if project_id is not None:
                                    project = {
                                        'id': project_id,
                                        'title': project_data.get('title', 'No Title'),
                                        'description': project_data.get('description', ''),
                                        'category': project_data.get('category', 'other'),
                                        'status': project_data.get('status', 'active'),
                                        'created_at': project_data.get('created_at', timezone.now().isoformat()),
                                        'skills': project_data.get('skills', [])
                                    }
                                    latest_projects.append(project)
                                    
                                    if len(latest_projects) >= 10:
                                        break
                                        
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Invalid project data: {str(e)}")
                        
                        if latest_projects:
                            self.ml_success = True
                            logger.info(f"Successfully got {len(latest_projects)} projects from ML service")
                            return latest_projects
                            
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse ML service response: {e}")
            else:
                logger.warning(f"ML service returned status code: {ml_response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Request to ML service failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error calling ML service: {str(e)}", exc_info=True)
        
        # Fallback to database if ML service fails or returns no results
        logger.info("Falling back to database query for latest projects")
        return Project.objects.filter(
            status='active'
        ).select_related('company').order_by('-created_at')[:10]
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Check if we have Project objects or dictionaries
        if not queryset:
            return self.get_paginated_response({
                'latest_projects': [],
                'ml_success': getattr(self, 'ml_success', False)
            })
            
        if isinstance(queryset[0], dict):
            # For dictionaries from ML service
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                return self.get_paginated_response({
                    'latest_projects': page,
                    'ml_success': getattr(self, 'ml_success', False)
                })
                
            # Fallback if pagination is not applied
            return Response({
                'count': len(queryset),
                'next': None,
                'previous': None,
                'total_pages': 1,
                'current_page': 1,
                'latest_projects': queryset,
                'ml_success': getattr(self, 'ml_success', False)
            })
        else:
            # For Project objects from database, use the standard list method
            return super().list(request, *args, **kwargs)
    
    def get_candidate_profile(self, user):
        """Get the candidate profile for the authenticated user."""
        try:
            return user.candidate_profile
        except Candidate.DoesNotExist:
            raise NotFound("Candidate profile not found for this user.")

    # Keep the original get method for backward compatibility
    def get(self, request):
        candidate = self.get_candidate_profile(request.user)
        logger = logging.getLogger(__name__)
        
        # Try to get personalized projects from ML endpoint
        ml_success = False
        latest_projects = []
        ml_data = None
        
        try:
            ml_url = f"{settings.FLIT_AI_URL}/show_projects_for_candidate/{candidate.id}"
            logger.info(f"Calling ML service for projects at: {ml_url}")
            
            # Add headers if needed (e.g., for authentication)
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Increase timeout to 30 seconds and add retry logic
            max_retries = 2
            retry_delay = 5  # seconds
            
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Attempt {attempt + 1}/{max_retries + 1} to call ML service")
                    
                    # Log the full request details
                    logger.info(f"Sending GET request to ML service with headers: {headers}")
                    
                    # Increased timeout to 5 minutes (300 seconds)
                    ml_response = requests.get(ml_url, headers=headers, timeout=300)
                    logger.info(f"ML service response status: {ml_response.status_code}")
                    logger.info(f"Response headers: {dict(ml_response.headers)}")
                    
                    # Log response content for debugging (first 1000 chars)
                    response_preview = ml_response.text[:1000]
                    logger.info(f"Response preview: {response_preview}")
                    
                    # If we got a successful response, break out of the retry loop
                    if ml_response.status_code == 200:
                        break
                        
                except requests.exceptions.Timeout:
                    if attempt == max_retries:
                        exception_logger.error(f"ML service timed out after {max_retries + 1}attempts")
                        logger.error(f"ML service timed out after {max_retries + 1} attempts")
                        raise
                    logger.warning(f"ML service timed out, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries:
                        exception_logger.exception(f"Failed to call ML service after {max_retries + 1} attempts")
                        logger.error(f"Failed to call ML service after {max_retries + 1} attempts: {str(e)}")
                        raise
                    logger.warning(f"Error calling ML service, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries}): {str(e)}")
                    time.sleep(retry_delay)
            
            if ml_response.status_code == 200:
                try:
                    ml_data = ml_response.json()
                    logger.info(f"ML service response data type: {type(ml_data)}")
                    
                    # Check if we have a direct list of projects or ranked_projects
                    if isinstance(ml_data, list):
                        logger.info(f"Received direct list of {len(ml_data)} projects from ML service")
                        ml_data = {'opportunities': ml_data}
                    # Check for ranked_projects in the response
                    elif 'ranked_projects' in ml_data and isinstance(ml_data['ranked_projects'], list):
                        logger.info(f"Found {len(ml_data['ranked_projects'])} projects in ranked_projects")
                        ml_data['opportunities'] = ml_data.pop('ranked_projects')
                    
                    project_ids = []
                    project_data_map = {}
                    
                    # Try to get project IDs from the opportunities array if it exists
                    if 'opportunities' in ml_data and isinstance(ml_data['opportunities'], list):
                        logger.info(f"Found {len(ml_data['opportunities'])} project opportunities in ML response")
                        
                        # Extract valid project IDs from opportunities and build project data map
                        for project_data in ml_data['opportunities']:
                            try:
                                project_id = project_data.get('project_id') or project_data.get('id')
                                if project_id is not None:
                                    project_id = int(project_id)
                                    project_ids.append(project_id)
                                    project_data_map[project_id] = project_data
                            except (ValueError, TypeError) as e:
                                exception_logger.exception(f"Invalid project ID in ML response: {project_data.get('project_id') or project_data.get('id')}")
                                logger.warning(f"Invalid project ID in ML response: {project_data.get('project_id') or project_data.get('id')}")
                    
                    # If no project IDs found in opportunities, try the root level ranked_opportunity_ids
                    if not project_ids and 'ranked_opportunity_ids' in ml_data and isinstance(ml_data['ranked_opportunity_ids'], list):
                        logger.info(f"Found {len(ml_data['ranked_opportunity_ids'])} project IDs in ranked_opportunity_ids")
                        for project_id in ml_data['ranked_opportunity_ids']:
                            try:
                                project_id = int(project_id)
                                project_ids.append(project_id)
                            except (ValueError, TypeError):
                                exception_logger.exception(f"Invalid project ID in ranked_opportunity_ids: {project_id}")
                                logger.warning(f"Invalid project ID in ranked_opportunity_ids: {project_id}")
                    
                    # If we still don't have project IDs, check if we have direct project data
                    if not project_ids and isinstance(ml_data, dict):
                        # Look for any list that might contain project data
                        for key, value in ml_data.items():
                            if isinstance(value, list) and value and isinstance(value[0], dict):
                                if 'project_id' in value[0] or 'id' in value[0]:
                                    logger.info(f"Found potential project data in key: {key}")
                                    for item in value:
                                        try:
                                            project_id = item.get('project_id') or item.get('id')
                                            if project_id is not None:
                                                project_id = int(project_id)
                                                project_ids.append(project_id)
                                                project_data_map[project_id] = item
                                        except (ValueError, TypeError):
                                            exception_logger.exception(f"Invalid project ID in {key}: {item.get('project_id') or item.get('id')}")
                                            logger.warning(f"Invalid project ID in {key}: {item.get('project_id') or item.get('id')}")
                    
                    if project_ids:
                        logger.info(f"Processing {len(project_ids)} projects from ML response")
                        
                        # Remove duplicates while preserving order
                        seen = set()
                        project_ids = [x for x in project_ids if not (x in seen or seen.add(x))]
                        
                        # Create a list to hold all projects
                        latest_projects = []
                        
                        # Process each project from the ML response
                        for project_id in project_ids:
                            project_data = project_data_map.get(project_id)
                            if not project_data:
                                continue
                                
                            try:
                                logger.info(f"Processing project from ML data: {project_id} - {project_data.get('title')}")
                                
                                # Try to get the project from the database first
                                try:
                                    project = Project.objects.get(id=project_id, status='active')
                                    logger.info(f"Found existing project in database: {project_id}")
                                    
                                    # Update skills from ML response if available
                                    if 'skills' in project_data:
                                        project._skills = project_data['skills']
                                    
                                    latest_projects.append(project)
                                    continue
                                except Project.DoesNotExist:
                                    # exception_logger.error(f"Project.DoesNotExist: Active project not found for project_id={project_id}")
                                    pass
                                
                                # If not in database, create a new project from ML data
                                project = Project(
                                    id=project_id,
                                    title=project_data.get('title', 'No Title'),
                                    description=project_data.get('description', ''),
                                    paymentType=project_data.get('payment_type', 'fixed'),
                                    paymentAmount=project_data.get('payment_amount') or 0,
                                    estimatedHours=project_data.get('estimated_hours', '1-2 weeks'),
                                    work_style=project_data.get('work_style', 'remote'),
                                    status='active',
                                    category=project_data.get('category', 'other')
                                )
                                
                                # Set skills from ML response if available
                                if 'skills' in project_data and project_data['skills']:
                                    project._skills = project_data['skills']
                                    
                                    # Create ProjectSkill objects for each skill
                                    # Skip creating ProjectSkill objects since we're not saving the project
                                    # Just keep the skills in the _skills attribute for the response
                                
                                latest_projects.append(project)
                                logger.info(f"Created project from ML data: {project_id} with skills: {project_data.get('skills', [])}")
                                
                            except Exception as e:
                                exception_logger.exception(f"Error processing project with project_id={project_id}")
                                logger.error(f"Error processing project {project_id}: {str(e)}", exc_info=True)
                    
                    if latest_projects:
                        ml_success = True
                        logger.info(f"Successfully got {len(latest_projects)} projects from ML service")
                    else:
                        logger.warning("No projects found in ML service")
                        
                except json.JSONDecodeError as e:
                    exception_logger.exception("Failed to parse ML service response as JSON")
                    logger.error(f"Failed to parse ML service response as JSON: {e}")
                    logger.info(f"Raw response content: {ml_response.text[:500]}...")  # Log first 500 chars of response
                except Exception as e:
                    exception_logger.exception("Unexpected error processing ML response")
                    logger.error(f"Unexpected error processing ML response: {str(e)}", exc_info=True)
            else:
                logger.warning(f"ML service returned status code: {ml_response.status_code}")
                logger.warning(f"Response content: {ml_response.text[:500]}...")  # Log first 500 chars of response
                
        except requests.RequestException as e:
            exception_logger.exception("Request to ML service failed")
            error_msg = f"Request to ML service failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f"\nResponse status: {e.response.status_code}"
                try:
                    error_msg += f"\nResponse content: {e.response.text[:500]}"
                except:
                    pass
            logger.error(error_msg, exc_info=True)
        except Exception as e:
            exception_logger.exception("Unexpected error calling ML service")
            logger.error(f"Unexpected error calling ML service: {str(e)}", exc_info=True)
        
        # Prepare the response data - only include projects if we successfully got them from ML service
        response_data = []
        
        if ml_success and latest_projects:
            for project in latest_projects:
                # Get project data from the database or ML response
                project_data = {
                    'id': project.id,
                    'title': project.title,
                    'description': project.description or '',
                    'category': project.category or 'other',
                    'estimatedHours': project.estimatedHours or '1-2 weeks',
                    'paymentType': project.paymentType or 'fixed',
                    'paymentAmount': project.paymentAmount or 0,
                    'deadline': project.deadline.strftime('%Y-%m-%d') if hasattr(project, 'deadline') and project.deadline else None,
                    'status': project.status,
                    'created_at': project.created_at.strftime('%Y-%m-%dT%H:%M:%SZ') if project.created_at else None,
                    'company_name': project.company.company_name if hasattr(project, 'company') and project.company else None,
                    'company_id': project.company.id if hasattr(project, 'company') and project.company else None,
                    'skills': []
                }
                
                # Add skills from _skills if available, otherwise use the related skills
                if hasattr(project, '_skills') and project._skills:
                    project_data['skills'] = project._skills
                else:
                    # Fall back to database skills if _skills is not set
                    project_data['skills'] = list(project.required_skills.values_list('name', flat=True))
                
                response_data.append(project_data)
        
        # Apply pagination
        page = self.paginate_queryset(response_data)
        if page is not None:
            return self.get_paginated_response({
                'latest_projects': page,
                'ml_success': ml_success
            })
            
        # Fallback if pagination is not applied
        return Response({
            'count': len(response_data),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'latest_projects': response_data,
            'ml_success': ml_success,
            'message': 'ML projects retrieved successfully' if ml_success and response_data else 'No ML projects found'
        })


class CandidateViewSet(viewsets.ModelViewSet):
    """ViewSet for candidate endpoints."""
    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        # Add our custom response data to the paginated response
        response.data.update({
            'total_companies': self.queryset.count() if hasattr(self, 'queryset') else 0,
            'total_jobs': Job.objects.count(),
            'total_projects': Project.objects.count(),
        })
        return response

    def _get_candidate_profile(self, user):
        try:
            return user.candidate_profile
        except Candidate.DoesNotExist:
            exception_logger.error("Candidate.DoesNotExist: Candidate profile not found for this request")
            return Response({'error': 'Candidate profile not found'}, status=status.HTTP_404_NOT_FOUND)

    def _save_file(self, file_obj, storage_path_prefix, request):
        try:
            # Get file extension and name without extension
            file_name, file_ext = os.path.splitext(get_valid_filename(file_obj.name))
            # Add timestamp to filename to prevent overwrites
            timestamp = int(time.time())
            unique_filename = f"{file_name}_{timestamp}{file_ext}"
            
            # Save the file with the new unique filename
            storage_path = default_storage.save(
                f'{storage_path_prefix}/{unique_filename}', 
                file_obj
            )
            
            # Always return the relative storage path (not the full URL)
            # The URL will be constructed when needed using request.build_absolute_uri()
            return storage_path
        except Exception as e:
            exception_logger.exception(f"File saving failed in _save_file: {str(e)}")
            return None

    def retrieve(self, request, pk=None):
        # Support viewing by either candidate PK or user ID on the same endpoint.
        candidate = None
        viewed_publicly = False
        # 1) Try by USER ID with public visibility first (to prefer user.id semantics)
        try:
            candidate = Candidate.objects.get(user__id=pk, profile_visibility="public")
            viewed_publicly = True
        except Candidate.DoesNotExist:
            exception_logger.error("Candidate.DoesNotExist: Candidate not found for this request")
            candidate = None
        # 2) If not found, try by candidate PK with public visibility
        if candidate is None:
            try:
                candidate = Candidate.objects.get(pk=pk, profile_visibility="public")
                viewed_publicly = True
            except Candidate.DoesNotExist:
                exception_logger.error("Candidate.DoesNotExist: Candidate not found for this request")
                candidate = None
        # 3) If still not found, allow owner to view their own profile regardless of visibility (by either key)
        if candidate is None and getattr(request.user, 'is_authenticated', False):
            try:
                candidate = Candidate.objects.get(Q(pk=pk) | Q(user__id=pk), user=request.user)
                viewed_publicly = False
            except Candidate.DoesNotExist:
                exception_logger.error("Candidate.DoesNotExist: Candidate not found for this request")
                candidate = None
        if candidate is None:
            return Response(
                {"detail": "Candidate not found or profile is not public"},
                status=status.HTTP_404_NOT_FOUND
            )
        if viewed_publicly and hasattr(request.user, 'employer_profile'):
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

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code != status.HTTP_201_CREATED:
            return response

        ml_success = False
        candidate_profile_summary = None
        candidate_tags = []
        ml_error = None

        candidate_id = response.data.get('id')
        candidate = None

        if not candidate_id:
            ml_error = 'Candidate ID missing in response; cannot trigger ML sync'
            logger.error(ml_error)
        else:
            try:
                candidate = Candidate.objects.get(id=candidate_id)
            except Candidate.DoesNotExist:
                exception_logger.error("Candidate.DoesNotExist: Candidate with ID {candidate_id} not found for ML sync")
                ml_error = f'Candidate with ID {candidate_id} not found for ML sync'
                logger.error(ml_error)

        if candidate:
            # Prepare ML API URL and payload
            ml_api_url = f"{settings.FLIT_AI_URL}/create_candidates/{candidate.id}"
            ml_payload = {
                "full_name": candidate.full_name,
                "title": candidate.title,
                "bio": candidate.bio or "",
                "location": candidate.location,
                "work_style": candidate.work_style,
                "availability_type": candidate.availability_type,
                "is_available": candidate.is_available,
                "skills": candidate.skills or [],
                "superpowers": candidate.superpowers or [],
                "preferred_roles": candidate.preferred_roles or [],
                "seniority_level": candidate.seniority_level,
                "min_salary": candidate.min_salary,
                "max_salary": candidate.max_salary,
                "salary_currency": candidate.salary_currency,
                "portfolio_links": candidate.portfolio_links or [],
                "resume_url": candidate.resume_url,
                "video_intro_url": candidate.video_intro_url,
                "profile_visibility": candidate.profile_visibility,
                "user_id": candidate.user.id if hasattr(candidate, 'user') and candidate.user else None,
                "email": candidate.user.email if hasattr(candidate, 'user') and candidate.user else None,
                "resume_data": getattr(candidate, 'resume_data', None),  # Include resume data if available
            }

            max_retries = 3  # Increased retries for better reliability
            timeout_seconds = 45  # Increased timeout for ML processing
            ml_response = None

            # Configure headers with content type
            headers = {
                "Content-Type": "application/json",
                # Uncomment and update if API key is required
                # "Authorization": f"Bearer {settings.ML_API_KEY}"
            }

            # Make the API call with retry logic
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Calling Candidate create ML API (attempt {attempt + 1}/{max_retries + 1}) for candidate {candidate.id}")
                    logger.debug(f"ML API URL: {ml_api_url}")
                    logger.debug(f"ML Payload: {json.dumps(ml_payload, indent=2)}")
                    
                    ml_response = requests.post(
                        ml_api_url,
                        json=ml_payload,
                        headers=headers,
                        timeout=timeout_seconds
                    )
                    
                    # Log the response status and content for debugging
                    logger.info(f"ML API Response Status: {ml_response.status_code}")
                    logger.debug(f"ML API Response: {ml_response.text}")
                    
                    # If we get a successful response, break out of the retry loop
                    if ml_response.status_code in (200, 201):
                        break
                        
                except requests.exceptions.Timeout:
                    if attempt == max_retries:
                        exception_logger.error("Candidate create ML API timed out after maximum retries")
                        ml_error = "Candidate create ML API timed out after retries"
                        logger.error(ml_error)
                        break
                    logger.warning(f"Candidate create ML API timeout (attempt {attempt + 1}), retrying...")
                    time.sleep(1)  # Wait before retry
                except requests.exceptions.RequestException as exc:
                    if attempt == max_retries:
                        exception_logger.exception("Candidate create ML API request failed after all retries")
                        ml_error = f"Candidate create ML API request failed: {str(exc)}"
                        logger.error(ml_error, exc_info=True)
                        break
                    logger.warning(f"Candidate create ML API request failed (attempt {attempt + 1}), retrying...")
                    time.sleep(1)  # Wait before retry
                except requests.exceptions.Timeout:
                    if attempt == max_retries:
                        exception_logger.error("Candidate create ML API timed out after maximum retries")
                        ml_error = "Candidate create ML API timed out after retries"
                        logger.error(ml_error)
                        break
                    logger.warning(f"Candidate create ML API timeout (attempt {attempt + 1}), retrying...")
                    time.sleep(1)
                except requests.exceptions.RequestException as exc:
                    exception_logger.exception("Candidate create ML API request failed")
                    ml_error = f"Candidate create ML API request failed: {str(exc)}"
                    logger.error(ml_error, exc_info=True)
                    break

            # Process the ML API response
            if ml_response is not None and ml_response.status_code in (200, 201):
                try:
                    ml_data = ml_response.json()
                    logger.info(f"Successfully received data from ML API for candidate {candidate.id}")
                    
                    # Extract data from ML API response
                    candidate_profile_summary = ml_data.get('candidate_profile_summary')
                    candidate_tags = ml_data.get('candidate_tags', [])
                    
                    # You can add more fields from ML response as needed
                    updates = {}
                    if candidate_profile_summary is not None:
                        updates['candidate_profile_summary'] = candidate_profile_summary
                    if candidate_tags:
                        updates['candidate_tags'] = candidate_tags
                    
                    # Update candidate with ML data if any updates are available
                    if updates:
                        try:
                            for field, value in updates.items():
                                setattr(candidate, field, value)
                            candidate.save(update_fields=list(updates.keys()))
                            logger.info(f"Successfully updated candidate {candidate.id} with ML data")
                            ml_success = True
                        except Exception as save_exc:
                            exception_logger.exception(f"Error saving ML data to candidate {candidate.id}")
                            ml_error = f"Error saving ML data: {str(save_exc)}"
                            logger.error(ml_error)
                    else:
                        logger.info("No updates to save from ML API response")
                        ml_success = True  # Still mark as success if no updates needed
                        
                except json.JSONDecodeError:
                    ml_error = "Invalid JSON response from Candidate create ML API"
                    exception_logger.exception(ml_error)
                    logger.error(f"Response content: {ml_response.text}")
                except Exception as exc:
                    ml_error = f"Error processing ML API response: {str(exc)}"
                    exception_logger.exception(ml_error)
            elif ml_response is not None:
                # Handle non-200/201 responses
                ml_error = f"Candidate create ML API returned status code {ml_response.status_code}"
                logger.error(f"{ml_error}. Response content: {ml_response.text}")
                
                # Try to extract more detailed error message if available
                try:
                    error_data = ml_response.json()
                    if 'detail' in error_data:
                        ml_error = f"ML API Error: {error_data['detail']}"
                except:
                    pass  # If we can't parse the error, use the default message

        # Prepare the response data
        response_data = {
            'message': 'Candidate created successfully',
            'ml_success': ml_success,
            'candidate_profile_summary': candidate_profile_summary,
            'candidate_tags': candidate_tags,
            'data': response.data,
            'ml_api': {
                'called': True,
                'status': 'success' if ml_success else 'failed',
                'message': 'ML API processed successfully' if ml_success else (ml_error or 'ML API processing failed')
            }
        }
        
        # If there was an ML API error but the candidate was created successfully,
        # we still want to return a 201 status but include the ML API error details
        if not ml_success and response.status_code == 201:
            response_data['warning'] = 'Candidate created but ML processing failed'
            
        response.data = response_data

        if ml_error:
            response.data['ml_error'] = ml_error

        return response

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='views')
    def record_view(self, request, pk=None):
        try:
            employer = request.user.employer_profile
        except Exception:
            exception_logger.exception("Not Employer or Unexpected error while accessing employer_profile in record_view")
            raise PermissionDenied("Only employers can record candidate profile views.")
        try:
            candidate = Candidate.objects.get(pk=pk)
        except Candidate.DoesNotExist:
            exception_logger.error(f"Candidate.DoesNotExist: Candidate with ID {pk} not found")
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
            exception_logger.error(f"Invalid 'limit' query param: Defaulting to 12.")
            limit = 12
        jobs_qs = Job.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]
        projects_qs = Project.objects.filter(status='active').select_related('company').order_by('-created_at')[:limit]
        data['latest_jobs'] = JobListSerializer(jobs_qs, many=True).data
        data['latest_projects'] = ProjectListSerializer(projects_qs, many=True).data
        return Response(data, status=status.HTTP_200_OK)

    def _update_ml_candidate_data(self, candidate_id, data):
        """
        Update candidate data in the ML service
        
        Args:
            candidate_id: ID of the candidate to update
            data: Dictionary containing candidate data
            
        Returns:
            tuple: (success: bool, message: str, data: dict)
        """
        try:
            # Get the candidate instance
            try:
                candidate = Candidate.objects.get(id=candidate_id)
            except Candidate.DoesNotExist:
                error_msg = f"Candidate with ID {candidate_id} not found"
                logger.error(error_msg)
                return False, error_msg, None
            
            # Prepare the ML API URLs
            base_url = f"{settings.FLIT_AI_URL}/"

            # First try to update existing candidate
            update_endpoint = f"update_candidate_data/{candidate_id}"
            update_url = f"{base_url}/{update_endpoint}"
            
            # Fallback to create if update fails
            create_endpoint = f"create_candidates/{candidate_id}"
            create_url = f"{base_url}/{create_endpoint}"
            
            logger.info(f"Preparing to update ML service for candidate {candidate_id}")
            
            # Prepare the candidate data for ML service
            ml_payload = {
                "id": candidate_id,
                "full_name": candidate.full_name or "",
                "title": candidate.title or "",
                "bio": candidate.bio or "",
                "location": candidate.location or "",
                "work_style": candidate.work_style or "",
                "availability_type": candidate.availability_type or "",
                "is_available": getattr(candidate, 'is_available', False),
                "skills": getattr(candidate, 'skills', []) or [],
                "superpowers": getattr(candidate, 'superpowers', []) or [],
                "preferred_roles": getattr(candidate, 'preferred_roles', []) or [],
                "seniority_level": candidate.seniority_level or "",
                "min_salary": getattr(candidate, 'min_salary', None),
                "max_salary": getattr(candidate, 'max_salary', None),
                "resume_url": getattr(candidate, 'resume_url', ''),
                "video_intro_url": getattr(candidate, 'video_intro_url', ''),
                "video_transcription": getattr(candidate, 'video_transcription', ''),
                "profile_visibility": getattr(candidate, 'profile_visibility', 'public'),
                "user_id": candidate.user.id if hasattr(candidate, 'user') and candidate.user else None,
                "email": candidate.user.email if hasattr(candidate, 'user') and candidate.user else None,
                "resume_data": getattr(candidate, 'resume_data', {}) or {},
                "profile_completed": getattr(candidate, 'profile_completed', False),
                "passion_projects": getattr(candidate, 'passion_projects', '') or ''
            }
            
            # Set up headers
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Try to update first
            response = None
            try:
                logger.info(f"Attempting to update candidate at: {update_url}")
                logger.debug(f"Update payload: {json.dumps(ml_payload, indent=2, default=str)}")
                
                # First try PATCH to update
                response = requests.patch(
                    update_url,
                    json=ml_payload,
                    headers=headers,
                    timeout=30
                )
                logger.debug(f"Update response: {response.status_code} - {response.text}")
                
                # If update fails with 404, try to create
                if response.status_code == 404:
                    logger.info(f"Update endpoint not found, trying create at: {create_url}")
                    response = requests.post(
                        create_url,
                        json=ml_payload,
                        headers=headers,
                        timeout=30
                    )
                    logger.debug(f"Create response: {response.status_code} - {response.text}")
                    
            except requests.exceptions.RequestException as e:
                error_msg = f"Error calling ML service: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg, None
            
            # Check if we got a valid response
            if response is None:
                error_msg = "No response received from ML service"
                logger.error(error_msg)
                return False, error_msg, None
                
            # Log the raw response for debugging
            logger.debug(f"ML service response status: {response.status_code}")
            logger.debug(f"ML service response content: {response.text}")
            
            # Check response status for success
            if response.status_code in (200, 201, 204):
                try:
                    response_data = response.json()
                    logger.info(f"Successfully updated ML service for candidate {candidate_id}")
                    return True, "Successfully updated ML service", response_data
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON response from ML service: {str(e)}. Response: {response.text[:500]}"
                    logger.error(error_msg)
                    return False, "Invalid response from ML service", None
            elif response.status_code == 404:
                error_msg = f"ML service endpoint not found (404). Please check the URL: {update_url}"
                logger.error(error_msg)
                return False, error_msg, None
            else:
                error_msg = f"ML service returned status {response.status_code}: {response.text[:500]}"
                logger.error(error_msg)
                return False, f"ML service error: {response.status_code}", None
                
        except Exception as e:
            logger.exception(f"Unexpected error in _update_ml_candidate_data for candidate {candidate_id}")
            return False, f"Unexpected error: {str(e)}", None

    def _parse_form_data(self, data):
        """Helper method to parse form data"""
        if not data:
            return {}
            
        # Create a mutable copy if it's a QueryDict
        if hasattr(data, 'copy') and not isinstance(data, dict):
            data = data.copy()
            
        # Convert QueryDict to regular dict if needed
        if hasattr(data, 'dict'):
            data = data.dict()
            
        # Make sure we're working with a dictionary
        if not isinstance(data, dict):
            return {}
            
        # Create a new dictionary to store the parsed data
        parsed_data = {}
            
        # Handle list fields
        for key in ['skills', 'languages', 'preferred_locations', 'superpowers', 'preferred_roles', 'portfolio_links']:
            if key in data:
                value = data.get(key)
                if isinstance(value, str) and (value.startswith('[') or value.startswith('{')):
                    try:
                        parsed_value = json.loads(value)
                        parsed_data[key] = parsed_value if isinstance(parsed_value, list) else [parsed_value]
                    except json.JSONDecodeError:
                        exception_logger.error(f"Invalid JSON format for key '{key}' with value: {value}")
                        parsed_data[key] = [value] if value.strip() else []
                else:
                    parsed_data[key] = self._parse_json_list(value)
        
        # Handle boolean fields
        for key in ['is_remote', 'is_available']:
            if key in data:
                parsed_data[key] = self._parse_bool(data.get(key))
        
        # Handle numeric fields
        for key in ['min_salary', 'max_salary']:
            if key in data and data.get(key) not in [None, '']:
                parsed = self._parse_int(data.get(key))
                if parsed is not None:
                    parsed_data[key] = parsed
        
        # Copy remaining fields
        for key, value in data.items():
            if key not in parsed_data:
                parsed_data[key] = value
        
        return parsed_data
        
    def _parse_json_list(self, value):
        """Parse a JSON list from string if needed"""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                exception_logger.error(f"Invalid JSON string encountered: {value}")
                return [value] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]
        
    def _parse_bool(self, value):
        """Parse boolean value from various formats"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)
        
    def _parse_int(self, value):
        """Parse integer value from string"""
        try:
            return int(value)
        except (ValueError, TypeError):
            exception_logger.error(f"Invalid integer value: {value}")
            return None
            
    def _prepare_ml_data(self, candidate):
        """Prepare candidate data for ML API update"""
        if not candidate or not hasattr(candidate, 'user'):
            return None
            
        # Handle file fields properly
        profile_picture_url = ''
        if hasattr(candidate, 'profile_picture') and candidate.profile_picture:
            try:
                profile_picture_url = candidate.profile_picture.url
            except (ValueError, AttributeError):
                profile_picture_url = ''
        
        resume_url = getattr(candidate, 'resume_url', '')
        if hasattr(resume_url, 'url'):  # If it's a FileField/ImageField
            try:
                resume_url = resume_url.url
            except (ValueError, AttributeError):
                resume_url = ''
            
        return {
            'first_name': candidate.user.first_name or '',
            'last_name': candidate.user.last_name or '',
            'email': getattr(candidate.user, 'email', ''),
            'profile_data': {
                'headline': getattr(candidate, 'headline', '') or '',
                'summary': getattr(candidate, 'summary', '') or '',
                'skills': [skill.name for skill in getattr(candidate, 'skills', []) if hasattr(skill, 'name')],
                'resume_url': resume_url or '',
                'profile_picture': profile_picture_url,
                'work_experience': [
                    {
                        'title': getattr(exp, 'title', ''),
                        'company': getattr(exp, 'company', ''),
                        'description': getattr(exp, 'description', ''),
                        'start_date': exp.start_date.isoformat() if hasattr(exp, 'start_date') and exp.start_date else None,
                        'end_date': exp.end_date.isoformat() if hasattr(exp, 'end_date') and exp.end_date else None,
                        'is_current': getattr(exp, 'is_current', False)
                    } for exp in getattr(candidate, 'work_experiences', []).all() if hasattr(candidate, 'work_experiences')
                ] if hasattr(candidate, 'work_experiences') else [],
                'education': [
                    {
                        'degree': getattr(edu, 'degree', ''),
                        'field_of_study': getattr(edu, 'field_of_study', ''),
                        'institution': getattr(edu, 'institution', ''),
                        'start_date': edu.start_date.isoformat() if hasattr(edu, 'start_date') and edu.start_date else None,
                        'end_date': edu.end_date.isoformat() if hasattr(edu, 'end_date') and edu.end_date else None
                    } for edu in getattr(candidate, 'educations', []).all() if hasattr(candidate, 'educations')
                ] if hasattr(candidate, 'educations') else []
            }
        }
        
    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def profile(self, request):
        """
        Retrieve or update the current candidate's profile.
        """
        # Get or create candidate profile
        candidate = self._get_candidate_profile(request.user)
        if isinstance(candidate, Response):
            return candidate
            
        if request.method == 'GET':
            serializer = self.get_serializer(candidate)
            return Response(serializer.data)
            
        # Parse the request data to handle JSON fields and other special types
        data = self._parse_form_data(request.data)
        
        # Create a new dictionary for the final data
        final_data = {}
        
        # Copy all non-file data from parsed data
        for key, value in data.items():
            if key not in request.FILES:  # Skip file fields
                final_data[key] = value
        
        # Handle profile picture upload
        if 'profile_image' in request.FILES:
            try:
                # Get the file from request
                profile_image = request.FILES['profile_image']
                
                # Generate a unique filename
                file_ext = os.path.splitext(profile_image.name)[1]
                filename = f"{request.user.id}_{int(time.time())}{file_ext}"
                filepath = f"candidates/profile_images/{filename}"
                
                # Save the file to S3
                s3 = boto3.client('s3',
                                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                                region_name=settings.AWS_S3_REGION_NAME)
                
                s3.upload_fileobj(
                    profile_image,
                    settings.AWS_STORAGE_BUCKET_NAME,
                    filepath,
                    ExtraArgs={
                        'ContentType': profile_image.content_type
                    }
                )
                
                # Store just the file path, not the full URL
                candidate.profile_image = filepath
                candidate.save(update_fields=['profile_image'])
                
            except Exception as e:
                exception_logger.exception("Error saving profile image")
                logger.error(f"Error saving profile image: {str(e)}", exc_info=True)
                return Response(
                    {"error": f"Failed to process profile image: {str(e)}"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Handle resume file upload and parsing
        if 'resume_file' in request.FILES:
            try:
                # First save the resume file
                resume_file = request.FILES['resume_file']
                
                # Parse the resume using the ML API
                try:
                    # Save the resume file temporarily
                    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_resumes')
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_path = os.path.join(temp_dir, resume_file.name)
                    
                    with open(temp_path, 'wb+') as destination:
                        for chunk in resume_file.chunks():
                            destination.write(chunk)
                    
                    # Call the ML API to parse the resume
                    ml_api_url = f"{settings.FLIT_AI_URL}/parse_cv"
                    
                    try:
                        with open(temp_path, 'rb') as f:
                            # Log file info for debugging
                            file_size = os.path.getsize(temp_path)
                            file_extension = os.path.splitext(resume_file.name)[1].lower()
                            logger.info(f"Sending file to ML API - Name: {resume_file.name}, Size: {file_size} bytes, Type: {file_extension}")
                            
                            # Set appropriate content type based on file extension
                            content_type = 'application/pdf'
                            if file_extension in ['.doc', '.docx']:
                                content_type = 'application/msword' if file_extension == '.doc' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                            
                            # Use 'resume_file' as the field name to match the ML API's expected field
                            files = {'resume_file': (resume_file.name, f, content_type)}
                            headers = {'accept': 'application/json'}
                            
                            # Log the request
                            logger.info(f"Sending request to ML API: {ml_api_url}")
                            
                            # Make the request with timeout
                            response = requests.post(
                                ml_api_url, 
                                files=files, 
                                headers=headers,
                                timeout=30  # 30 seconds timeout
                            )
                            
                            # Log response status and headers
                            logger.info(f"ML API Response - Status: {response.status_code}, Headers: {dict(response.headers)}")
                            
                            # For non-200 responses, log the response body for debugging
                            if response.status_code != 200:
                                logger.error(f"ML API Error Response: {response.text}")
                    
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Error calling ML API: {str(e)}", exc_info=True)
                        return Response(
                            {"error": f"Error connecting to resume parsing service: {str(e)}"}, 
                            status=status.HTTP_503_SERVICE_UNAVAILABLE
                        )
                    finally:
                        # Always remove the temporary file
                        try:
                            os.remove(temp_path)
                        except Exception as e:
                            logger.warning(f"Failed to remove temporary file {temp_path}: {str(e)}")
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            if data.get('success', False):
                                # Save the parsed resume data
                                candidate.resume_data = data.get('data', {})
                                logger.info(f"Successfully parsed resume for candidate {candidate.id}")
                                
                                # Save the resume file to media storage
                                resume_url = self._save_file(
                                    resume_file, 
                                    'candidates/resumes', 
                                    request
                                )
                                
                                if resume_url:
                                    # Update the resume URL in the candidate's profile
                                    final_data['resume_url'] = resume_url
                                    candidate.resume_url = resume_url
                                    
                                    # Mark portfolio as completed since we have a resume
                                    candidate.portfolio_completed = True
                                    
                                    logger.info(f"Successfully saved resume file for candidate {candidate.id}")
                                else:
                                    logger.warning("Failed to save resume file to media storage")
                                    return Response(
                                        {"error": "Failed to save resume file"}, 
                                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                                    )
                            else:
                                error_msg = data.get('message', 'Unknown error from ML service')
                                logger.warning(f"Failed to parse resume: {error_msg}")
                                return Response(
                                    {"error": f"Failed to parse resume: {error_msg}"}, 
                                    status=status.HTTP_400_BAD_REQUEST
                                )
                        except ValueError as e:
                            logger.error(f"Invalid JSON response from ML API: {response.text}", exc_info=True)
                            return Response(
                                {"error": "Invalid response from resume parsing service"}, 
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR
                            )
                    else:
                        error_msg = f"Failed to parse resume: HTTP {response.status_code}"
                        if response.status_code == 422:
                            error_msg = "The resume file could not be processed. Please ensure it's a valid PDF or Word document and try again."
                        elif response.status_code >= 500:
                            error_msg = "The resume parsing service is currently unavailable. Please try again later."
                            
                        logger.warning(f"{error_msg} - Response: {response.text}")
                        return Response(
                            {"error": error_msg}, 
                            status=status.HTTP_400_BAD_REQUEST if response.status_code < 500 else status.HTTP_503_SERVICE_UNAVAILABLE
                        )
                        
                except Exception as e:
                    logger.error(f"Error parsing resume: {str(e)}", exc_info=True)
                    return Response(
                        {"error": f"Failed to process resume: {str(e)}"}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                    
            except Exception as e:
                logger.error(f"Error handling resume file: {str(e)}", exc_info=True)
                return Response(
                    {"error": f"Failed to process resume file: {str(e)}"}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except Exception as e:
                exception_logger.exception("Error saving resume")
                logger.error(f"Error saving resume: {str(e)}", exc_info=True)
                return Response(
                    {"error": f"Failed to process resume file: {str(e)}"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Handle video file upload
        if 'video_file' in request.FILES:
            try:
                video_url = self._save_file(
                    request.FILES['video_file'],
                    'candidates/videos',
                    request
                )
                if video_url:
                    # Update the video URL in the candidate model
                    candidate.video_intro_url = video_url
                    candidate.save(update_fields=['video_intro_url', 'updated_at'])
                    data['video_intro_url'] = video_url
            except Exception as e:
                exception_logger.exception("Error saving video")
                logger.error(f"Error saving video: {str(e)}")
                return Response(
                    {"error": "Failed to process video file"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Now handle the data with the serializer
        partial = request.method == 'PATCH'
        
        # Log the data being passed to the serializer for debugging
        logger.info(f"Data being passed to serializer: {final_data}")
        
        # Check which sections are being updated and update completion flags
        if 'full_name' in final_data or 'title' in final_data or 'bio' in final_data or 'location' in final_data:
            candidate.basic_info_completed = True
        
        if 'work_style' in final_data or 'availability_type' in final_data or 'is_available' in final_data:
            candidate.work_preferences_completed = True
            
        if 'skills' in final_data or 'superpowers' in final_data or 'preferred_roles' in final_data:
            candidate.skills_completed = True
            
        if 'portfolio_links' in final_data or 'resume_url' in final_data or 'video_intro_url' in final_data:
            candidate.portfolio_completed = True
            
        if 'profile_visibility' in final_data or 'video_visibility' in final_data or 'contact_visibility' in final_data or 'salary_visibility' in final_data:
            candidate.privacy_completed = True
        
        # Update the candidate instance with the new data
        for key, value in final_data.items():
            if hasattr(candidate, key):
                setattr(candidate, key, value)
        
        # Save the candidate instance
        candidate.save()
        
        # Get the updated data using the serializer
        serializer = self.get_serializer(candidate)
        
        # Skip ML service updates as requested
        ml_success = True
        ml_message = "ML service updates are disabled"
        logger.info("Skipping ML service update as requested")
        
        # Add ML update status to response
        response_data = serializer.data
        
        return Response({
            'success': True,
            'ml_success': ml_success,
            'candidate': response_data
        })
        
        # Initialize response data with updated candidate data
        response_data = serializer.data
        
        # Update ML service
        ml_success = False
        ml_message = 'ML service not called'
        
        try:
            ml_data = self._prepare_ml_data(candidate)
            if ml_data:
                ml_success, ml_message, _ = self._update_ml_candidate_data(candidate.id, ml_data)
        except Exception as e:
            exception_logger.exception("Error updating ML service")
            logger.error(f"Error updating ML service: {str(e)}")
            ml_success = False
            ml_message = f"Error updating ML service: {str(e)}"
        
        # Add ML API status to the response
        if isinstance(response_data, dict):
            response_data['ml_api_status'] = {
                'success': ml_success,
                'message': ml_message
            }
        
        # Clear prefetch cache if it exists
        if getattr(candidate, '_prefetched_objects_cache', None):
            candidate._prefetched_objects_cache = {}
            
        # Handle video file upload and analysis
        video_file = request.FILES.get('video_file')
        if video_file:
            try:
                analyze_url = f"{settings.FLIT_AI_URL}/analyze_intro_video"
                headers = {}
                api_key = getattr(settings, 'ML_API_KEY', None) or os.environ.get('ML_API_KEY')
                if api_key:
                    headers['Authorization'] = f'Bearer {api_key}'
                    
                # Save video file
                video_url = self._save_file(video_file, 'candidates/videos', request)
                if video_url:
                    # Update candidate's video URL
                    candidate.video_intro_url = video_url
                    candidate.save(update_fields=['video_intro_url'])
                    
                    # Prepare video data for analysis
                    video_file.seek(0)
                    video_content = video_file.read()
                    files = {
                        'video_file': (video_file.name, video_content, video_file.content_type)
                    }
                    
                    data_payload = {
                        'user_id': str(getattr(request.user, 'id', '')),
                        'video_url': request.build_absolute_uri(candidate.video_intro_url)
                    }
                    
                    # Send video for analysis
                    try:
                        resp = requests.post(analyze_url, files=files, data=data_payload, headers=headers, timeout=60)
                        if resp and resp.ok:
                            resp_json = resp.json()
                            analysis = resp_json.get('analysis', {})
                            transcription = analysis.get('video_transcript')
                            if transcription:
                                update_fields = ['updated_at', 'video_transcription']
                                candidate.video_transcription = transcription
                                candidate.intro_video_description = analysis.get('description')
                                update_fields.append('intro_video_description')
                                candidate.save(update_fields=update_fields)
                                
                                # Update response with video analysis status
                                if isinstance(response_data, dict):
                                    if 'video_analysis' not in response_data:
                                        response_data['video_analysis'] = {}
                                    response_data['video_analysis'].update({
                                        'status': 'success',
                                        'has_transcription': bool(transcription)
                                    })
                    except Exception as e:
                        exception_logger.exception("Error during video analysis")
                        logger.error(f"Error during video analysis: {str(e)}")
                        if isinstance(response_data, dict):
                            if 'video_analysis' not in response_data:
                                response_data['video_analysis'] = {}
                            response_data['video_analysis'].update({
                                'status': 'error',
                                'message': str(e)
                            })
            except Exception as e:
                exception_logger.exception("Error processing video file")
                logger.error(f"Error processing video file: {str(e)}")
                if isinstance(response_data, dict):
                    if 'video_analysis' not in response_data:
                        response_data['video_analysis'] = {}
                    response_data['video_analysis'].update({
                        'status': 'error',
                        'message': f"Failed to process video: {str(e)}"
                    })
        
        return Response(response_data, status=status.HTTP_200_OK)

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
            ml_service_url = f"{settings.FLIT_AI_URL}/get_candidates_for_job"
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
            exception_logger.exception("Error calling ML service")
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
                    exception_logger.error("Employer.DoesNotExist: Employer not found while fetching companies")
                    companies_qs = Company.objects.none()
        companies_qs = companies_qs.distinct().order_by('-created_at')
        serializer = CompanyWithOpeningsSerializer(companies_qs, many=True, context={'request': request})
        return Response({
            'count': companies_qs.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)

    def _get_clean_url(self, file_field):
        """Helper method to get clean URL from a FileField"""
        if not file_field:
            return None
        
        # Get the storage-relative path
        path = file_field.name
        
        # If using S3Boto3Storage, we need to handle the URL generation differently
        if hasattr(file_field.storage, 'bucket_name'):
            # For S3, use the storage's url method to generate the correct URL
            # This handles all the URL encoding properly
            return file_field.storage.url(path)
        
        # For default storage, use the storage's url method
        return file_field.storage.url(path)

    @action(detail=False, methods=['post'], url_path='upload-resume', permission_classes=[permissions.IsAuthenticated])
    def upload_resume(self, request):
        """
        Handle resume file upload, save to resume_url field, and parse using ML API
        """
        candidate = self._get_candidate_profile(request.user)
        if isinstance(candidate, Response):
            return candidate
            
        # Check if file is present in the request
        if 'resume' not in request.FILES:
            return Response(
                {"error": "No resume file provided"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        resume_file = request.FILES['resume']
        
        try:
            # Save the resume file using our _save_file method
            storage_path = self._save_file(resume_file, 'candidates/resumes', request)
            if not storage_path:
                return Response(
                    {"error": "Failed to save resume file"}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Update the resume_url in the candidate model
            candidate.resume_url = storage_path
            candidate.save(update_fields=['resume_url', 'updated_at'])
            
            # Save the resume file temporarily for ML API processing
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_resumes')
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, resume_file.name)
            
            with open(temp_path, 'wb+') as destination:
                for chunk in resume_file.chunks():
                    destination.write(chunk)
            
            # Call the ML API to parse the resume
            ml_api_url = "https://dev-flit-ai.neurooceans.com/parse_cv"
            
            with open(temp_path, 'rb') as f:
                files = {'file': (resume_file.name, f, resume_file.content_type)}
                response = requests.post(ml_api_url, files=files)
            
            # Remove the temporary file
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {temp_path}: {str(e)}")
            
            if response.status_code != 200:
                logger.error(f"Failed to parse resume. Status: {response.status_code}, Response: {response.text}")
                return Response(
                    {
                        "error": "Failed to parse resume using ML service", 
                        "status_code": response.status_code,
                        "resume_url": self._get_clean_url(candidate.resume_url)
                    }, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            try:
                data = response.json()
                
                # Check if the response has the expected structure
                if not data.get('success', False):
                    error_msg = data.get('message', 'Unknown error from ML service')
                    logger.error(f"ML service returned error: {error_msg}")
                    return Response(
                        {
                            "error": "Failed to parse resume", 
                            "details": error_msg,
                            "resume_url": self._get_clean_url(candidate.resume_url)
                        }, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Update the resume_data field with parsed data
                candidate.resume_data = data.get('data', {})
                
                # Save the updated resume_data
                candidate.save(update_fields=['resume_data', 'updated_at'])
                
                # Get the URL and ensure it's not double-encoded
                resume_url = None
                if candidate.resume_url:
                    # If the URL is already absolute, use it as is
                    if candidate.resume_url.url.startswith(('http://', 'https://')):
                        resume_url = candidate.resume_url.url
                    else:
                        # Otherwise, build the URL manually to prevent double encoding
                        from django.core.files.storage import default_storage
                        resume_url = default_storage.url(candidate.resume_url.name)
                
                return Response({
                    "success": True,
                    "message": "Resume uploaded and parsed successfully",
                    "resume_url": resume_url,
                    "resume_data": candidate.resume_data
                }, status=status.HTTP_200_OK)
                
            except ValueError as e:
                logger.error(f"Failed to parse JSON response from ML service: {str(e)}")
                return Response(
                    {
                        "error": "Invalid response from resume parsing service",
                        "resume_url": self._get_clean_url(candidate.resume_url)
                    }, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Exception as e:
            logger.error(f"Error processing resume: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": f"Failed to process resume: {str(e)}",
                    "resume_url": self._get_clean_url(candidate.resume_url) if hasattr(candidate, 'resume_url') and candidate.resume_url else None
                }, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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
            exception_logger.exception("Error syncing profile_completed flag for candidate")
            pass
        return Response({
            'message': f'{section} section marked as complete',
            'profile_completed': candidate.is_profile_complete
        }, status=status.HTTP_200_OK)

class WorkDNAQuestionView(APIView):
    """
    View to handle work DNA questions and answers
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        For evaluate_answers, only allow candidate access.
        """
        if self.request.method == 'GET' and 'candidate_id' in self.kwargs:
            # For evaluation endpoint, only allow the candidate to access their own evaluation
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]
    
    def get(self, request, candidate_id=None):
        """
        Get work DNA questions for the authenticated candidate
        If no questions exist, fetch them from the ML API
        Response includes questions and any existing answers
        
        If candidate_id is provided in the URL, it's an evaluation request
        """
        try:
            # If candidate_id is provided in URL, handle evaluation
            if candidate_id is not None:
                return self.evaluate_answers(request, candidate_id)
                
            # Otherwise, handle normal questions retrieval
            candidate = request.user.candidate_profile
            
            # Check if questions exist for this candidate
            work_dna_question = WorkDNAQuestion.objects.filter(candidate=candidate).first()
            
            if work_dna_question:
                serializer = WorkDNAQuestionSerializer(work_dna_question)
                return Response(serializer.data)
            
            # If no questions exist, fetch from ML API
            return self.fetch_work_dna_questions(candidate)
            
        except Exception as e:
            exception_logger.exception("Unhandled error in get() while fetching work DNA questions")
            return Response(
                {'error': f'An error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    def post(self, request):
        """
        Submit answers to work DNA questions
        Expected request data format:
        {
            "answers": {
                "1": "answer text for question 1",
                "2": "answer text for question 2"
            }
        }
        """
        try:
            candidate = request.user.candidate_profile
            answers = request.data.get('answers', {})
            
            if not isinstance(answers, dict):
                return Response(
                    {'error': 'Answers must be a dictionary with question IDs as keys'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get work DNA question record
            work_dna_question = WorkDNAQuestion.objects.filter(candidate=candidate).first()
            
            if not work_dna_question:
                return Response(
                    {'error': 'No work DNA questions found. Please fetch questions first.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get the current questions and answers
            current_questions = work_dna_question.questions
            current_answers = work_dna_question.answers or {}
            
            # Update answers with the new ones
            for question_id, answer in answers.items():
                if question_id.isdigit() and int(question_id) <= len(current_questions):
                    # Use the question text as the key in the answers dictionary
                    question_text = current_questions[int(question_id) - 1].get('question', f'Question {question_id}')
                    current_answers[question_text] = answer
                    # Also keep the numeric key for backward compatibility
                    current_answers[question_id] = answer
            
            # Remove any old numeric keys to prevent duplicates
            for key in list(current_answers.keys()):
                if str(key).isdigit():
                    del current_answers[key]
            
            # Save the updated answers
            work_dna_question.answers = current_answers
            work_dna_question.save()
            
            # Return the updated record with questions and answers
            response_data = {
                'id': work_dna_question.id,
                'candidate': work_dna_question.candidate.id,
                'questions': current_questions,
                'answers': current_answers,
                'created_at': work_dna_question.created_at,
                'updated_at': work_dna_question.updated_at
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            exception_logger.exception("Error while saving Work DNA answers")
            return Response(
                {'error': f'An error occurred while saving answers: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def evaluate_answers(self, request, candidate_id):
        """
        Evaluate work DNA answers by calling the ML API
        """
        try:
            # Get the candidate
            try:
                candidate = Candidate.objects.get(id=candidate_id)
            except Candidate.DoesNotExist:
                logger.error(f"Candidate with ID {candidate_id} not found")
                return Response(
                    {'error': 'Candidate not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get the work DNA question record
            work_dna_question = WorkDNAQuestion.objects.filter(candidate=candidate).first()
            
            if not work_dna_question:
                logger.error(f"No work DNA questions found for candidate {candidate_id}")
                return Response(
                    {'error': 'No work DNA questions found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            if not work_dna_question.answers:
                logger.error(f"No answers found for candidate {candidate_id}")
                return Response(
                    {'error': 'No answers found for evaluation'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                # Call the ML API to evaluate the answers
                ml_api_url = f"{settings.FLIT_AI_URL}/evaluate_work_dna_questions/{candidate.id}"
                logger.info(f"Calling ML API: {ml_api_url}")
                
                # Add a timeout to the request
                response = requests.get(ml_api_url, timeout=30)
                response.raise_for_status()  # This will raise an exception for 4XX/5XX responses
                
                evaluation_result = response.json()
                
                # Save the evaluation result
                work_dna_question.evaluation_result = evaluation_result
                work_dna_question.save()
                
                logger.info(f"Successfully evaluated work DNA for candidate {candidate_id}")
                return Response(evaluation_result)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling ML API: {str(e)}")
                return Response(
                    {'error': f'Failed to connect to evaluation service: {str(e)}'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
                
        except requests.RequestException as e:
            exception_logger.exception("Error connecting to ML service for evaluation")
            return Response(
                {'error': f'Error connecting to ML service: {str(e)}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            exception_logger.exception("Error in work DNA evaluation")
            return Response(
                {'error': f'An error occurred during evaluation: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def fetch_work_dna_questions(self, candidate):
        """Fetch work DNA questions from ML API and filter to include only questions 1 and 2"""
        try:
            # Call the ML API to get work DNA questions
            ml_api_url = f"{settings.FLIT_AI_URL}/generate_work_dna_questions/{candidate.id}"
            response = requests.get(ml_api_url)
            
            if response.status_code == 200:
                data = response.json()
                
                # Filter questions to include only questions 1 and 2
                if 'questions' in data and isinstance(data['questions'], list):
                    # Keep only the first two questions
                    filtered_questions = data['questions']
                    # Update the total questions count
                    data['questions'] = filtered_questions
                    data['total_questions'] = len(filtered_questions)
                
                # Create and save work dna questions
                work_dna_question = WorkDNAQuestion.objects.create(
                    candidate=candidate,
                    candidate_name=candidate.full_name,
                    questions=data.get('questions', []),
                    total_questions=data.get('total_questions', 0)
                )
                
                serializer = WorkDNAQuestionSerializer(work_dna_question)
                return Response(serializer.data)
            else:
                return Response(
                    {'error': 'Failed to fetch work DNA questions from ML service'},
                    status=response.status_code
                )
                
        except requests.RequestException as e:
            exception_logger.exception("Error connecting to ML service")
            return Response(
                {'error': f'Error connecting to ML service: {str(e)}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            exception_logger.exception("Unhandled error in ML service handler")
            return Response(
                {'error': f'An error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CandidateAIMatchingView(APIView):
    """
    Proxy endpoint for triggering the external AI matching service.
    Expects `candidate_id` in the URL and optional `total` as a query parameter.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, candidate_id):
        total = request.query_params.get('total')
        ml_api_url = f"{settings.FLIT_AI_URL}/ai_matching/{candidate_id}"

        params = {}
        if total is not None:
            params['total'] = total

        try:
            # Removed timeout to allow the request to wait indefinitely
            response = requests.get(ml_api_url, params=params, timeout=None)

        except requests.RequestException as exc:
            exception_logger.exception("AI matching service request failed")
            logger.exception("AI matching service request failed")
            return Response(
                {'error': 'Unable to reach AI matching service', 'details': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        try:
            payload = response.json()
        except ValueError:
            exception_logger.error("Invalid JSON response while parsing AI matching service payload")
            payload = {'raw_response': response.text or ''}

        if response.status_code >= 400:
            return Response(
                {
                    'error': 'AI matching service returned an error',
                    'details': payload
                },
                status=response.status_code
            )

        return Response(payload, status=status.HTTP_200_OK)


class DiscoverTalentView(generics.ListAPIView):
    """
    API endpoint to discover talent with minimal required fields
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination
    serializer_class = DiscoverTalentSerializer
    
    def get_queryset(self):
        # Get all active candidates
        queryset = Candidate.objects.select_related('user').filter(
            user__is_active=True
        )
        
        # Apply filters if provided in query params
        skills = self.request.query_params.getlist('skills', [])
        if skills:
            queryset = queryset.filter(skills__name__in=skills).distinct()
            
        location = self.request.query_params.get('location')
        if location:
            queryset = queryset.filter(
                Q(current_location__icontains=location) | 
                Q(user__city__icontains=location) |
                Q(user__country__icontains=location)
            )
            
        availability = self.request.query_params.get('availability')
        if availability:
            queryset = queryset.filter(availability=availability)
            
        return queryset


class ReferenceRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Reference request detail view.
    - GET: Public access to view reference request details
    - Other methods (PUT, PATCH, DELETE): Require authentication
    """
    serializer_class = ReferenceRequestSerializer
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
    def get_queryset(self):
        if self.request.method == 'GET':
            return ReferenceRequest.objects.all()
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)
    
class ReferenceRequestListView(generics.ListCreateAPIView):
    """Reference request list and create view."""
    serializer_class = ReferenceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # Disable pagination

    def get_queryset(self):
        return ReferenceRequest.objects.filter(candidate__user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })

    def perform_create(self, serializer):
        candidate = self.request.user.candidate_profile
        serializer.save(candidate=candidate)