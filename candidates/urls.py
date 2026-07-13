from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views_reference import (
    VerifyReferenceTokenView,
    ReferenceResponseView,
    ReferenceResponsesView 
)
from .views import DiscoverTalentView, CandidateRegistrationView

router = DefaultRouter()
router.register(r'', views.CandidateViewSet, basename='candidates')

urlpatterns = [
    path('reference-requests/', views.ReferenceRequestViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='reference-request-list'),

    path('reference-requests/<int:pk>/', views.ReferenceRequestViewSet.as_view({
        'get': 'retrieve',
        'patch': 'partial_update',
        'put': 'update',
        'delete': 'destroy'
    }), name='reference-request-detail'),

    path('reference-requests/<int:pk>/delete-response/', views.ReferenceRequestViewSet.as_view({
        'delete': 'delete_response'
    }), name='reference-request-delete-response'),

    path('register/', CandidateRegistrationView.as_view(), name='candidate-register'),
    path('discover-talent/', DiscoverTalentView.as_view(), name='discover-talent'),
  

    # Reference verification and response
    path('verify-reference-token/', VerifyReferenceTokenView.as_view(), name='verify-reference-token'),
    path('respond-to-reference/', ReferenceResponseView.as_view(http_method_names=['get', 'post']), name='respond-to-reference'),
    path('reference-responses/', ReferenceResponsesView.as_view(), name='reference-responses'),

    # Public, unauthenticated shareable candidate profile (opt-in). Must be
    # registered before the router include so its catch-all doesn't swallow it.
    path('public/share/<uuid:token>/', views.PublicShareCandidateProfileView.as_view(), name='public-share-candidate-profile'),
    path('public/share/<uuid:token>/track-view/', views.PublicShareCandidateTrackView.as_view(), name='public-share-candidate-track-view'),
    path('public/<int:pk>/', views.PublicCandidateProfileView.as_view(), name='public-candidate-profile'),
    path('public/<int:pk>/track-view/', views.PublicCandidateProfileViewTrackView.as_view(), name='public-candidate-track-view'),

    path('', include(router.urls)),
   
  
]