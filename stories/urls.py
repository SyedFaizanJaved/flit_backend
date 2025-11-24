from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views_company_project_job import (
    CompanyLikeView, CompanyCommentListCreateView, CompanySaveView,
    ProjectLikeView, ProjectCommentListCreateView, ProjectSaveView,
    JobLikeView, JobCommentListCreateView, JobSaveView,
    CompanyListView, ProjectListView, JobListView
)

app_name = 'stories'

# Story endpoints
story_urlpatterns = [
    path('', views.StoryListCreateView.as_view(), name='story-list-create'),
    path('<int:pk>/', views.StoryDetailView.as_view(), name='story-detail'),
    path('<int:story_id>/like/', views.LikeStoryView.as_view(), name='like-story'),
    path('<int:story_id>/comments/', views.CommentListView.as_view(), name='comment-list'),
    path('<int:story_id>/comments/create/', views.CommentCreateView.as_view(), name='comment-create'),
    path('<int:story_id>/save/', views.SaveStoryView.as_view(), name='save-story'),
    path('saved/', views.SavedStoriesListView.as_view(), name='saved-stories'),
]

# Company interaction endpoints
company_urlpatterns = [
    path('', CompanyListView.as_view(), name='company-list'),
    path('<int:pk>/like/', CompanyLikeView.as_view(), name='company-like'),
    path('<int:pk>/comments/', CompanyCommentListCreateView.as_view(), name='company-comments'),
    path('<int:pk>/save/', CompanySaveView.as_view(), name='company-save'),
]

# Project interaction endpoints
project_urlpatterns = [
    path('', ProjectListView.as_view(), name='project-list'),
    path('<int:pk>/like/', ProjectLikeView.as_view(), name='project-like'),
    path('<int:pk>/comments/', ProjectCommentListCreateView.as_view(), name='project-comments'),
    path('<int:pk>/save/', ProjectSaveView.as_view(), name='project-save'),
]

# Job interaction endpoints
job_urlpatterns = [
    path('', JobListView.as_view(), name='job-list'),
    path('<int:pk>/like/', JobLikeView.as_view(), name='job-like'),
    path('<int:pk>/comments/', JobCommentListCreateView.as_view(), name='job-comments'),
    path('<int:pk>/save/', JobSaveView.as_view(), name='job-save'),
]

urlpatterns = [
    path('stories/', include((story_urlpatterns, 'stories'))),
    path('companies/', include((company_urlpatterns, 'companies'))),
    path('projects/', include((project_urlpatterns, 'projects'))),
    path('jobs/', include((job_urlpatterns, 'jobs'))),
]
