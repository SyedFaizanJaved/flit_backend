from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.EmployerViewSet, basename='employers')
router.register(r'candidate-actions', views.CandidateActionViewSet, basename='candidate-actions')

# Dashboard endpoints
urlpatterns = [
    # Registration
    path('register/', views.EmployerRegistrationView.as_view(), name='employer-register'),
    
    # Dashboard endpoints
    path('dashboard/profile/', views.EmployerProfileDashboardView.as_view(), name='employer-profile-dashboard'),
    path('dashboard/applications/jobs/', views.EmployerJobApplicationsView.as_view(), name='employer-job-applications'),
    path('dashboard/applications/projects/', views.EmployerProjectApplicationsView.as_view(), name='employer-project-applications'),
    
    # ML API Endpoint
    path('ml-flitpass/<int:company_id>/', views.get_flitpass_data, name='get-flitpass-data'),
    
    # Include router URLs
    path('', include(router.urls)),
]
