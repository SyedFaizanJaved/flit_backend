from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from . import views

urlpatterns = [
    # Authentication
    path('register/', views.UserRegistrationView.as_view(), name='user-register'),
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
    path('dashboard/', views.user_dashboard, name='user-dashboard'),
    path('roles/', views.roles_list, name='roles-list'),
    
    # Admin
    path('list/', views.UserListView.as_view(), name='user-list'),
]