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
router.register(r'reference-requests', views.ReferenceRequestViewSet, basename='reference-requests')

urlpatterns = [
    # Registration & Discovery
    path('register/', CandidateRegistrationView.as_view(), name='candidate-register'),
    path('discover-talent/', DiscoverTalentView.as_view(), name='discover-talent'),

    # Reference verification/response (external)
    path('verify-reference-token/', VerifyReferenceTokenView.as_view(), name='verify-reference-token'),
    path('respond-to-reference/', ReferenceResponseView.as_view(), name='respond-to-reference'),
    path('reference-responses/', ReferenceResponsesView.as_view(), name='reference-responses'),

    path('', include(router.urls)),
]