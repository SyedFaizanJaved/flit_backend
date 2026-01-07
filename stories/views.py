# stories/views.py

import logging
from datetime import timedelta
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Count, Exists, OuterRef, Case, When, Value, BooleanField, IntegerField, F, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404
from rest_framework import generics, status, permissions, serializers
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from utils.pagination import CustomPagination

from .models import Story, Like, Comment, SavedItem,SavedStory
from .serializers import (
    StorySerializer, CommentSerializer, SavedItemSerializer,
    CompanySerializer, ProjectSerializer, JobSerializer, CandidateSerializer
)
from companies.models import Company
from projects.models import Project
from jobs.models import Job
from candidates.models import Candidate

# Logger setup
logger = logging.getLogger('stories')


# =============================
# STORY VIEWS
# =============================


class StoryListCreateView(generics.ListCreateAPIView):
    serializer_class = StorySerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = CustomPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'request': self.request})
        return context

    def perform_create(self, serializer):
        # ... (perform_create remains unchanged - same as before)
        user = self.request.user
        user_type = None
        company_id = None
        candidate_id = None

        if hasattr(user, 'employer_profile'):
            user_type = 'employer'
            company_id = self.request.data.get('company') or (
                user.employer_profile.company.id if user.employer_profile.company else None
            )
        elif hasattr(user, 'candidate_profile'):
            user_type = 'candidate'
            candidate_id = self.request.data.get('candidate') or user.candidate_profile.id
        else:
            logger.warning(f"User {user.id} attempted to create story without proper profile")
            raise serializers.ValidationError({
                'user': 'User must be either an employer or a candidate to create a story.'
            })

        if user_type == 'employer' and not company_id:
            raise serializers.ValidationError({
                'company': 'Company is required for employer stories.'
            })
        if user_type == 'candidate' and not candidate_id:
            raise serializers.ValidationError({
                'candidate': 'Candidate profile is required for candidate stories'
            })

        data = {'user': user, 'user_type': user_type}
        if user_type == 'employer':
            data['company_id'] = company_id
        elif user_type == 'candidate':
            data['candidate_id'] = candidate_id

        serializer.save(**data)
        logger.info(f"Story created by {user_type} user {user.id}")

    def get_queryset(self):
        user = self.request.user
        queryset = Story.objects.filter(is_active=True)
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
        queryset = queryset.filter(created_at__gte=twenty_four_hours_ago)

        # Optional filter by user_type via query param (e.g., ?user_type=candidate)
        user_type = self.request.query_params.get('user_type')
        if user_type in ['employer', 'candidate']:
            queryset = queryset.filter(user_type=user_type)

        # Optional filter by specific user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # NO automatic filtering by logged-in user's type → everyone sees all stories

        # Annotations
        like_count_sq = Subquery(
            Story.objects.filter(pk=OuterRef('pk'))
            .annotate(count=Count('likes'))
            .values('count')
        )

        comment_count_sq = Comment.objects.filter(
            story_id=OuterRef('pk')
        ).values('story_id').annotate(count=Count('id')).values('count')

        return queryset.annotate(
            like_count=Coalesce(like_count_sq, 0),
            comment_count=Coalesce(comment_count_sq, 0),
            is_liked=Case(
                When(likes=user, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            is_saved=Exists(
                SavedStory.objects.filter(story_id=OuterRef('pk'), user=user)
            )
        ).order_by('-created_at')


class StoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Story.objects.all()
    serializer_class = StorySerializer
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        if self.get_object().user != self.request.user:
            logger.warning(f"User {self.request.user.id} tried to update story {self.get_object().id}")
            raise PermissionDenied("You do not have permission to update this story.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user != self.request.user and not self.request.user.is_staff:
            logger.warning(f"Unauthorized delete attempt on story {instance.id} by {self.request.user.id}")
            raise PermissionDenied("You do not have permission to delete this story.")
        instance.is_active = False
        instance.save()
        logger.info(f"Story {instance.id} soft-deleted by {self.request.user.id}")


class LikeStoryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, story_id):
        story = get_object_or_404(Story, id=story_id, is_active=True)
        if story.likes.filter(id=request.user.id).exists():
            story.likes.remove(request.user)
            logger.info(f"User {request.user.id} unliked story {story_id}")
            return Response({"status": "unliked"}, status=status.HTTP_200_OK)
        else:
            story.likes.add(request.user)
            logger.info(f"User {request.user.id} liked story {story_id}")
            return Response({"status": "liked"}, status=status.HTTP_201_CREATED)


class CommentCreateView(generics.CreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        story = get_object_or_404(Story, id=self.kwargs['story_id'], is_active=True)
        serializer.save(user=self.request.user, story=story)
        logger.info(f"Comment created on story {self.kwargs['story_id']} by user {self.request.user.id}")


class CommentListView(generics.ListAPIView):
    serializer_class = CommentSerializer

    def get_queryset(self):
        return Comment.objects.filter(
            story_id=self.kwargs['story_id'],
            story__is_active=True
        ).order_by('-created_at')


class SaveStoryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, story_id):
        story = get_object_or_404(Story, id=story_id, is_active=True)
        user = request.user
        
        saved_story, created = SavedStory.objects.get_or_create(
            user=user,
            story=story
        )
        
        if not created:
            saved_story.delete()
            logger.info(f"Story {story_id} unsaved by user {user.id}")
            return Response("Story removed from saved", status=status.HTTP_200_OK)
        
        logger.info(f"Story {story_id} saved by user {user.id}")
        return Response("Story saved successfully", status=status.HTTP_201_CREATED)

class SavedStoriesListView(generics.ListAPIView):
    serializer_class = StorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user
        # Get saved active stories with same annotations as StoryListCreateView
        like_count_sq = Subquery(
            Story.objects.filter(pk=OuterRef('story__pk'))
            .annotate(count=Count('likes'))
            .values('count')
        )
        comment_count_sq = Comment.objects.filter(
            story_id=OuterRef('story__pk')
        ).values('story_id').annotate(count=Count('id')).values('count')

        return SavedStory.objects.filter(
            user=user,
            story__is_active=True
        ).select_related('story').annotate(
            like_count=Coalesce(like_count_sq, 0),
            comment_count=Coalesce(comment_count_sq, 0),
            is_liked=Case(
                When(story__likes=user, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            is_saved=Value(True, output_field=BooleanField())  # Always true for saved list
        ).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        stories = [item.story for item in page] if page is not None else [item.story for item in queryset]
        serializer = StorySerializer(stories, many=True, context={'request': request})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })


class UserStoriesView(generics.ListAPIView):
    serializer_class = StorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_id = self.kwargs.get('user_id')
        # Reuse same annotations as main story list
        user = self.request.user
        like_count_sq = Subquery(
            Story.objects.filter(pk=OuterRef('pk'))
            .annotate(count=Count('likes'))
            .values('count')
        )
        comment_count_sq = Comment.objects.filter(
            story_id=OuterRef('pk')
        ).values('story_id').annotate(count=Count('id')).values('count')

        return Story.objects.filter(user_id=user_id).annotate(
            like_count=Coalesce(like_count_sq, 0),
            comment_count=Coalesce(comment_count_sq, 0),
            is_liked=Case(
                When(likes=user, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            is_saved=Exists(
                SavedStory.objects.filter(story_id=OuterRef('pk'), user=user)
            )
        ).order_by('-created_at')

# =============================
# INTERACTION VIEWS
# =============================

class BaseInteractionView(APIView):
    permission_classes = [IsAuthenticated]
    model = None

    def get_object(self, pk):
        return get_object_or_404(self.model, pk=pk)


# Candidate Interactions
class CandidateLikeView(BaseInteractionView):
    model = Candidate

    def get(self, request, pk):
        candidate = self.get_object(pk)
        likes = Like.objects.filter(candidate_id=candidate.id)
        return Response({
            'is_liked': likes.filter(user=request.user).exists(),
            'like_count': likes.count()
        })

    def post(self, request, pk):
        candidate = self.get_object(pk)
        like = Like.objects.filter(candidate_id=candidate.id, user=request.user).first()
        if like:
            like.delete()
            is_liked = False
            logger.info(f"User {request.user.id} unliked candidate {pk}")
        else:
            Like.objects.create(candidate_id=candidate.id, user=request.user)
            is_liked = True
            logger.info(f"User {request.user.id} liked candidate {pk}")
        return Response({
            'is_liked': is_liked,
            'like_count': Like.objects.filter(candidate_id=candidate.id).count(),
            'message': 'Liked' if is_liked else 'Unliked'
        }, status=status.HTTP_200_OK if not is_liked else status.HTTP_201_CREATED)

class CandidateCommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        candidate_id = self.kwargs['pk']
        return Comment.objects.filter(
            Q(story__candidate_id=candidate_id) | Q(candidate_id=candidate_id)
        ).order_by('-created_at')

    def perform_create(self, serializer):
        candidate = get_object_or_404(Candidate, id=self.kwargs['pk'])
        serializer.save(
            user=self.request.user,
            story=None,
            company=None,
            project=None,
            job=None,
            candidate=candidate
        )
        logger.info(f"Comment added on candidate {self.kwargs['pk']} by {self.request.user.id}")

class CandidateSaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        candidate = get_object_or_404(Candidate, pk=pk)
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            candidate_id=candidate.id,
            defaults={'item_type': 'candidate'}
        )
        if not created:
            saved_item.delete()
            logger.info(f"Candidate {pk} unsaved by {request.user.id}")
            return Response({'status': 'unsaved'}, status.HTTP_200_OK)
        logger.info(f"Candidate {pk} saved by {request.user.id}")
        return Response({'status': 'saved'}, status.HTTP_201_CREATED)


# Company Interactions
class CompanyLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        is_liked = Like.objects.filter(user=request.user, company_id=company.id).exists()
        return Response({'is_liked': is_liked})

    def post(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        like, created = Like.objects.get_or_create(user=request.user, company_id=company.id)
        if not created:
            like.delete()
            logger.info(f"Company {pk} unliked by {request.user.id}")
            return Response({"message": "Company unliked"}, status.HTTP_200_OK)
        logger.info(f"Company {pk} liked by {request.user.id}")
        return Response({"message": "Company liked"}, status.HTTP_201_CREATED)

class CompanyCommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        company = get_object_or_404(Company, id=self.kwargs['pk'])
        return Comment.objects.filter(Q(company=company) | Q(story__company=company)).order_by('-created_at')

    def perform_create(self, serializer):
        company = get_object_or_404(Company, id=self.kwargs['pk'])
        serializer.save(
            user=self.request.user,
            story=None,
            company=company,
            project=None,
            job=None,
            candidate=None
        )
        logger.info(f"Comment on company {self.kwargs['pk']} by {self.request.user.id}")



class CompanySaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user, company_id=company.id, defaults={'item_type': 'company'}
        )
        if not created:
            saved_item.delete()
            logger.info(f"Company {pk} unsaved")
            return Response({'status': 'unsaved'}, status.HTTP_200_OK)
        logger.info(f"Company {pk} saved")
        return Response({'status': 'saved'}, status.HTTP_201_CREATED)


# Project Interactions
class ProjectLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        is_liked = Like.objects.filter(user=request.user, project_id=project.id).exists()
        return Response({'is_liked': is_liked})

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        like = Like.objects.filter(user=request.user, project_id=project.id).first()
        if like:
            like.delete()
            logger.info(f"Project {pk} unliked")
            return Response({"message": "Project unliked"}, status.HTTP_200_OK)
        Like.objects.create(user=request.user, project_id=project.id)
        logger.info(f"Project {pk} liked")
        return Response({"message": "Project liked"}, status.HTTP_201_CREATED)


class ProjectCommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        project = get_object_or_404(Project, id=self.kwargs['pk'])
        if not project.company:
            return Comment.objects.none()
        return Comment.objects.filter(Q(project=project) | Q(story__project=project)).order_by('-created_at')

    def perform_create(self, serializer):
        project = get_object_or_404(Project, id=self.kwargs['pk'])
        if not project.company:
            raise serializers.ValidationError("Cannot comment on a project without a company")
        serializer.save(
            user=self.request.user,
            story=None,
            company=None,
            project=project,
            job=None,
            candidate=None
        )
        logger.info(f"Comment on project {self.kwargs['pk']}")

class ProjectSaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user, project_id=project.id, defaults={'item_type': 'project'}
        )
        if not created:
            saved_item.delete()
            logger.info(f"Project {pk} unsaved")
            return Response({'status': 'unsaved'}, status.HTTP_200_OK)
        logger.info(f"Project {pk} saved")
        return Response({'status': 'saved'}, status.HTTP_201_CREATED)


# Job Interactions
class JobLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        is_liked = Like.objects.filter(user=request.user, job_id=job.id).exists()
        return Response({'is_liked': is_liked})

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        like = Like.objects.filter(user=request.user, job_id=job.id).first()
        if like:
            like.delete()
            logger.info(f"Job {pk} unliked")
            return Response({"message": "Job unliked"}, status.HTTP_200_OK)
        Like.objects.create(user=request.user, job_id=job.id)
        logger.info(f"Job {pk} liked")
        return Response({"message": "Job liked"}, status.HTTP_201_CREATED)


class JobCommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        job = get_object_or_404(Job, id=self.kwargs['pk'])
        if not job.company:
            return Comment.objects.none()
        return Comment.objects.filter(Q(job=job) | Q(story__job=job)).order_by('-created_at')

    def perform_create(self, serializer):
        job = get_object_or_404(Job, id=self.kwargs['pk'])
        if not job.company:
            raise serializers.ValidationError("Cannot comment on a job without a company")
        serializer.save(
            user=self.request.user,
            story=None,
            company=None,
            project=None,
            job=job,
            candidate=None
        )
        logger.info(f"Comment on job {self.kwargs['pk']}")

class JobSaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user, job_id=job.id, defaults={'item_type': 'job'}
        )
        if not created:
            saved_item.delete()
            logger.info(f"Job {pk} unsaved")
            return Response({'status': 'unsaved'}, status.HTTP_200_OK)
        logger.info(f"Job {pk} saved")
        return Response({'status': 'saved'}, status.HTTP_201_CREATED)


# =============================
# LIST VIEWS WITH INTERACTIONS
# =============================

class AllSavedItemsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        return SavedItem.objects.none()  # Keep this to satisfy generics

    def list(self, request, *args, **kwargs):
        user = request.user
        saved_items = SavedItem.objects.filter(user=user).order_by('-created_at')

        # Extract IDs
        project_ids = [item.project_id for item in saved_items if item.item_type == 'project' and item.project_id]
        job_ids = [item.job_id for item in saved_items if item.item_type == 'job' and item.job_id]
        candidate_ids = [item.candidate_id for item in saved_items if item.item_type == 'candidate' and item.candidate_id]
        company_ids = [item.company_id for item in saved_items if item.item_type == 'company' and item.company_id]

        all_items = []

        # === Projects ===
        if project_ids:
            like_count_sq = Like.objects.filter(project_id=OuterRef('pk')).values('project_id').annotate(count=Count('id')).values('count')
            direct_comment_sq = Comment.objects.filter(project_id=OuterRef('pk')).values('project_id').annotate(count=Count('id')).values('count')
            story_comment_sq = Comment.objects.filter(story__project_id=OuterRef('pk')).values('story__project_id').annotate(count=Count('id')).values('count')

            projects = Project.objects.select_related('company').filter(id__in=project_ids).annotate(
                like_count=Coalesce(Subquery(like_count_sq), 0),
                comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
                is_liked=Exists(Like.objects.filter(project_id=OuterRef('pk'), user=user)),
                is_saved=Value(True, output_field=BooleanField())  # Always saved
            )

            all_items.extend([{'item_type': 'project', **data} for data in ProjectSerializer(projects, many=True, context={'request': request}).data])

        # === Jobs ===
        if job_ids:
            like_count_sq = Like.objects.filter(job_id=OuterRef('pk')).values('job_id').annotate(count=Count('id')).values('count')
            direct_comment_sq = Comment.objects.filter(job_id=OuterRef('pk')).values('job_id').annotate(count=Count('id')).values('count')
            story_comment_sq = Comment.objects.filter(story__job_id=OuterRef('pk')).values('story__job_id').annotate(count=Count('id')).values('count')

            jobs = Job.objects.select_related('company').filter(id__in=job_ids).annotate(
                like_count=Coalesce(Subquery(like_count_sq), 0),
                comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
                is_liked=Exists(Like.objects.filter(job_id=OuterRef('pk'), user=user)),
                is_saved=Value(True, output_field=BooleanField())
            )

            all_items.extend([{'item_type': 'job', **data} for data in JobSerializer(jobs, many=True, context={'request': request}).data])

        # === Candidates ===
        if candidate_ids:
            like_count_sq = Like.objects.filter(candidate_id=OuterRef('pk')).values('candidate_id').annotate(count=Count('id')).values('count')
            direct_comment_sq = Comment.objects.filter(candidate_id=OuterRef('pk')).values('candidate_id').annotate(count=Count('id')).values('count')
            story_comment_sq = Comment.objects.filter(story__candidate_id=OuterRef('pk')).values('story__candidate_id').annotate(count=Count('id')).values('count')

            candidates = Candidate.objects.filter(id__in=candidate_ids).annotate(
                like_count=Coalesce(Subquery(like_count_sq), 0),
                comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
                is_liked=Exists(Like.objects.filter(candidate_id=OuterRef('pk'), user=user)),
                is_saved=Value(True, output_field=BooleanField())
            )

            all_items.extend([{'item_type': 'candidate', **data} for data in CandidateSerializer(candidates, many=True, context={'request': request}).data])

        # === Companies ===
        if company_ids:
            like_count_sq = Like.objects.filter(company_id=OuterRef('pk')).values('company_id').annotate(count=Count('id')).values('count')
            direct_comment_sq = Comment.objects.filter(company_id=OuterRef('pk')).values('company_id').annotate(count=Count('id')).values('count')
            story_comment_sq = Comment.objects.filter(story__company_id=OuterRef('pk')).values('story__company_id').annotate(count=Count('id')).values('count')

            companies = Company.objects.filter(id__in=company_ids).annotate(
                like_count=Coalesce(Subquery(like_count_sq), 0),
                comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
                is_liked=Exists(Like.objects.filter(company_id=OuterRef('pk'), user=user)),
                is_saved=Value(True, output_field=BooleanField())
            )

            all_items.extend([{'item_type': 'company', **data} for data in CompanySerializer(companies, many=True, context={'request': request}).data])

        # Sort by created_at descending
        all_items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Pagination on the Python list
        page = self.paginate_queryset(all_items)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(all_items)

class CompanyListView(generics.ListAPIView):
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user

        like_count_sq = Like.objects.filter(
            company_id=OuterRef('pk')
        ).values('company_id').annotate(count=Count('id')).values('count')

        direct_comment_sq = Comment.objects.filter(
            company_id=OuterRef('pk')
        ).values('company_id').annotate(count=Count('id')).values('count')

        story_comment_sq = Comment.objects.filter(
            story__company_id=OuterRef('pk')
        ).values('story__company_id').annotate(count=Count('id')).values('count')

        return Company.objects.all().annotate(
            like_count=Coalesce(Subquery(like_count_sq), 0),
            comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
            is_liked=Exists(Like.objects.filter(company_id=OuterRef('pk'), user=user)),
            is_saved=Exists(SavedItem.objects.filter(company_id=OuterRef('pk'), user=user, item_type='company'))
        ).order_by('-created_at')


class ProjectListView(generics.ListAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user

        like_count_sq = Like.objects.filter(
            project_id=OuterRef('pk')
        ).values('project_id').annotate(count=Count('id')).values('count')

        direct_comment_sq = Comment.objects.filter(
            project_id=OuterRef('pk')
        ).values('project_id').annotate(count=Count('id')).values('count')

        story_comment_sq = Comment.objects.filter(
            story__project_id=OuterRef('pk')
        ).values('story__project_id').annotate(count=Count('id')).values('count')

        return Project.objects.select_related('company').all().annotate(
            like_count=Coalesce(Subquery(like_count_sq), 0),
            comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
            is_liked=Exists(Like.objects.filter(project_id=OuterRef('pk'), user=user)),
            is_saved=Exists(SavedItem.objects.filter(project_id=OuterRef('pk'), user=user, item_type='project'))
        ).order_by('-created_at')


class JobListView(generics.ListAPIView):
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user

        like_count_sq = Like.objects.filter(
            job_id=OuterRef('pk')
        ).values('job_id').annotate(count=Count('id')).values('count')

        direct_comment_sq = Comment.objects.filter(
            job_id=OuterRef('pk')
        ).values('job_id').annotate(count=Count('id')).values('count')

        story_comment_sq = Comment.objects.filter(
            story__job_id=OuterRef('pk')
        ).values('story__job_id').annotate(count=Count('id')).values('count')

        return Job.objects.select_related('company').all().annotate(
            like_count=Coalesce(Subquery(like_count_sq), 0),
            comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
            is_liked=Exists(Like.objects.filter(job_id=OuterRef('pk'), user=user)),
            is_saved=Exists(SavedItem.objects.filter(job_id=OuterRef('pk'), user=user, item_type='job'))
        ).order_by('-created_at')


class CandidateListView(generics.ListAPIView):
    serializer_class = CandidateSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user

        queryset = Candidate.objects.all()

        # Hide own candidate profile if the logged-in user is a candidate
        if hasattr(user, 'candidate_profile'):
            queryset = queryset.exclude(id=user.candidate_profile.id)

        like_count_sq = Like.objects.filter(
            candidate_id=OuterRef('pk')
        ).values('candidate_id').annotate(count=Count('id')).values('count')

        direct_comment_sq = Comment.objects.filter(
            candidate_id=OuterRef('pk')
        ).values('candidate_id').annotate(count=Count('id')).values('count')

        story_comment_sq = Comment.objects.filter(
            story__candidate_id=OuterRef('pk')
        ).values('story__candidate_id').annotate(count=Count('id')).values('count')

        return queryset.annotate(
            like_count=Coalesce(Subquery(like_count_sq), 0),
            comment_count=Coalesce(Subquery(direct_comment_sq), 0) + Coalesce(Subquery(story_comment_sq), 0),
            is_liked=Exists(Like.objects.filter(candidate_id=OuterRef('pk'), user=user)),
            is_saved=Exists(SavedItem.objects.filter(
                candidate_id=OuterRef('pk'),
                user=user,
                item_type='candidate'
            ))
        ).order_by('-created_at')

        
class UserStoriesView(generics.ListAPIView):
    """
    View to get all stories for a specific user
    """
    serializer_class = StorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_id = self.kwargs.get('user_id')
        return Story.objects.filter(user_id=user_id).order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'status': 'success',
            'count': len(serializer.data),
            'data': serializer.data
        })  # You'll need to create this serializer



