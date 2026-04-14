from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router for ViewSets
router = DefaultRouter()
router.register(r'jobs', views.JobApplicationViewSet, basename='job-application')
router.register(r'projects', views.ProjectApplicationViewSet, basename='project-application')

urlpatterns = [
    # Combined Applications
    path('combined/', views.CombinedApplicationsView.as_view(), name='combined-applications'),
    path('active-postings/', views.ActivePostingsListView.as_view(), name='active-postings-list'),
    
    path('', include(router.urls)),
    
    # Custom actions
    path('apply/job/<int:job_id>/', views.apply_to_job, name='apply-to-job'),
    path('apply/project/<int:project_id>/', views.apply_to_project, name='apply-to-project'),
    path('withdraw/<str:application_type>/<int:application_id>/', views.withdraw_application, name='withdraw-application'),
]