from django.urls import path
from . import views

urlpatterns = [
    # Combined Applications
    path('combined/', views.CombinedApplicationsView.as_view(), name='combined-applications'),
    
    # Job Applications
    path('jobs/', views.JobApplicationListView.as_view(), name='job-application-list'),
    path('jobs/<int:pk>/', views.JobApplicationDetailView.as_view(), name='job-application-detail'),
    
    # Project Applications
    path('projects/', views.ProjectApplicationListView.as_view(), name='project-application-list'),
    path('projects/<int:pk>/', views.ProjectApplicationDetailView.as_view(), name='project-application-detail'),
    
    # Interviews
    path('interviews/', views.InterviewListView.as_view(), name='interview-list'),
    path('interviews/<int:pk>/', views.InterviewDetailView.as_view(), name='interview-detail'),
    
    # Messages
    path('messages/', views.ApplicationMessageListView.as_view(), name='application-message-list'),
    
    # Interview Requests
    path('interview-requests/', views.InterviewRequestListView.as_view(), name='interview-request-list'),
    path('interview-requests/<int:pk>/', views.InterviewRequestupdateView.as_view(), name='interview-request-update'),
    
    # Application Actions
    path('apply/job/<int:job_id>/', views.apply_to_job, name='apply-to-job'),
    path('apply/project/<int:project_id>/', views.apply_to_project, name='apply-to-project'),
    path('withdraw/<str:application_type>/<int:application_id>/', views.withdraw_application, name='withdraw-application'),
]
