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

    path('reference-responses/', ReferenceResponsesView.as_view(), name='reference-responses'),

    path('', include(router.urls)),
   
    path('register/', CandidateRegistrationView.as_view(), name='candidate-register'),
    path('discover-talent/', DiscoverTalentView.as_view(), name='discover-talent'),
    path('verify-reference-token/', VerifyReferenceTokenView.as_view(), name='verify-reference-token'),
    path('respond-to-reference/', ReferenceResponseView.as_view(), name='respond-to-reference'),
    path('reference-responses/', ReferenceResponsesView.as_view(), name='reference-responses'),

]