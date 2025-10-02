from django.urls import path
from . import views

urlpatterns = [
    # Profile Management
    path('profile/', views.CandidateProfileView.as_view(), name='candidate-profile'),
    path('profile/update/', views.CandidateProfileUpdateView.as_view(), name='candidate-profile-update'),
    path('profile/complete/<str:section>/', views.complete_profile_section, name='complete-profile-section'),
    
    # Public Profiles
    path('list/', views.CandidateListView.as_view(), name='candidate-list'),
    
    # Work DNA
    path('work-dna/', views.WorkDNAView.as_view(), name='work-dna'),
    
    # References
    path('references/', views.ReferenceListView.as_view(), name='reference-list'),
    path('references/<int:pk>/', views.ReferenceDetailView.as_view(), name='reference-detail'),
    
    # Reference Requests
    path('reference-requests/', views.ReferenceRequestListView.as_view(), name='reference-request-list'),
    path('reference-requests/<int:pk>/', views.ReferenceRequestDetailView.as_view(), name='reference-request-detail'),
    
    # Dashboard
    path('dashboard/', views.candidate_dashboard, name='candidate-dashboard'),
]
