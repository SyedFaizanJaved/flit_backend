from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import check_password
from django.conf import settings
from .models import User, Role
from companies.models import Company
from candidates.models import Candidate
from employers.models import Employer
from jobs.models import Job
from projects.models import Project
from applications.models import JobApplication, ProjectApplication
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer,
    UserUpdateSerializer, ChangePasswordSerializer, UserListSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer
)


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
        except Exception:
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
def user_dashboard(request):
    """
    User dashboard data
    """
    user = request.user
    data = {
        'user': UserProfileSerializer(user).data,
        'profile_completed': user.profile_completed,
        'role': getattr(getattr(user, 'role', None), 'name', None),
        'totals': {
            'jobs': Job.objects.count(),
            'projects': Project.objects.count(),
            'active_jobs': Job.objects.filter(status='active').count(),
            'active_projects': Project.objects.filter(status='active').count(),
        }
    }
    
    # Add role-specific data
    if getattr(getattr(user, 'role', None), 'name', None) == settings.USER_ROLE_CANDIDATE and hasattr(user, 'candidate_profile'):
        candidate = user.candidate_profile
        data['candidate'] = {
            'profile_completed': candidate.is_profile_complete,
            'applications_count': candidate.applications.count(),
            'references_count': candidate.references.count(),
        }
    elif getattr(getattr(user, 'role', None), 'name', None) == settings.USER_ROLE_EMPLOYER and hasattr(user, 'employer_profile'):
        employer = user.employer_profile
        data['employer'] = {
            'profile_completed': employer.is_profile_complete,
            'jobs_posted': employer.total_jobs_posted,
            'projects_posted': employer.total_projects_posted,
            'applications_received': employer.total_applications_received,
        }
    
    return Response(data, status=status.HTTP_200_OK)


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
            'candidates': list(Candidate.objects.order_by('-created_at').values('id', 'full_name', 'title')[:5]),
            'employers': list(Employer.objects.order_by('-created_at').values('id', 'first_name', 'last_name')[:5]),
            'jobs': list(Job.objects.order_by('-created_at').values('id', 'title', 'status')[:5]),
            'projects': list(Project.objects.order_by('-created_at').values('id', 'title', 'status')[:5]),
        }
    }

    return Response(data, status=status.HTTP_200_OK)


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