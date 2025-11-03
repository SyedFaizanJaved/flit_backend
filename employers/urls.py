from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.EmployerViewSet, basename='employers')

# Dashboard endpoints
urlpatterns = [
    # Registration
    path('register/', views.EmployerRegistrationView.as_view(), name='employer-register'),
    
    # Dashboard endpoints
    path('dashboard/profile/', views.EmployerProfileDashboardView.as_view(), name='employer-profile-dashboard'),
    path('dashboard/applications/jobs/', views.EmployerJobApplicationsView.as_view(), name='employer-job-applications'),
    path('dashboard/applications/projects/', views.EmployerProjectApplicationsView.as_view(), name='employer-project-applications'),
    
    # Include router URLs
    path('', include(router.urls)),
]
