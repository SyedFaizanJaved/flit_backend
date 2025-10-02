from django.urls import path
from . import views

urlpatterns = [
    # Job Management
    path('', views.JobListView.as_view(), name='job-list'),
    path('<int:pk>/', views.JobDetailView.as_view(), name='job-detail'),
    
    # My Jobs
    path('my-jobs/', views.MyJobsView.as_view(), name='my-jobs'),
    
    # Job Skills
    path('<int:job_id>/skills/', views.JobSkillView.as_view(), name='job-skills'),
    
    # Job Languages
    path('<int:job_id>/languages/', views.JobLanguageView.as_view(), name='job-languages'),
    
    # Job Applications
    path('<int:job_id>/applications/', views.job_applications, name='job-applications'),
    path('<int:job_id>/status/', views.update_job_status, name='update-job-status'),
    path('<int:job_id>/applications/<int:application_id>/shortlist/', views.shortlist_application, name='shortlist-application'),
    path('<int:job_id>/applications/<int:application_id>/reject/', views.reject_application, name='reject-application'),
]
