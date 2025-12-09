from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views_company_project_job import (
    CompanyLikeView, CompanyCommentListCreateView, CompanySaveView,
    ProjectLikeView, ProjectCommentListCreateView, ProjectSaveView,
    JobLikeView, JobCommentListCreateView, JobSaveView,
    CompanyListView, ProjectListView, JobListView, CandidateListView,
    CandidateLikeView, CandidateCommentListCreateView, CandidateSaveView,
    AllSavedItemsView,UserStoriesView
)

app_name = 'stories'

urlpatterns = [
    # Story endpoints
    path('', views.StoryListCreateView.as_view(), name='story-list-create'),
    path('<int:pk>/', views.StoryDetailView.as_view(), name='story-detail'),
    path('<int:story_id>/like/', views.LikeStoryView.as_view(), name='like-story'),
    path('<int:story_id>/comments/', views.CommentListView.as_view(), name='comment-list'),
    path('<int:story_id>/comments/create/', views.CommentCreateView.as_view(), name='comment-create'),
    path('<int:story_id>/save/', views.SaveStoryView.as_view(), name='save-story'),
    path('saved/', views.SavedStoriesListView.as_view(), name='saved-stories'),

    # User stories
    path('<int:user_id>/stories/', UserStoriesView.as_view(), name='user-stories'),

    
    # Company interaction endpoints
    path('companies/', CompanyListView.as_view(), name='company-list'),
    path('companies/<int:pk>/like/', CompanyLikeView.as_view(), name='company-like'),
    path('companies/<int:pk>/comments/', CompanyCommentListCreateView.as_view(), name='company-comments'),
    path('companies/<int:pk>/save/', CompanySaveView.as_view(), name='company-save'),
    
    # Project interaction endpoints
    path('projects/', ProjectListView.as_view(), name='project-list'),
    path('projects/<int:pk>/like/', ProjectLikeView.as_view(), name='project-like'),
    path('projects/<int:pk>/comments/', ProjectCommentListCreateView.as_view(), name='project-comments'),
    path('projects/<int:pk>/save/', ProjectSaveView.as_view(), name='project-save'),
    
    # Job interaction endpoints
    path('jobs/', JobListView.as_view(), name='job-list'),
    path('jobs/<int:pk>/like/', JobLikeView.as_view(), name='job-like'),
    path('jobs/<int:pk>/comments/', JobCommentListCreateView.as_view(), name='job-comments'),
    path('jobs/<int:pk>/save/', JobSaveView.as_view(), name='job-save'),
    
    # Candidate interaction endpoints
    path('candidates/', CandidateListView.as_view(), name='candidate-list'),
    path('candidates/<int:pk>/like/', CandidateLikeView.as_view(), name='candidate-like'),
    path('candidates/<int:pk>/comments/', CandidateCommentListCreateView.as_view(), name='candidate-comments'),
    path('candidates/<int:pk>/save/', CandidateSaveView.as_view(), name='candidate-save'),
    
    # Saved items
    path('saved-items/', AllSavedItemsView.as_view(), name='all-saved-items'),
]
