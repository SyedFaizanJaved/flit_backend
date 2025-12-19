from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes, api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from utils.pagination import CustomPagination
from django.contrib.auth.hashers import check_password
from django.conf import settings
from .models import User, Role
from companies.models import Company
from candidates.models import Candidate
from employers.models import Employer
from projects.models import Project, ProjectSkill, ProjectMilestone
from django.db.models import Prefetch
from applications.models import JobApplication, ProjectApplication
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer,
    UserUpdateSerializer, ChangePasswordSerializer, UserListSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer
)
from candidates.models import Candidate, ReferenceRequest
from applications.models import JobApplication, ProjectApplication
from jobs.models import Job, JobSkill
import logging
logger = logging.getLogger("exceptions")


class UserRegistrationView(generics.CreateAPIView):
    """
    User registration endpoint
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        return Response({
            'user': UserProfileSerializer(user).data,
            'message': 'User registered successfully'
        }, status=status.HTTP_201_CREATED)


class BaseRoleRegistrationView(generics.CreateAPIView):
    """
    Generic registration view that forces a specific userType.
    Subclasses must set `fixed_user_type` to one of the allowed roles.
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    fixed_user_type = None

    def get_serializer(self, *args, **kwargs):
        data = kwargs.get('data')
        if isinstance(data, dict) and self.fixed_user_type:
            # Override/ensure the role set by the endpoint
            data = {**data, 'role': self.fixed_user_type}
            kwargs['data'] = data
        return super().get_serializer(*args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            'user': UserProfileSerializer(user).data,
            'message': 'User registered successfully'
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def user_login(request):
    """
    User login endpoint
    """
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        login(request, user)
        
        # Issue JWT tokens
        refresh = RefreshToken.for_user(user)
        # Determine unified profile completion flag by role
        user_role = getattr(getattr(user, 'role', None), 'name', None)
        profile_completed = False
        employer_company_completed = False
        try:
            # Fast path: if employer profile exists and is linked to a company, treat as completed
            if hasattr(user, 'employer_profile') and getattr(user.employer_profile, 'company_id', None):
                employer_company_completed = True
            else:
                # Fallback: check completed companies created by the user
                employer_company_completed = Company.objects.filter(
                    created_by=user, is_active=True, is_completed=True
                ).exists()
        except Exception as e:
            logger.exception(e)
            employer_company_completed = Company.objects.filter(
                created_by=user, is_active=True, is_completed=True
            ).exists()

        if user_role == getattr(settings, 'USER_ROLE_EMPLOYER', 'employer') or (user_role is None and employer_company_completed):
            profile_completed = employer_company_completed
        elif user_role == getattr(settings, 'USER_ROLE_CANDIDATE', 'candidate') or (user_role is None and hasattr(user, 'candidate_profile')):
            try:
                candidate_profile = user.candidate_profile
                profile_completed = candidate_profile.is_profile_complete
            except Candidate.DoesNotExist:
                logger.error('Candidate.DoesNotExist: Candidate profile does not exist')
                profile_completed = False

        # Persist the latest computed state on the user for quick access elsewhere
        if user.profile_completed != profile_completed:
            user.profile_completed = profile_completed
            user.save(update_fields=['profile_completed'])

        return Response({
            'user': UserProfileSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'message': 'Login successful',
            'profile_completed': profile_completed,
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def user_logout(request):
    """
    User logout endpoint
    """
    logout(request)
    return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    User profile view
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class UserUpdateView(generics.UpdateAPIView):
    """
    User profile update view
    """
    serializer_class = UserUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    """
    Change password endpoint
    """
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Return fresh JWT tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Password changed successfully',
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserListView(generics.ListAPIView):
    """
    User list view (admin only)
    """
    queryset = User.objects.all()
    serializer_class = UserListSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Only allow admin users to see all users
        if self.request.user.is_staff:
            return User.objects.all()
        return User.objects.none()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_dashboard(request):
    """
    Admin dashboard data: aggregates across users, candidates, employers, jobs, projects, and applications.
    Only accessible to admin users (role == USER_ROLE_ADMIN or is_staff True).
    """
    user = request.user
    role_name = getattr(getattr(user, 'role', None), 'name', None)
    admin_role = getattr(settings, 'USER_ROLE_ADMIN', 'admin')
    if not (getattr(user, 'is_staff', False) or role_name == admin_role):
        return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    # Initialize pagination
    pagination = CustomPagination()
    page_size = request.query_params.get('page_size', 20)  # Default page size is 20
    
    # Get recent items with pagination
    recent_candidates = Candidate.objects.order_by('-created_at').values('id', 'full_name', 'title')
    recent_employers = Employer.objects.order_by('-created_at').values('id', 'first_name', 'last_name', 'company__company_name')
    recent_jobs = Job.objects.order_by('-created_at').values('id', 'title', 'status')
    recent_projects = Project.objects.order_by('-created_at').values('id', 'title', 'status')
    
    # Paginate each queryset
    paginated_candidates = pagination.paginate_queryset(recent_candidates, request)
    paginated_employers = pagination.paginate_queryset(recent_employers, request)
    paginated_jobs = pagination.paginate_queryset(recent_jobs, request)
    paginated_projects = pagination.paginate_queryset(recent_projects, request)
    
    data = {
        'summary': {
            'total_users': User.objects.count(),
            'total_candidates': Candidate.objects.count(),
            'total_employers': Employer.objects.count(),
            'total_jobs': Job.objects.count(),
            'total_projects': Project.objects.count(),
            'total_job_applications': JobApplication.objects.count(),
            'total_project_applications': ProjectApplication.objects.count(),
        },
        'recent': {
            'candidates': list(paginated_candidates),
            'employers': list(paginated_employers),
            'jobs': list(paginated_jobs),
            'projects': list(paginated_projects),
        },
        'pagination': {
            'count': pagination.page.paginator.count,
            'next': pagination.get_next_link(),
            'previous': pagination.get_previous_link(),
            'page_size': int(page_size)
        }
    }

    return Response(data, status=status.HTTP_200_OK)


def check_admin_permission(user):
    """Helper function to check if user is admin"""
    role_name = getattr(getattr(user, 'role', None), 'name', None)
    admin_role = getattr(settings, 'USER_ROLE_ADMIN', 'admin')
    return getattr(user, 'is_staff', False) or role_name == admin_role



@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_employer_detail(request, pk):
    """Get company details for a specific employer"""
    if not check_admin_permission(request.user):
        return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        employer = Employer.objects.select_related('company', 'user').get(pk=pk)
        
        if not employer.company:
            return Response({'detail': 'No company found for this employer'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        # Get counts for jobs and projects
        total_jobs = Job.objects.filter(employer=employer.user).count() if employer.user else 0
        total_projects = Project.objects.filter(employer=employer.user).count() if employer.user else 0
        
        # Prepare company data
        data = {
            'id': employer.company.id,
            'profile_completed': bool(employer.company.name and employer.company.industry and employer.company.size),
            'company_name': employer.company.name if hasattr(employer.company, 'name') else '',
            'description': employer.company.description if hasattr(employer.company, 'description') else '',
            'industry': employer.company.industry if hasattr(employer.company, 'industry') else '',
            'size': employer.company.size if hasattr(employer.company, 'size') else '',
            'website': employer.company.website if hasattr(employer.company, 'website') else '',
            'logo': employer.company.logo.url if employer.company.logo else None,
            'location': employer.company.location if hasattr(employer.company, 'location') else '',
            'values': employer.company.values if hasattr(employer.company, 'values') else [],
            'is_verified': employer.company.is_verified if hasattr(employer.company, 'is_verified') else False,
            'is_active': employer.company.is_active if hasattr(employer.company, 'is_active') else True,
            'is_completed': all([
                employer.company.name,
                employer.company.industry,
                employer.company.size,
                employer.company.description
            ]),
            'total_jobs': total_jobs,
            'total_projects': total_projects,
            'total_hires': 0,  # You'll need to implement this based on your hiring logic
            'total_employees': 0,  # You'll need to implement this based on your employee count
            'created_at': employer.company.created_at if hasattr(employer.company, 'created_at') else None,
            'updated_at': employer.company.updated_at if hasattr(employer.company, 'updated_at') else None,
            'created_by': employer.company.created_by.id if hasattr(employer.company, 'created_by') and employer.company.created_by else None
        }
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Employer.DoesNotExist:
        logger.error('Employer.DoesNotExist: Employer not found')
        return Response({'detail': 'Employer not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_candidate_detail(request, pk):
    """Get details of a specific candidate with complete profile"""
    if not check_admin_permission(request.user):
        return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)    
    try:
        # Get candidate with related data
        candidate = Candidate.objects.select_related('user').prefetch_related(
            Prefetch('job_applications', queryset=JobApplication.objects.select_related('job', 'company').order_by('-applied_at')),
            Prefetch('project_applications', queryset=ProjectApplication.objects.select_related('project', 'company').order_by('-applied_at'))
        ).get(pk=pk)
        
        # Get reference responses
        reference_responses = ReferenceRequest.objects.filter(
            candidate=candidate,
            status='completed'
        ).values('id', 'reference_name', 'reference_email', 'suggested_relationship', 'reply_message')
        
        # Process job applications
        job_applications = []
        job_apps = candidate.job_applications.select_related('job', 'company').all()
        for app in job_apps:
            job_applications.append({
                'id': app.id,
                'type': 'job',
                'title': getattr(app.job, 'title', '') if hasattr(app, 'job') and app.job else '',
                'company': getattr(app.company, 'name', '') if hasattr(app, 'company') and app.company else '',
                'status': getattr(app, 'status', ''),
                'applied_at': getattr(app, 'applied_at', None),
                'is_shortlisted': getattr(app, 'is_shortlisted', False),
                'is_rejected': getattr(app, 'is_rejected', False)
            })
        
        # Process project applications
        project_applications = []
        project_apps = candidate.project_applications.select_related('project', 'company').all()
        for app in project_apps:
            project_applications.append({
                'id': app.id,
                'type': 'project',
                'title': getattr(app.project, 'title', '') if hasattr(app, 'project') and app.project else '',
                'company': getattr(app.company, 'name', '') if hasattr(app, 'company') and app.company else '',
                'status': getattr(app, 'status', ''),
                'applied_at': getattr(app, 'applied_at', None),
                'is_shortlisted': getattr(app, 'is_shortlisted', False),
                'is_rejected': getattr(app, 'is_rejected', False)
            })
        
        # Combine and sort all applications by applied_at
        all_applications = sorted(
            job_applications + project_applications,
            key=lambda x: x['applied_at'] if x['applied_at'] else '',
            reverse=True
        )
        
        # Paginate applications
        pagination = CustomPagination()
        page_size = request.query_params.get('page_size', 20)
        paginated_applications = pagination.paginate_queryset(all_applications, request)
        
        data = {
            'id': candidate.id,
            'full_name': getattr(candidate, 'full_name', ''),
            'email': candidate.user.email if hasattr(candidate, 'user') and candidate.user else None,
            'profile_completed': all([
                getattr(candidate, 'title', None),
                getattr(candidate, 'bio', None),
                getattr(candidate, 'skills', None),
                getattr(candidate, 'preferred_roles', None),
                getattr(candidate, 'min_salary', None) is not None,
                getattr(candidate, 'max_salary', None) is not None
            ]),
            'title': getattr(candidate, 'title', ''),
            'bio': getattr(candidate, 'bio', ''),
            'work_style': getattr(candidate, 'work_style', ''),
            'availability_type': getattr(candidate, 'availability_type', ''),
            'skills': getattr(candidate, 'skills', []),
            'superpowers': getattr(candidate, 'superpowers', []),
            'preferred_roles': getattr(candidate, 'preferred_roles', []),
            'min_salary': getattr(candidate, 'min_salary', None),
            'max_salary': getattr(candidate, 'max_salary', None),
            'resume_url': getattr(candidate, 'resume_url', ''),
            'video_intro_url': getattr(candidate, 'video_intro_url', ''),
            'video_transcription': getattr(candidate, 'video_transcription', ''),
            'privacy_completed': getattr(candidate, 'privacy_completed', False),
            'location': getattr(candidate, 'location', ''),
            'passion_projects': getattr(candidate, 'passion_projects', ''),
            'profile_image': candidate.user.profile_image.url if hasattr(candidate, 'user') and hasattr(candidate.user, 'profile_image') and candidate.user.profile_image else None,
            'profile_views': getattr(candidate, 'profile_views', 0),
            'viewers_count': len(getattr(candidate, 'viewers', [])),
            'profile_views_display': str(getattr(candidate, 'profile_views', 0)),
            'created_at': getattr(candidate, 'created_at', None),
            'updated_at': getattr(candidate, 'updated_at', None),
            'user': candidate.user.id if hasattr(candidate, 'user') and candidate.user else None,
            'reference_responses': list(reference_responses),
            'applications': paginated_applications,
            'applications_count': len(all_applications),
            'pagination': {
                'count': len(all_applications),
                'next': pagination.get_next_link(),
                'previous': pagination.get_previous_link(),
                'page_size': int(page_size)
            }
        }
        return Response(data, status=status.HTTP_200_OK)
    except Candidate.DoesNotExist:
        logger.error('Candidate.DoesNotExist: Candidate not found')
        return Response({'detail': 'Candidate not found'}, status=status.HTTP_404_NOT_FOUND)



@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_job_detail(request, pk):
    """Get complete details of a specific job"""
    if not check_admin_permission(request.user):
        return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
    try:
        # Get job with related data
        job = Job.objects.select_related('company').prefetch_related('required_skills').get(pk=pk)
        
        # Get company details
        company_name = job.company.name if hasattr(job, 'company') and job.company else None
        company_id = job.company.id if hasattr(job, 'company') and job.company else None
        
        # Get employer details
        employer = None
        if hasattr(job, 'employer') and job.employer:
            try:
                employer = Employer.objects.get(user=job.employer)
            except Employer.DoesNotExist:
                logger.error("Employer.DoesNotExist: Employer object not found for job.employer")
                pass
        
        # Get required skills with details
        required_skills = []
        if hasattr(job, 'required_skills'):
            required_skills = [{
                'id': skill.id,
                'name': skill.name,
                'level': skill.level,
                'is_required': skill.is_required
            } for skill in job.required_skills.all()]
        
        data = {
            'id': job.id,
            'title': getattr(job, 'title', ''),
            'description': getattr(job, 'description', ''),
            'company_name': company_name,
            'company_id': company_id,
            'workStyle': getattr(job, 'work_style', '').lower() if hasattr(job, 'work_style') else None,
            'category': getattr(job, 'category', '').lower() if hasattr(job, 'category') else None,
            'experienceLevel': getattr(job, 'experience_level', '').lower() if hasattr(job, 'experience_level') else None,
            'employmentType': getattr(job, 'employment_type', '').lower() if hasattr(job, 'employment_type') else None,
            'skills': getattr(job, 'skills', []),
            'salaryRangeMin': getattr(job, 'min_salary', None),
            'salaryRangeMax': getattr(job, 'max_salary', None),
            'benefits': getattr(job, 'benefits', []),
            'applicationDeadline': getattr(job, 'application_deadline', None),
            'hasTemporaryOption': getattr(job, 'has_temporary_option', False),
            'temporaryDuration': getattr(job, 'temporary_duration', None),
            'status': getattr(job, 'status', '').lower() if hasattr(job, 'status') else None,
            'created_at': getattr(job, 'created_at', None),
            'updated_at': getattr(job, 'updated_at', None),
            'required_skills': required_skills,
            'employer': {
                'id': employer.id if employer else None,
                'name': employer.full_name if employer else None,
                'email': job.employer.email if hasattr(job, 'employer') and job.employer else None
            } if employer or hasattr(job, 'employer') else None
        }
        return Response(data, status=status.HTTP_200_OK)
    except Job.DoesNotExist:
        logger.error("Job.DoesNotExist: Job record not found for the given identifier")
        return Response({'detail': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def admin_project_detail(request, pk):
    """Get complete details of a specific project"""
    if not check_admin_permission(request.user):
        return Response({'detail': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    try:
        # Get project with related data
        project = Project.objects.select_related('company').prefetch_related(
            'required_skills',
            Prefetch('milestones', queryset=ProjectMilestone.objects.order_by('due_date'))
        ).get(pk=pk)
        
        # Get company details
        company_name = project.company.name if hasattr(project, 'company') and project.company else None
        company_id = project.company.id if hasattr(project, 'company') and project.company else None
        
        # Get employer details
        employer = None
        if hasattr(project, 'employer') and project.employer:
            try:
                employer = Employer.objects.get(user=project.employer)
            except Employer.DoesNotExist:
                logger.error("Employer.DoesNotExist: Employer not found for project.employer")
                pass
        
        # Get required skills with details
        required_skills = []
        if hasattr(project, 'required_skills'):
            required_skills = [{
                'id': skill.id,
                'name': skill.name,
                'level': skill.level,
                'is_required': skill.is_required
            } for skill in project.required_skills.all()]
        
        # Get project milestones
        milestones = []
        if hasattr(project, 'milestones'):
            milestones = [{
                'id': m.id,
                'title': m.title,
                'description': m.description,
                'due_date': m.due_date,
                'payment_amount': m.payment_amount
            } for m in project.milestones.all()]
        
        data = {
            'id': project.id,
            'title': getattr(project, 'title', ''),
            'description': getattr(project, 'description', ''),
            'company_name': company_name,
            'company_id': company_id,
            'category': getattr(project, 'category', '').lower() if hasattr(project, 'category') else 'other',
            'estimatedHours': getattr(project, 'estimated_hours', None),
            'paymentType': getattr(project, 'payment_type', '').lower() if hasattr(project, 'payment_type') else None,
            'paymentAmount': getattr(project, 'payment_amount', None),
            'skills': getattr(project, 'skills', []),
            'deadline': getattr(project, 'deadline', None),
            'status': getattr(project, 'status', '').lower() if hasattr(project, 'status') else None,
            'created_at': getattr(project, 'created_at', None),
            'updated_at': getattr(project, 'updated_at', None),
            'required_skills': required_skills,
            'milestones': milestones,
            'employer': {
                'id': employer.id if employer else None,
                'name': employer.full_name if employer else None,
                'email': project.employer.email if hasattr(project, 'employer') and project.employer else None
            } if employer or hasattr(project, 'employer') else None
        }
        return Response(data, status=status.HTTP_200_OK)
    except Project.DoesNotExist:
        logger.error("Project.DoesNotExist: Project record not found for the given identifier")
        return Response({'detail': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_request(request):
    """
    Initiate password reset: user submits email, we send reset link via email.
    """
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response({
        'message': 'Reset link has been sent on your email'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    """
    Confirm reset by providing token and new password.
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'The password has been reset successfully.'}, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def roles_list(request):
    """
    Public endpoint to list available roles for registration selector.
    Only returns 'candidate' and 'employer' roles.
    Returns: [{id, name, description}]
    """
    roles = list(Role.objects.filter(
        name__in=['candidate', 'employer']
    ).values('id', 'name', 'description'))
    return Response({'results': roles}, status=status.HTTP_200_OK)