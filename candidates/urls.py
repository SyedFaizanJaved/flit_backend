from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views_reference import (
    VerifyReferenceTokenView, 
    ReferenceResponseView,
    ReferenceResponsesView
)
from .views import DiscoverTalentView

router = DefaultRouter()
router.register(r'', views.CandidateViewSet, basename='candidates')

# Dashboard endpoints
urlpatterns = [
    # Legacy dashboard (all-in-one)
    path('dashboard/', views.CandidateDashboardView.as_view(), name='candidate-dashboard'),
    
    # New separated dashboard endpoints
    path('dashboard/profile/', views.CandidateProfileDashboardView.as_view(), name='candidate-profile-dashboard'),
    path('dashboard/applications/', views.CandidateApplicationsView.as_view(), name='candidate-applications'),
    path('work-dna/questions/', views.WorkDNAQuestionView.as_view(), name='work-dna-questions'),
    path('dashboard/latest-jobs/', views.CandidateLatestJobsView.as_view(), name='candidate-latest-jobs'),
    path('dashboard/latest-projects/', views.CandidateLatestProjectsView.as_view(), name='candidate-latest-projects'),
    path('ai-matching/<int:candidate_id>/', views.CandidateAIMatchingView.as_view(), name='candidate-ai-matching'),
    
    # Registration
    path('register/', views.CandidateRegistrationView.as_view(), name='candidate-register'),
    # Reference Requests
    path('reference-requests/', views.ReferenceRequestListView.as_view(), name='reference-request-list'),
    path('reference-requests/<int:pk>/', views.ReferenceRequestDetailView.as_view(), name='reference-request-detail'),
    # Reference verification and response
    path('verify-reference-token/', VerifyReferenceTokenView.as_view(), name='verify-reference-token'),
    path('respond-to-reference/', ReferenceResponseView.as_view(), name='respond-to-reference'),
    path('reference-responses/', ReferenceResponsesView.as_view(), name='reference-responses'),
   
    # Talent discovery endpoint
    path('discover-talent/', DiscoverTalentView.as_view(), name='discover-talent'),
    
    # Router-based endpoints for list/profile/dashboard/complete-section
    path('', include(router.urls)),
]
