from django.urls import path
from . import views

app_name = 'stories'

urlpatterns = [
    # Story endpoints
    path('', views.StoryListCreateView.as_view(), name='story-list-create'),
    path('<int:pk>/', views.StoryDetailView.as_view(), name='story-detail'),
    path('<int:story_id>/like/', views.LikeStoryView.as_view(), name='like-story'),
    path('<int:story_id>/comments/', views.CommentListView.as_view(), name='comment-list'),
    path('<int:story_id>/comments/create/', views.CommentCreateView.as_view(), name='comment-create'),
    path('<int:story_id>/save/', views.SaveStoryView.as_view(), name='save-story'),
    path('<int:story_id>/view/', views.MarkStoryViewedView.as_view(), name='view-story'),
    path('saved/', views.SavedStoriesListView.as_view(), name='saved-stories'),

    # User stories
    path('<int:user_id>/stories/', views.UserStoriesView.as_view(), name='user-stories'),

    # Company interaction endpoints
    path('companies/', views.CompanyListView.as_view(), name='company-list'),
    path('companies/<int:pk>/like/', views.CompanyLikeView.as_view(), name='company-like'),
    path('companies/<int:pk>/comments/', views.CompanyCommentListCreateView.as_view(), name='company-comments'),
    path('companies/<int:pk>/save/', views.CompanySaveView.as_view(), name='company-save'),

    # Project interaction endpoints
    path('projects/', views.ProjectListView.as_view(), name='project-list'),
    path('projects/<int:pk>/like/', views.ProjectLikeView.as_view(), name='project-like'),
    path('projects/<int:pk>/comments/', views.ProjectCommentListCreateView.as_view(), name='project-comments'),
    path('projects/<int:pk>/save/', views.ProjectSaveView.as_view(), name='project-save'),

    # Job interaction endpoints
    path('jobs/', views.JobListView.as_view(), name='job-list'),
    path('jobs/<int:pk>/like/', views.JobLikeView.as_view(), name='job-like'),
    path('jobs/<int:pk>/comments/', views.JobCommentListCreateView.as_view(), name='job-comments'),
    path('jobs/<int:pk>/save/', views.JobSaveView.as_view(), name='job-save'),

    # Candidate interaction endpoints
    path('candidates/', views.CandidateListView.as_view(), name='candidate-list'),
    path('candidates/<int:pk>/like/', views.CandidateLikeView.as_view(), name='candidate-like'),
    path('candidates/<int:pk>/comments/', views.CandidateCommentListCreateView.as_view(), name='candidate-comments'),
    path('candidates/<int:pk>/save/', views.CandidateSaveView.as_view(), name='candidate-save'),

    # All saved items (companies, projects, jobs, candidates)
    path('saved-items/', views.AllSavedItemsView.as_view(), name='all-saved-items'),
]