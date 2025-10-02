from django.urls import path
from . import views

urlpatterns = [
    # Profile Management
    path('profile/', views.EmployerProfileView.as_view(), name='employer-profile'),
    path('profile/update/', views.EmployerProfileUpdateView.as_view(), name='employer-profile-update'),
    path('profile/complete/<str:section>/', views.complete_profile_section, name='complete-profile-section'),
    
    # Public Profiles
    path('list/', views.EmployerListView.as_view(), name='employer-list'),
    
    # Preferences
    path('preferences/', views.EmployerPreferenceView.as_view(), name='employer-preferences'),
    
    # Compliance
    path('compliance/', views.EmployerComplianceView.as_view(), name='employer-compliance'),
    
    # Dashboard
    path('dashboard/', views.employer_dashboard, name='employer-dashboard'),
]
