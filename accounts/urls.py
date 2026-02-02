from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from . import views

urlpatterns = [
    # Authentication
    path('register/', views.UserRegistrationView.as_view(), name='user-register'),
    path('verify-email/', views.verify_email, name='verify-email'),
    path('login/', views.user_login, name='user-login'),
    path('logout/', views.user_logout, name='user-logout'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Profile Management
    path('profile/', views.UserProfileView.as_view(), name='user-profile'),
    path('profile/update/', views.UserUpdateView.as_view(), name='user-update'),
    path('change-password/', views.change_password, name='change-password'),
    path('forgot-password/', views.password_reset_request, name='password-reset-request'),
    path('reset-password/', views.password_reset_confirm, name='password-reset-confirm'),
    
    # Dashboard
    path('roles/', views.roles_list, name='roles-list'),
    
    # Admin
    path('list/', views.UserListView.as_view(), name='user-list'),
    path('admin/dashboard/', views.admin_dashboard, name='admin-dashboard'),
    path('admin/employers/<int:pk>/', views.admin_employer_detail, name='admin-employer-detail'),
    path('admin/candidates/<int:pk>/', views.admin_candidate_detail, name='admin-candidate-detail'),
    path('admin/jobs/<int:pk>/', views.admin_job_detail, name='admin-job-detail'),
    path('admin/projects/<int:pk>/', views.admin_project_detail, name='admin-project-detail'),
]