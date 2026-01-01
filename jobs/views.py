import logging
from rest_framework import viewsets, status, permissions, mixins, authentication
from rest_framework.decorators import action, authentication_classes, permission_classes, api_view
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import JSONParser
from django.shortcuts import get_object_or_404
from .models import Job, JobSkill, JobLanguage
from .serializers import (
    JobSerializer, JobListSerializer, JobCreateSerializer, JobUpdateSerializer,
    JobSkillSerializer, JobLanguageSerializer
)
from companies.models import Company
from accounts.permissions import IsEmployer
import requests
import time
from django.conf import settings
from django.db import models
import os
from utils.pagination import CustomPagination

logger = logging.getLogger(__name__)
exception_logger = logging.getLogger("exceptions")
        



class PublicAuthentication(authentication.BaseAuthentication):
    """
    Authentication class that allows any request (public access).
    """
    def authenticate(self, request):
        return None  

@authentication_classes([]) 
@permission_classes([permissions.AllowAny])  # Anyone can access
class PublicJobViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      GenericViewSet):
    """
    Public API: Anyone can see active jobs
    """
    queryset = Job.objects.all()
    serializer_class = JobListSerializer
    pagination_class = CustomPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        # If search parameter exists and no results found, return 404
        search_query = request.query_params.get('search', None)
        if search_query and not page:
            return Response(
                {"detail": "No jobs found matching the search criteria."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Return only active jobs and apply any additional filtering
        """
        queryset = super().get_queryset()
        
        # Apply any additional filtering from query parameters
        work_style = self.request.query_params.get('workStyle')
        if work_style:
            queryset = queryset.filter(workStyle=work_style)
            
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
            
        experience_level = self.request.query_params.get('experienceLevel')
        if experience_level:
            queryset = queryset.filter(experienceLevel=experience_level)
            
        employment_type = self.request.query_params.get('employmentType')
        if employment_type:
            queryset = queryset.filter(employmentType=employment_type)
            
        company_id = self.request.query_params.get('company')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
            
        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                models.Q(title__icontains=search_query)
            )
            
        return queryset.distinct()


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['workStyle', 'category', 'experienceLevel', 'employmentType', 'company']
    search_fields = ['title', 'description', 'company__company_name']
    ordering_fields = ['created_at', 'salaryRangeMin', 'salaryRangeMax']
    ordering = ['-created_at']
    pagination_class = CustomPagination

    def get_queryset(self):
        """
        Filter jobs based on the current user and request context.
        For employer users, only show jobs from their company by default.
        """
        queryset = super().get_queryset()
        
        # For list action, only show active jobs
        if self.action == 'list':
            queryset = queryset.filter(status='active')
            
        # For employer users, filter by their company
        if hasattr(self.request.user, 'employer_profile'):
            queryset = queryset.filter(company=self.request.user.employer_profile.company)
        
        # For owner-scoped actions, filter by the employer
        owner_scoped_actions = {
            'update', 'partial_update', 'destroy',
            'skills', 'languages', 'applications', 'update_status',
            'shortlist_application', 'reject_application'
        }
        if getattr(self, 'action', None) in owner_scoped_actions:
            queryset = queryset.filter(employer=self.request.user)
            
        # Allow explicit company filtering via query params
        company_id = self.request.query_params.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
            
        return queryset
        
    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve a job instance with proper request context.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_jobs(self, request):
        """
        Get jobs posted by the current user's company.
        """
        # Get the company ID from query params if provided
        company_id = request.query_params.get('company_id')
        
        if company_id:
            # If company_id is provided, verify the user has access to this company
            from companies.models import Company
            try:
                company = Company.objects.get(id=company_id)
                if not (request.user.is_staff or company.employers.filter(user=request.user).exists()):
                    return Response(
                        {'error': 'You do not have permission to view jobs for this company'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                queryset = self.filter_queryset(Job.objects.filter(company_id=company_id))
            except Company.DoesNotExist:
                exception_logger.error(f"Company.DoesNotExist: Company not found for ID {company_id}")
                return Response(
                    {'error': 'Company not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # If no company_id provided, get all companies the user has access to
          
            user_companies = Company.objects.filter(employers__user=request.user)
            if not user_companies.exists():
                return Response([], status=status.HTTP_200_OK)
                
            queryset = self.filter_queryset(Job.objects.filter(company__in=user_companies))
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = JobListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
            
        serializer = JobListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        if self.action == 'create':
            return JobCreateSerializer
        if self.action in ['update', 'partial_update']:
            return JobUpdateSerializer
        return JobSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'update_status', 'shortlist_application', 'reject_application', 'skills', 'languages']:
            return [permissions.IsAuthenticated(), IsEmployer()]
        return [permissions.IsAuthenticated()]
        
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code != status.HTTP_201_CREATED:
            return response

        ml_success = False
        job_profile_summary = None
        job_tags = []
        ml_error = None

        job_id = response.data.get('id')
        job = None

        if not job_id:
            ml_error = 'Job ID missing in response; cannot trigger ML sync'
            logger.error(ml_error)
        else:
            try:
                job = Job.objects.get(id=job_id)
            except Job.DoesNotExist:
                exception_logger.error(f"Job.DoesNotExist: Job with ID {job_id} not found for ML sync")
                ml_error = f'Job with ID {job_id} not found for ML sync'
                logger.error(ml_error)

        if job:
            ml_api_url = f"{settings.FLIT_AI_URL}/create_jobs/{job.id}"
            ml_payload = {
                "title": job.title,
                "description": job.description,
                "company_name": job.company.company_name if hasattr(job, 'company') and job.company else "",
                "employment_type": job.employmentType,
                "experience_level": job.experienceLevel,
                "work_style": job.workStyle,
                "category": job.category,
                "salary_range_min": job.salaryRangeMin,
                "salary_range_max": job.salaryRangeMax,
                "benefits": job.benefits or [],
                "application_deadline": job.applicationDeadline.isoformat() if job.applicationDeadline else None,
                "status": job.status,
                "location": job.location,
                "skills": job.skills or [],
            }

            max_retries = 2
            timeout_seconds = 30
            ml_response = None

            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Calling Job create ML API (attempt {attempt + 1}/{max_retries + 1}) for job {job.id}")
                    ml_response = requests.post(
                        ml_api_url,
                        json=ml_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=timeout_seconds
                    )
                    break
                except requests.exceptions.Timeout:
                    if attempt == max_retries:
                        exception_logger.error("Job create ML API timed out after retries")
                        ml_error = "Job create ML API timed out after retries"
                        logger.error(ml_error)
                        break
                    logger.warning(f"Job create ML API timeout (attempt {attempt + 1}), retrying...")
                    time.sleep(1)
                except requests.exceptions.RequestException as exc:
                    exception_logger.exception("Job create ML API request failed")
                    ml_error = f"Job create ML API request failed: {str(exc)}"
                    logger.error(ml_error, exc_info=True)
                    break

            if ml_response is not None:
                if ml_response.status_code in (200, 201):
                    try:
                        ml_data = ml_response.json()
                        job_profile_summary = ml_data.get('job_profile_summary')
                        job_tags = ml_data.get('job_tags', [])

                        updates = {}
                        if job_profile_summary is not None:
                            updates['job_profile_summary'] = job_profile_summary
                        if job_tags:
                            updates['job_tags'] = job_tags

                        if updates:
                            for field, value in updates.items():
                                setattr(job, field, value)
                            job.save(update_fields=list(updates.keys()))

                        ml_success = True
                    except ValueError:
                        exception_logger.error("Invalid JSON response from Job create ML API")
                        ml_error = "Invalid JSON response from Job create ML API"
                        logger.error(ml_error)
                    except Exception as exc:
                        exception_logger.exception("Error processing Job create ML API response")
                        ml_error = f"Error processing Job create ML API response: {str(exc)}"
                        logger.error(ml_error, exc_info=True)
                else:
                    ml_error = f"Job create ML API returned status code {ml_response.status_code}"
                    logger.error(f"{ml_error}. Response content: {ml_response.text}")

        response.data = {
            'message': 'Job created successfully',
            'ml_success': ml_success,
            'job_profile_summary': job_profile_summary,
            'job_tags': job_tags,
            'data': response.data
        }

        if ml_error:
            response.data['ml_error'] = ml_error

        return response
        
    def update(self, request, *args, **kwargs):
   
        # First, perform the normal update
        response = super().update(request, *args, **kwargs)
        
        if response.status_code == status.HTTP_200_OK:
            try:
                job = self.get_object()
                
                # Prepare data for ML API
                ml_api_url = f"{settings.FLIT_AI_URL}/update_job_data/{job.id}"
                ml_payload = {
                    "title": job.title,
                    "description": job.description,
                    "company_name": job.company.company_name if hasattr(job, 'company') else "",
                    "employment_type": job.employmentType,
                    "experience_level": job.experienceLevel,
                    "work_style": job.workStyle,
                    "category": job.category,
                    "salary_range_min": job.salaryRangeMin,
                    "salary_range_max": job.salaryRangeMax,
                    "benefits": job.benefits or [],
                    "application_deadline": job.applicationDeadline.isoformat() if job.applicationDeadline else None,
                    "status": job.status
                }
                
                # Call ML API with retry logic
                max_retries = 2
                timeout_seconds = 30  # Increased from 10 to 30 seconds
                
                for attempt in range(max_retries + 1):
                    try:
                        print(f"Calling ML API (attempt {attempt + 1}/{max_retries + 1})...")
                        ml_response = requests.patch(
                            ml_api_url,
                            json=ml_payload,
                            headers={"Content-Type": "application/json"},
                            timeout=timeout_seconds
                        )
                        break  # If successful, exit the retry loop
                    except requests.exceptions.Timeout:
                        if attempt == max_retries:
                            exception_logger.error("ML API timed out after retries")
                            raise  # Re-raise the timeout if we've exhausted all retries
                        exception_logger.error(f"ML API timeout (attempt {attempt + 1}), retrying...")
                        print(f"ML API timeout (attempt {attempt + 1}), retrying...")
                        time.sleep(1)  # Wait 1 second before retry
                    except requests.exceptions.RequestException as e:
                        # For other request exceptions, log and re-raise
                        exception_logger.exception("ML API request failed")
                        print(f"ML API request failed: {str(e)}")
                        raise
                
                if ml_response.status_code == 200:
                    try:
                        ml_data = ml_response.json()
                        # Update job with ML-enhanced data
                        if 'job_profile_summary' in ml_data:
                            job.job_profile_summary = ml_data['job_profile_summary']
                        if 'job_tags' in ml_data:
                            job.job_tags = ml_data['job_tags']
                        job.save()
                        
                        # Create response data in the exact format we want
                        response_data = {
                            'message': 'Job updated successfully',
                            'ml_success': True,  # ML API call was successful
                            'job_profile_summary': ml_data.get('job_profile_summary', ''),
                            'job_tags': ml_data.get('job_tags', []),
                            'data': {
                                'title': job.title,
                                'description': job.description,
                                'job_tags': ml_data.get('job_tags', []),
                                'location': job.location,
                                'workStyle': job.workStyle,
                                'category': job.category,
                                'experienceLevel': job.experienceLevel,
                                'employmentType': job.employmentType,
                                'hasTemporaryOption': job.hasTemporaryOption,
                                'temporaryDuration': job.temporaryDuration,
                                'salaryRangeMin': job.salaryRangeMin,
                                'salaryRangeMax': job.salaryRangeMax,
                                'benefits': job.benefits or [],
                                'applicationDeadline': job.applicationDeadline.isoformat() if job.applicationDeadline else None,
                                'start_date': job.start_date.isoformat() if job.start_date else None,
                                'status': job.status,
                                'company_name': job.company.company_name if hasattr(job, 'company') and job.company else None
                            }
                        }
                        
                        # Update the response with the formatted data
                        response.data = response_data
                    except Exception as e:
                        exception_logger.exception("Error processing ML API response")
                        print(f"Error processing ML API response: {str(e)}")
                        print(f"Response content: {ml_response.text}")
                        # Return the original response data with success message
                        response.data = {
                            'message': 'Job updated successfully (ML processing failed - invalid response format)',
                            'ml_success': False,  # ML API call failed
                            'job_profile_summary': None,
                            'job_tags': [],
                            'data': {
                                'title': job.title,
                                'description': job.description,
                                'job_tags': [],
                                'location': job.location,
                                'workStyle': job.workStyle,
                                'category': job.category,
                                'experienceLevel': job.experienceLevel,
                                'employmentType': job.employmentType,
                                'hasTemporaryOption': job.hasTemporaryOption,
                                'temporaryDuration': job.temporaryDuration,
                                'salaryRangeMin': job.salaryRangeMin,
                                'salaryRangeMax': job.salaryRangeMax,
                                'benefits': job.benefits or [],
                                'applicationDeadline': job.applicationDeadline.isoformat() if job.applicationDeadline else None,
                                'start_date': job.start_date.isoformat() if job.start_date else None,
                                'status': job.status,
                                'company_name': job.company.company_name if hasattr(job, 'company') and job.company else None
                            }
                        }
                else:
                    # If ML API fails, still return success but log the error
                    error_msg = f"ML API returned status code {ml_response.status_code}"
                    print(error_msg)
                    print(f"Response content: {ml_response.text}")
                    response.data = {
                        'message': f'Job updated successfully (ML processing failed - {error_msg})',
                        'ml_success': False,  # ML API call failed
                        'job_profile_summary': None,
                        'job_tags': [],
                        'data': {
                            'title': job.title,
                            'description': job.description,
                            'job_tags': [],
                            'location': job.location,
                            'workStyle': job.workStyle,
                            'category': job.category,
                            'experienceLevel': job.experienceLevel,
                            'employmentType': job.employmentType,
                            'hasTemporaryOption': job.hasTemporaryOption,
                            'temporaryDuration': job.temporaryDuration,
                            'salaryRangeMin': job.salaryRangeMin,
                            'salaryRangeMax': job.salaryRangeMax,
                            'benefits': job.benefits or [],
                            'applicationDeadline': job.applicationDeadline.isoformat() if job.applicationDeadline else None,
                            'start_date': job.start_date.isoformat() if job.start_date else None,
                            'status': job.status,
                            'company_name': job.company.company_name if hasattr(job, 'company') and job.company else None
                        }
                    }
                    
            except Exception as e:
                # If any error occurs with ML API, still return success but log the error
                exception_logger.exception("Error calling ML API")
                error_msg = f"Error calling ML API: {str(e)}"
                print(error_msg)
                if 'ml_response' in locals():
                    exception_logger.error(f"Response status: {getattr(ml_response, 'status_code', 'N/A')}")
                    print(f"Response status: {getattr(ml_response, 'status_code', 'N/A')}")
                    print(f"Response content: {getattr(ml_response, 'text', 'N/A')}")
                
                # Get the latest job data
                job = self.get_object()
                response.data = {
                    'message': f'Job updated successfully (ML processing failed - {str(e)})',
                    'ml_success': False,  # ML API call failed
                    'job_profile_summary': None,
                    'job_tags': [],
                    'data': {
                        'title': job.title,
                        'description': job.description,
                        'job_tags': [],
                        'location': job.location,
                        'workStyle': job.workStyle,
                        'category': job.category,
                        'experienceLevel': job.experienceLevel,
                        'employmentType': job.employmentType,
                        'hasTemporaryOption': job.hasTemporaryOption,
                        'temporaryDuration': job.temporaryDuration,
                        'salaryRangeMin': job.salaryRangeMin,
                        'salaryRangeMax': job.salaryRangeMax,
                        'benefits': job.benefits or [],
                        'applicationDeadline': job.applicationDeadline.isoformat() if job.applicationDeadline else None,
                        'start_date': job.start_date.isoformat() if job.start_date else None,
                        'status': job.status,
                        'company_name': job.company.company_name if hasattr(job, 'company') and job.company else None
                    }
                }
        
        return response
        
    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        self.perform_destroy(job)
        return Response(
            {'message': 'Job deleted successfully'}, 
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_path='my-jobs')
    def my_jobs(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(employer=request.user)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = JobListSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)
        serializer = JobListSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'results': serializer.data
        })

    @action(detail=True, methods=['get', 'post'], url_path='skills')
    def skills(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            skills = JobSkill.objects.filter(job=job)
            serializer = JobSkillSerializer(skills, many=True)
            return Response(serializer.data)
        serializer = JobSkillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], url_path='languages')
    def languages(self, request, pk=None):
        job = self.get_object()
        if request.method == 'GET':
            langs = JobLanguage.objects.filter(job=job)
            serializer = JobLanguageSerializer(langs, many=True)
            return Response(serializer.data)
        serializer = JobLanguageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='applications')
    def applications(self, request, pk=None):
        try:
            job = Job.objects.get(id=pk, employer=request.user)
        except Job.DoesNotExist:
            exception_logger.error("Job.DoesNotExist: Job not found")
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        applications = job.applications.all()
        data = {
            'job': JobSerializer(job).data,
            'applications': [
                {
                    'id': app.id,
                    'candidate_name': app.candidate.full_name,
                    'status': app.status,
                    'overall_match_score': app.overall_match_score,
                    'applied_at': app.applied_at,
                    'is_shortlisted': app.is_shortlisted,
                    'is_rejected': app.is_rejected
                }
                for app in applications
            ],
            'total_applications': applications.count(),
            'shortlisted_count': applications.filter(is_shortlisted=True).count(),
            'rejected_count': applications.filter(is_rejected=True).count(),
        }
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='status')
    def update_status(self, request, pk=None):
        try:
            job = Job.objects.get(id=pk, employer=request.user)
        except Job.DoesNotExist:
            exception_logger.error("Job.DoesNotExist: Job not found")
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        new_status = request.data.get('status')
        if new_status not in ['draft', 'active', 'paused', 'closed', 'filled']:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        job.status = new_status
        job.save()
        return Response({'message': 'Job status updated successfully', 'job': JobSerializer(job).data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/shortlist')
    def shortlist_application(self, request, pk=None, application_id=None):
        try:
            job = Job.objects.get(id=pk, employer=request.user)
            application = job.applications.get(id=application_id)
        except Job.DoesNotExist:
            exception_logger.error("Job.DoesNotExist: Job not found")
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            exception_logger.exception("Application not found")
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
        application.is_shortlisted = True
        application.is_rejected = False
        application.status = 'shortlisted'
        application.save()
        return Response({'message': 'Application shortlisted successfully', 'application': {'id': application.id, 'candidate_name': application.candidate.full_name, 'status': application.status, 'is_shortlisted': application.is_shortlisted}}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/reject')
    def reject_application(self, request, pk=None, application_id=None):
        try:
            # Ensure request.data is not None
            if request.data is None:
                return Response({'error': 'Request data is required'}, status=status.HTTP_400_BAD_REQUEST)
                
            job = Job.objects.get(id=pk, employer=request.user)
            application = job.applications.get(id=application_id)
            
            # Update application status
            application.is_rejected = True
            application.is_shortlisted = False
            application.status = 'rejected'
            
            # Safely get rejection_reason with proper error handling
            rejection_reason = ''
            try:
                rejection_reason = request.data.get('rejection_reason', '')
            except AttributeError:
                # In case request.data is not a dictionary-like object
                rejection_reason = ''
                
            application.rejection_reason = rejection_reason
            application.save()
            
            return Response({
                'message': 'Application rejected successfully', 
                'application': {
                    'id': application.id, 
                    'candidate_name': application.candidate.full_name, 
                    'status': application.status, 
                    'is_rejected': application.is_rejected,
                    'rejection_reason': application.rejection_reason
                }
            }, status=status.HTTP_200_OK)
            
        except Job.DoesNotExist:
            exception_logger.error(f"Job.DoesNotExist: Job {pk} not found for user {request.user.id}")
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
            
        except JobApplication.DoesNotExist:
            exception_logger.error(f"Application.DoesNotExist: Application {application_id} not found for job {pk}")
            return Response({'error': 'Application not found'}, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            exception_logger.exception(f"Error rejecting application {application_id}: {str(e)}")
            return Response(
                {'error': 'An error occurred while processing your request'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )