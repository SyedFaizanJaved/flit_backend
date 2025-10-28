from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.CandidateViewSet, basename='candidates')

urlpatterns = [
    # Registration
    path('register/', views.CandidateRegistrationView.as_view(), name='candidate-register'),
    path('conversations/', views.CandidateEmployerConversationListView.as_view(), name='candidate-employer-conversations'),
    # Work DNA (kept as-is)
    path('work-dna/', views.WorkDNAView.as_view(), name='work-dna'),
    # References
    path('references/', views.ReferenceListView.as_view(), name='reference-list'),
    path('references/<int:pk>/', views.ReferenceDetailView.as_view(), name='reference-detail'),
    # Reference Requests
    path('reference-requests/', views.ReferenceRequestListView.as_view(), name='reference-request-list'),
    path('reference-requests/<int:pk>/', views.ReferenceRequestDetailView.as_view(), name='reference-request-detail'),
    # Router-based endpoints for list/profile/dashboard/complete-section
    path('', include(router.urls)),
]
