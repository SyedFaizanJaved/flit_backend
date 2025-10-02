from django.urls import path
from . import views

urlpatterns = [
    # Project Management
    path('', views.ProjectListView.as_view(), name='project-list'),
    path('<int:pk>/', views.ProjectDetailView.as_view(), name='project-detail'),
    
    # My Projects
    path('my-projects/', views.MyProjectsView.as_view(), name='my-projects'),
    
    # Project Skills
    path('<int:project_id>/skills/', views.ProjectSkillView.as_view(), name='project-skills'),
    
    # Project Milestones
    path('<int:project_id>/milestones/', views.ProjectMilestoneView.as_view(), name='project-milestones'),
    
    # Project Applications
    path('<int:project_id>/applications/', views.project_applications, name='project-applications'),
    path('<int:project_id>/status/', views.update_project_status, name='update-project-status'),
    path('<int:project_id>/applications/<int:application_id>/shortlist/', views.shortlist_application, name='shortlist-application'),
    path('<int:project_id>/applications/<int:application_id>/reject/', views.reject_application, name='reject-application'),
]
