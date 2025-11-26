
import json
import logging
import os
import requests
# Set up logging
logger = logging.getLogger(__name__)
from django.conf import settings
from projects.models import Project, ProjectSkill  # Add ProjectSkill import
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
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from accounts.views import BaseRoleRegistrationView
from jobs.models import Job
from .models import ReferenceRequest
from .serializers import CandidateSerializer, CandidateProfileUpdateSerializer
from jobs.serializers import JobListSerializer
from projects.models import Project
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
            raise Http404('Candidate profile not found')


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
            
            # Take the 5 most recent applications
            recent_applications = all_applications[:5]
            
            # Prepare response data
            applications_data = []
            for app in recent_applications:
                app_obj = app['object']
                if app['type'] == 'job':
                    applications_data.append({
                        'id': app_obj.id,
                        'title': app_obj.job.title if hasattr(app_obj, 'job') and app_obj.job else 'Unknown Job',
                        'company': app_obj.job.company.name if hasattr(app_obj, 'job') and hasattr(app_obj.job, 'company') and app_obj.job.company else 'Unknown Company',
                        'status': app_obj.status,
                        'applied_at': app_obj.applied_at,
                        'type': 'job'
                    })
                else:  # project application
                    applications_data.append({
                        'id': app_obj.id,
                        'title': app_obj.project.title if hasattr(app_obj, 'project') and app_obj.project else 'Unknown Project',
                        'company': app_obj.project.company.name if hasattr(app_obj, 'project') and hasattr(app_obj.project, 'company') and app_obj.project.company else 'Unknown Company',
                        'status': app_obj.status,
                        'applied_at': app_obj.applied_at,
                        'type': 'project'
                    })
            
            return Response({
                'recent_applications': applications_data,
                'total_applications': len(job_applications) + len(project_applications),
                'job_applications_count': len(job_applications),
                'project_applications_count': len(project_applications)
            })
            
        except Exception as e:
            logger.error(f"Error fetching applications: {str(e)}", exc_info=True)
            return Response(
                {'error': 'An error occurred while fetching applications'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        


class CandidateLatestJobsView(DashboardBaseView):
    """Endpoint for latest jobs relevant to candidate."""
    def get(self, request):
        candidate = self.get_candidate_profile(request.user)
        logger = logging.getLogger(__name__)
        
        # Try to get personalized jobs from ML endpoint
        ml_success = False
        latest_jobs = []
        try:
            ml_url = f"https://dev-flit-ai.neurooceans.com/show_jobs_for_candidate/{candidate.id}"
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
                                job_id = job_data.get('job_id')
                                if not job_id:
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
                            
                            except Exception as e:
                                logger.error(f"Error processing job from ML data: {str(e)}", exc_info=True)
                        
                        if latest_jobs:
                            ml_success = True
                            logger.info(f"Successfully got {len(latest_jobs)} jobs from ML service")
                        else:
                            logger.warning("No valid jobs processed from ML response")
                    else:
                        logger.warning("No ranked_opportunities found or empty in ML response")
                except ValueError as e:
                    logger.error(f"Invalid JSON in ML response: {str(e)}")
            else:
                logger.warning(f"ML service returned status code: {ml_response.status_code}")
                logger.warning(f"Response content: {ml_response.text}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling ML service: {str(e)}", exc_info=True)
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
        
        # If we have Job objects (from fallback), serialize them
        if latest_jobs and isinstance(latest_jobs[0], Job):
            job_serializer = JobListSerializer(latest_jobs, many=True, context={'request': request})
            return Response({
                'latest_jobs': job_serializer.data
            })
        # If we have dictionaries (from ML API), return them directly
        elif latest_jobs and isinstance(latest_jobs[0], dict):
            return Response({
                'latest_jobs': latest_jobs
            })
        # Fallback to empty list if no jobs found
        return Response({
            'latest_jobs': []
        })

class CandidateLatestProjectsView(DashboardBaseView):
    """Endpoint for latest projects relevant to candidate."""
    def get(self, request):
        candidate = self.get_candidate_profile(request.user)
        logger = logging.getLogger(__name__)
        
        # Try to get personalized projects from ML endpoint
        ml_success = False
        latest_projects = []
        ml_data = None
        
        try:
            ml_url = f"https://dev-flit-ai.neurooceans.com/show_projects_for_candidate/{candidate.id}"
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
                        logger.error(f"ML service timed out after {max_retries + 1} attempts")
                        raise
                    logger.warning(f"ML service timed out, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries:
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
                                logger.warning(f"Invalid project ID in ML response: {project_data.get('project_id') or project_data.get('id')}")
                    
                    # If no project IDs found in opportunities, try the root level ranked_opportunity_ids
                    if not project_ids and 'ranked_opportunity_ids' in ml_data and isinstance(ml_data['ranked_opportunity_ids'], list):
                        logger.info(f"Found {len(ml_data['ranked_opportunity_ids'])} project IDs in ranked_opportunity_ids")
                        for project_id in ml_data['ranked_opportunity_ids']:
                            try:
                                project_id = int(project_id)
                                project_ids.append(project_id)
                            except (ValueError, TypeError):
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
                                logger.error(f"Error processing project {project_id}: {str(e)}", exc_info=True)
                    
                    # If we still don't have projects, try to get them from the database as fallback
                    if not latest_projects:
                        logger.info("No projects from ML response, falling back to database")
                        latest_projects = list(Project.objects.filter(status='active')
                                           .select_related('company')
                                           .prefetch_related('required_skills')
                                           .order_by('-created_at')[:10])
                    if latest_projects:
                        ml_success = True
                        logger.info(f"Successfully got {len(latest_projects)} projects from ML service")
                    else:
                        logger.warning("No projects found in ML response")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse ML service response as JSON: {e}")
                    logger.info(f"Raw response content: {ml_response.text[:500]}...")  # Log first 500 chars of response
                except Exception as e:
                    logger.error(f"Unexpected error processing ML response: {str(e)}", exc_info=True)
            else:
                logger.warning(f"ML service returned status code: {ml_response.status_code}")
                logger.warning(f"Response content: {ml_response.text[:500]}...")  # Log first 500 chars of response
                
        except requests.RequestException as e:
            error_msg = f"Request to ML service failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f"\nResponse status: {e.response.status_code}"
                try:
                    error_msg += f"\nResponse content: {e.response.text[:500]}"
                except:
                    pass
            logger.error(error_msg, exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error calling ML service: {str(e)}", exc_info=True)
        
        # Fallback to original logic if ML fails or no results
        if not ml_success or not latest_projects:
            logger.info("Falling back to default project list")
            # Get latest active projects, ordered by creation date
            latest_projects = list(Project.objects.filter(status='active')
                                        .select_related('company')
                                        .prefetch_related('required_skills')
                                        .order_by('-created_at')[:10])
        
        # Prepare the response data
        response_data = []
        
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
        
        return Response({
            'latest_projects': response_data,
            'ml_success': ml_success
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
        # Support viewing by either candidate PK or user ID on the same endpoint.
        candidate = None
        viewed_publicly = False
        # 1) Try by USER ID with public visibility first (to prefer user.id semantics)
        try:
            candidate = Candidate.objects.get(user__id=pk, profile_visibility="public")
            viewed_publicly = True
        except Candidate.DoesNotExist:
            candidate = None
        # 2) If not found, try by candidate PK with public visibility
        if candidate is None:
            try:
                candidate = Candidate.objects.get(pk=pk, profile_visibility="public")
                viewed_publicly = True
            except Candidate.DoesNotExist:
                candidate = None
        # 3) If still not found, allow owner to view their own profile regardless of visibility (by either key)
        if candidate is None and getattr(request.user, 'is_authenticated', False):
            try:
                candidate = Candidate.objects.get(Q(pk=pk) | Q(user__id=pk), user=request.user)
                viewed_publicly = False
            except Candidate.DoesNotExist:
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
                ml_error = f'Candidate with ID {candidate_id} not found for ML sync'
                logger.error(ml_error)

        if candidate:
            ml_api_url = f"https://dev-flit-ai.neurooceans.com/create_candidates/{candidate.id}"
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
            }

            max_retries = 2
            timeout_seconds = 30
            ml_response = None

            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Calling Candidate create ML API (attempt {attempt + 1}/{max_retries + 1}) for candidate {candidate.id}")
                    ml_response = requests.post(
                        ml_api_url,
                        json=ml_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=timeout_seconds
                    )
                    break
                except requests.exceptions.Timeout:
                    if attempt == max_retries:
                        ml_error = "Candidate create ML API timed out after retries"
                        logger.error(ml_error)
                        break
                    logger.warning(f"Candidate create ML API timeout (attempt {attempt + 1}), retrying...")
                    time.sleep(1)
                except requests.exceptions.RequestException as exc:
                    ml_error = f"Candidate create ML API request failed: {str(exc)}"
                    logger.error(ml_error, exc_info=True)
                    break

            if ml_response is not None:
                if ml_response.status_code in (200, 201):
                    try:
                        ml_data = ml_response.json()
                        candidate_profile_summary = ml_data.get('candidate_profile_summary')
                        candidate_tags = ml_data.get('candidate_tags', [])

                        updates = {}
                        if candidate_profile_summary is not None:
                            updates['candidate_profile_summary'] = candidate_profile_summary
                        if candidate_tags:
                            updates['candidate_tags'] = candidate_tags

                        if updates:
                            for field, value in updates.items():
                                setattr(candidate, field, value)
                            candidate.save(update_fields=list(updates.keys()))

                        ml_success = True
                    except ValueError:
                        ml_error = "Invalid JSON response from Candidate create ML API"
                        logger.error(ml_error)
                    except Exception as exc:
                        ml_error = f"Error processing Candidate create ML API response: {str(exc)}"
                        logger.error(ml_error, exc_info=True)
                else:
                    ml_error = f"Candidate create ML API returned status code {ml_response.status_code}"
                    logger.error(f"{ml_error}. Response content: {ml_response.text}")

        response.data = {
            'message': 'Candidate created successfully',
            'ml_success': ml_success,
            'candidate_profile_summary': candidate_profile_summary,
            'candidate_tags': candidate_tags,
            'data': response.data
        }

        if ml_error:
            response.data['ml_error'] = ml_error

        return response

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

    def _update_ml_candidate_data(self, candidate_id, data):
        """
        Update candidate data in the ML service
        Returns:
            tuple: (success: bool, message: str, data: dict)
        """
        try:
            # Use the create_candidates endpoint for both create and update operations
            ml_api_url = f"https://dev-flit-ai.neurooceans.com/create_candidates/{candidate_id}"
            logger.info(f"Sending data to ML API: {ml_api_url}")
            logger.debug(f"Data being sent: {data}")
            
            # Prepare headers without API key
            headers = {
                'Content-Type': 'application/json'
            }
            
            try:
                # Always use POST for the create_candidates endpoint
                response = requests.post(
                    ml_api_url,
                    json=data,
                    headers=headers,
                    timeout=30  # 30 seconds timeout
                )
                
                # Log the raw response for debugging
                logger.debug(f"ML API response status: {response.status_code}")
                logger.debug(f"ML API response content: {response.text}")
                
                response.raise_for_status()
                
                try:
                    response_data = response.json()
                    # Consider it successful if we get a 200 status and valid JSON with candidate data
                    if response.status_code == 200 and 'id' in response_data:
                        logger.info(f"ML API update successful for candidate {candidate_id}")
                        return True, "Profile Updated successfully in ML service", response_data
                    else:
                        error_msg = response_data.get('message', 
                            f"Status: {response.status_code}, Response: {response.text}")
                        logger.error(f"ML API error for candidate {candidate_id}: {error_msg}")
                        logger.debug(f"Full response headers: {dict(response.headers)}")
                        return False, f"ML service error: {error_msg}", response_data
                        
                except json.JSONDecodeError:
                    # If response is not JSON, but status is 200, consider it a success
                    if response.status_code == 200:
                        logger.info(f"ML API update successful (non-JSON response) for candidate {candidate_id}")
                        return True, "Profile updated successfully in ML service", {}
                    raise  # Re-raise if not 200
                
            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP Error: {str(e)}"
                logger.error(f"{error_msg} for candidate {candidate_id}")
                return False, error_msg, None
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Error connecting to ML service: {str(e)}"
            logger.error(f"{error_msg} for candidate {candidate_id}")
            return False, error_msg, None
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response from ML service: {str(e)}"
            logger.error(f"{error_msg} for candidate {candidate_id}")
            return False, error_msg, None
            
        except Exception as e:
            error_msg = f"Unexpected error updating ML service: {str(e)}"
            logger.error(f"{error_msg} for candidate {candidate_id}", exc_info=True)
            return False, error_msg, None
            
    def _parse_form_data(self, data):
        """Helper method to parse form data"""
        if not data:
            return data
            
        if isinstance(data, dict):
            # Handle list fields
            for key in ['skills', 'languages', 'preferred_locations']:
                if key in data:
                    data[key] = self._parse_json_list(data.get(key))
            
            # Handle boolean fields
            for key in ['is_remote', 'is_available']:
                if key in data:
                    data[key] = self._parse_bool(data.get(key))
            
            # Handle numeric fields
            for key in ['min_salary', 'max_salary']:
                if key in data and data.get(key) not in [None, '']:
                    parsed = self._parse_int(data.get(key))
                    if parsed is not None:
                        data[key] = parsed
        
        return data
        
    def _parse_json_list(self, value):
        """Parse a JSON list from string if needed"""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
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
            return None
            
    def _prepare_ml_data(self, candidate):
        """Prepare candidate data for ML API update"""
        if not candidate or not hasattr(candidate, 'user'):
            return None
            
        return {
            'first_name': candidate.user.first_name or '',
            'last_name': candidate.user.last_name or '',
            'email': getattr(candidate.user, 'email', ''),
            'profile_data': {
                'headline': getattr(candidate, 'headline', '') or '',
                'summary': getattr(candidate, 'summary', '') or '',
                'skills': [skill.name for skill in getattr(candidate, 'skills', []) if hasattr(skill, 'name')],
                'resume_url': getattr(candidate, 'resume_url', '') or '',
                'profile_picture': candidate.profile_picture.url if hasattr(candidate, 'profile_picture') and candidate.profile_picture else '',
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
            
        # Handle PUT/PATCH requests
        partial = request.method == 'PATCH'
        serializer = self.get_serializer(candidate, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Handle file uploads
        if 'profile_picture' in request.FILES:
            serializer.validated_data['profile_picture'] = request.FILES['profile_picture']
            
        if 'resume_file' in request.FILES:
            resume_url = self._save_file(request.FILES['resume_file'], 'candidates/resumes', request)
            if resume_url:
                serializer.validated_data['resume_url'] = resume_url
        
        # Save the updated profile
        self.perform_update(serializer)
        
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
                analyze_url = 'https://dev-flit-ai.neurooceans.com/analyze_intro_video'
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
                        logger.error(f"Error during video analysis: {str(e)}")
                        if isinstance(response_data, dict):
                            if 'video_analysis' not in response_data:
                                response_data['video_analysis'] = {}
                            response_data['video_analysis'].update({
                                'status': 'error',
                                'message': str(e)
                            })
            except Exception as e:
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
            ml_service_url = 'https://dev-flit-ai.neurooceans.com/get_candidates_for_job'
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

class WorkDNAQuestionView(APIView):
    """
    View to handle work DNA questions and answers
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get work DNA questions for the authenticated candidate
        If no questions exist, fetch them from the ML API
        Response includes questions and any existing answers
        """
        try:
            candidate = request.user.candidate_profile
            
            # Check if questions exist for this candidate
            work_dna_question = WorkDNAQuestion.objects.filter(candidate=candidate).first()
            
            if work_dna_question:
                serializer = WorkDNAQuestionSerializer(work_dna_question)
                return Response(serializer.data)
            
            # If no questions exist, fetch from ML API
            return self.fetch_work_dna_questions(candidate)
            
        except Exception as e:
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
            return Response(
                {'error': f'An error occurred while saving answers: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def fetch_work_dna_questions(self, candidate):
        """Fetch work DNA questions from ML API and filter to include only questions 1 and 2"""
        try:
            # Call the ML API to get work DNA questions
            ml_api_url = f"https://dev-flit-ai.neurooceans.com/generate_work_dna_questions/{candidate.id}"
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
            return Response(
                {'error': f'Error connecting to ML service: {str(e)}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
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
        ml_api_url = f"https://dev-flit-ai.neurooceans.com/ai_matching/{candidate_id}"

        params = {}
        if total is not None:
            params['total'] = total

        try:
            # Removed timeout to allow the request to wait indefinitely
            response = requests.get(ml_api_url, params=params, timeout=None)

        except requests.RequestException as exc:
            logger.exception("AI matching service request failed")
            return Response(
                {'error': 'Unable to reach AI matching service', 'details': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        try:
            payload = response.json()
        except ValueError:
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