from rest_framework import generics, status, serializers
from rest_framework.pagination import PageNumberPagination
from utils.pagination import CustomPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Exists, OuterRef, Case, When, Value, BooleanField, IntegerField
from django.db.models.functions import Coalesce
from stories.models import Like, Comment, SavedItem
from .models import Story, Comment, SavedItem, Like
from .serializers import (
    LikeSerializer, 
    CommentSerializer, 
    StorySerializer,
    SavedItemSerializer
)
from companies.models import Company
from projects.models import Project
from jobs.models import Job
from candidates.models import Candidate
from .serializers_company_project_job import (
    CompanySerializer,
    ProjectSerializer,
    JobSerializer,
    CandidateSerializer
)
from .serializers_company_project_job import (
    CompanySerializer,
    ProjectSerializer,
    JobSerializer,
    CandidateSerializer
)

# Import the models
from companies.models import Company
from projects.models import Project
from jobs.models import Job
from candidates.models import Candidate

class AllSavedItemsView(generics.ListAPIView):
    """
    View to list all saved items (projects, jobs, candidates, companies) for the current user
    with pagination support
    """
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        # Return empty queryset since we're handling pagination manually
        return SavedItem.objects.none()
    
    def list(self, request, *args, **kwargs):
        # Get all saved items for the current user
        saved_items = SavedItem.objects.filter(user=request.user).order_by('-created_at')
        
        # Get IDs for each type
        project_ids = [item.project_id for item in saved_items if item.item_type == 'project' and item.project_id]
        job_ids = [item.job_id for item in saved_items if item.item_type == 'job' and item.job_id]
        candidate_ids = [item.candidate_id for item in saved_items if item.item_type == 'candidate' and item.candidate_id]
        company_ids = [item.company_id for item in saved_items if item.item_type == 'company' and item.company_id]
        
        # Fetch all items in bulk for better performance
        all_items = []
        
        # Add projects
        if project_ids:
            projects = Project.objects.filter(id__in=project_ids)
            project_serializer = ProjectSerializer(projects, many=True, context={'request': request})
            all_items.extend([
                {**item, 'item_type': 'project'} 
                for item in project_serializer.data
            ])
        
        # Add jobs
        if job_ids:
            jobs = Job.objects.filter(id__in=job_ids)
            job_serializer = JobSerializer(jobs, many=True, context={'request': request})
            all_items.extend([
                {**item, 'item_type': 'job'} 
                for item in job_serializer.data
            ])
        
        # Add candidates
        if candidate_ids:
            candidates = Candidate.objects.filter(id__in=candidate_ids)
            candidate_serializer = CandidateSerializer(candidates, many=True, context={'request': request})
            all_items.extend([
                {**item, 'item_type': 'candidate'} 
                for item in candidate_serializer.data
            ])
        
        # Add companies
        if company_ids:
            companies = Company.objects.filter(id__in=company_ids)
            company_serializer = CompanySerializer(companies, many=True, context={'request': request})
            all_items.extend([
                {**item, 'item_type': 'company'} 
                for item in company_serializer.data
            ])
        
        # Sort all items by creation date (newest first)
        all_items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Paginate the results
        page = self.paginate_queryset(all_items)
        if page is not None:
            return self.get_paginated_response(page)
            
        return Response(all_items)


class BaseInteractionView(APIView):
    """
    Base view for like/comment/save interactions
    """
    permission_classes = [IsAuthenticated]
    model = None  # Should be set by child classes
    
    def get_object(self, pk):
        # Get object by primary key without checking is_active
        return get_object_or_404(self.model, pk=pk)
    

# Company Interaction Views
class CandidateLikeView(BaseInteractionView):
    model = Candidate
    
    def get(self, request, pk):
        """Check if the current user has liked the candidate and get like count"""
        candidate = self.get_object(pk)
        
        # Get like count and check if current user has liked
        likes = Like.objects.filter(candidate_id=candidate.id)
        likes_count = likes.count()
        is_liked = likes.filter(user=request.user).exists()
        
        return Response({
            'is_liked': is_liked,
            'like_count': likes_count
        }, status=status.HTTP_200_OK)
    
    def post(self, request, pk):
        """Like or unlike the candidate"""
        candidate = self.get_object(pk)
        
        # Check if the like already exists
        like = Like.objects.filter(
            candidate_id=candidate.id,
            user=request.user
        ).first()
        
        if like:
            # Unlike if the like already exists
            like.delete()
            is_liked = False
        else:
            # Create new like
            Like.objects.create(
                candidate_id=candidate.id,
                user=request.user
            )
            is_liked = True
            
        # Get updated like count
        likes_count = Like.objects.filter(candidate_id=candidate.id).count()
        
        return Response({
            'is_liked': is_liked,
            'like_count': likes_count,
            'message': 'Candidate liked successfully' if is_liked else 'Candidate unliked successfully'
        }, status=status.HTTP_200_OK if like else status.HTTP_201_CREATED)


class CandidateCommentListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating comments on a candidate.
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        candidate_id = self.kwargs['pk']
        # Return all comments for this candidate, regardless of story association
        return Comment.objects.filter(
            Q(story__candidate_id=candidate_id) | 
            Q(candidate_id=candidate_id)
        ).order_by('-created_at')
        
    def create(self, request, *args, **kwargs):
        candidate_id = self.kwargs['pk']
        
        # First get the current count before creating the comment
        current_count = Comment.objects.filter(
            Q(story__candidate_id=candidate_id) | 
            Q(candidate_id=candidate_id)
        ).count()
        
        # Create the comment
        response = super().create(request, *args, **kwargs)
        
        # The new count should be current_count + 1
        response.data['comment_count'] = current_count + 1
        
        # Also update the candidate's comment count if needed
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            if hasattr(candidate, 'comment_count'):
                candidate.comment_count = F('comment_count') + 1
                candidate.save(update_fields=['comment_count'])
        except Candidate.DoesNotExist:
            pass
            
        return response
    
    def perform_create(self, serializer):
        candidate_id = self.kwargs['pk']
        candidate = get_object_or_404(Candidate, id=candidate_id)
        
        # Ensure no story is created when making a comment
        if 'story' in serializer.validated_data:
            del serializer.validated_data['story']
            
        # Save comment without any story association
        comment = serializer.save(
            user=self.request.user,
            story=None,  # Explicitly set to None
            candidate=candidate,  # Associate directly with the candidate
            content=serializer.validated_data.get('content', '')
        )
        
        # Double-check that no story was created
        if hasattr(comment, 'story') and comment.story is not None:
            # If a story was somehow created, delete it
            story = comment.story
            comment.story = None
            comment.save()
            story.delete()


class CandidateSaveView(APIView):
    """
    View for saving/unsaving a candidate
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        candidate = get_object_or_404(Candidate, pk=pk)
        
        # Check if already saved
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            candidate_id=candidate.id,
            defaults={
                'user': request.user,
                'candidate_id': candidate.id,
                'item_type': 'candidate'
            }
        )
        
        if not created:
            # If already saved, unsave it
            saved_item.delete()
            return Response(
                {'status': 'unsaved'},
                status=status.HTTP_200_OK
            )
            
        return Response(
            {'status': 'saved'},
            status=status.HTTP_201_CREATED
        )


class CompanyLikeView(APIView):
    """
    View for liking/unliking a company
    """
    permission_classes = [IsAuthenticated]
    
    def get_company(self, pk):
        try:
            return Company.objects.get(pk=pk)
        except Company.DoesNotExist:
            raise Http404("Company not found")
    
    def get(self, request, pk):
        """Check if the current user has liked the company"""
        company = self.get_company(pk)
        
        is_liked = Like.objects.filter(
            user=request.user,
            company_id=company.id
        ).exists()
        
        return Response({'is_liked': is_liked})
    
    def post(self, request, pk):
        """Like or unlike the company"""
        company = self.get_company(pk)
        
        like, created = Like.objects.get_or_create(
            user=request.user,
            company_id=company.id,
            defaults={'company_id': company.id}
        )
        
        if not created:
            like.delete()
            return Response(
                {"message": "Company unliked successfully"}, 
                status=status.HTTP_200_OK
            )
            
        return Response(
            {"message": "Company liked successfully"}, 
            status=status.HTTP_201_CREATED
        )


class CompanyCommentListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating comments on a company.
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        company_id = self.kwargs['pk']
        company = get_object_or_404(Company, id=company_id)
        
        # Return all comments for this company, both direct and via stories
        return Comment.objects.filter(
            Q(company=company) | Q(story__company=company)
        ).order_by('-created_at')
    
    def create(self, request, *args, **kwargs):
        company_id = self.kwargs['pk']
        company = get_object_or_404(Company, id=company_id)
        
        # Get the current count of comments for this company
        current_count = Comment.objects.filter(
            Q(company=company) | Q(story__company=company)
        ).count()
        
        # Create the comment
        response = super().create(request, *args, **kwargs)
        
        # The new count should be current_count + 1
        response.data['comment_count'] = current_count + 1
        
        # Also update the company's comment count if the field exists
        if hasattr(company, 'comment_count'):
            company.comment_count = F('comment_count') + 1
            company.save(update_fields=['comment_count'])
            
        return response
    
    def perform_create(self, serializer):
        company_id = self.kwargs['pk']
        company = get_object_or_404(Company, id=company_id)
        
        # Ensure no story is created when making a comment
        if 'story' in serializer.validated_data:
            del serializer.validated_data['story']
        
        # Save comment without any story association
        comment = serializer.save(
            user=self.request.user,
            story=None,  # Explicitly set to None
            company=company,
            content=serializer.validated_data.get('content', '')
        )
        
        # Double-check that no story was created
        if hasattr(comment, 'story') and comment.story is not None:
            # If a story was somehow created, delete it
            story = comment.story
            comment.story = None
            comment.save()
            story.delete()


class CompanySaveView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        
        # Check if already saved
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            company_id=company.id,
            defaults={
                'user': request.user,
                'company_id': company.id,
                'item_type': 'company'
            }
        )
        
        if not created:
            # If already saved, unsave it
            saved_item.delete()
            return Response(
                {'status': 'unsaved'},
                status=status.HTTP_200_OK
            )
            
        return Response(
            {'status': 'saved'},
            status=status.HTTP_201_CREATED
        )


# Project Interaction Views (similar to Company)
class ProjectLikeView(BaseInteractionView):
    model = Project
    
    def get(self, request, pk):
        """Check if the current user has liked the project"""
        project = self.get_object(pk)
        
        is_liked = Like.objects.filter(
            user=request.user,
            project_id=project.id
        ).exists()
        
        return Response({'is_liked': is_liked})
    
    def post(self, request, pk):
        """Like or unlike the project"""
        project = self.get_object(pk)
        
        # First check if the like exists
        like = Like.objects.filter(
            user=request.user,
            project_id=project.id
        ).first()
        
        if like:
            # Unlike if already liked
            like.delete()
            return Response(
                {"message": "Project unliked successfully"}, 
                status=status.HTTP_200_OK
            )
        else:
            # Create new like
            Like.objects.create(
                user=request.user,
                project_id=project.id
            )
            return Response(
                {"message": "Project liked successfully"}, 
                status=status.HTTP_201_CREATED
            )


class ProjectCommentListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating comments on a project.
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        project_id = self.kwargs['pk']
        project = get_object_or_404(Project, id=project_id)
        
        if not project.company:
            return Response(
                {"error": "Cannot comment on a project without a company"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the current count of comments for this project (both direct and via story)
        current_count = Comment.objects.filter(
            Q(project=project) | Q(story__project=project)
        ).count()
        
        # Create the comment
        response = super().create(request, *args, **kwargs)
        
        # The new count should be current_count + 1
        response.data['comment_count'] = current_count + 1
        
        # Also update the project's comment count if the field exists
        if hasattr(project, 'comment_count'):
            project.comment_count = F('comment_count') + 1
            project.save(update_fields=['comment_count'])
            
        return response
    
    def get_queryset(self):
        project_id = self.kwargs['pk']
        project = get_object_or_404(Project, id=project_id)
        
        if not project.company:
            return Comment.objects.none()
            
        # Return both direct comments and those associated with stories for this project
        return Comment.objects.filter(
            Q(project=project) | Q(story__project=project)
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        project_id = self.kwargs['pk']
        project = get_object_or_404(Project, id=project_id)
        
        if not project.company:
            raise serializers.ValidationError("Cannot comment on a project without a company")
        
        # Ensure no story is created when making a comment
        if 'story' in serializer.validated_data:
            del serializer.validated_data['story']
            
        # Save the comment without any story association
        comment = serializer.save(
            user=self.request.user,
            story=None,  # Explicitly set to None
            project=project,
            content=serializer.validated_data.get('content', '')
        )
        
        # Double-check that no story was created
        if hasattr(comment, 'story') and comment.story is not None:
            # If a story was somehow created, delete it
            story = comment.story
            comment.story = None
            comment.save()
            story.delete()

class ProjectSaveView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Check if the project is saved by the current user"""
        is_saved = SavedItem.objects.filter(
            user=request.user,
            project_id=pk,
            item_type='project'
        ).exists()
        
        return Response({
            'is_saved': is_saved,
            'project_id': pk
        })
    
    def post(self, request, pk):
        """Save or unsave the project"""
        project = get_object_or_404(Project, pk=pk)
        
        # Check if already saved
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            project_id=project.id,
            defaults={
                'user': request.user,
                'project_id': project.id,
                'item_type': 'project'
            }
        )
        
        if not created:
            # If already saved, unsave it
            saved_item.delete()
            return Response(
                {'status': 'unsaved'},
                status=status.HTTP_200_OK
            )
            
        return Response(
            {'status': 'saved'},
            status=status.HTTP_201_CREATED
        )
        project = self.get_object(pk)
        content_type = self.get_content_type()
        
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=project.id,
            defaults={'item_type': 'project'}
        )
        
        if not created:
            saved_item.delete()
            return Response({"detail": "Removed from saved"}, status=status.HTTP_200_OK)
            
        return Response({"detail": "Saved"}, status=status.HTTP_201_CREATED)


# Job Interaction Views (similar to Company)
class JobLikeView(BaseInteractionView):
    model = Job
    
    def get(self, request, pk):
        """Check if the current user has liked the job"""
        job = self.get_object(pk)
        
        is_liked = Like.objects.filter(
            user=request.user,
            job_id=job.id
        ).exists()
        
        return Response({'is_liked': is_liked})
    
    def post(self, request, pk):
        """Like or unlike the job"""
        job = self.get_object(pk)
        
        # First check if the like exists
        like = Like.objects.filter(
            user=request.user,
            job_id=job.id
        ).first()
        
        if like:
            # Unlike if already liked
            like.delete()
            return Response(
                {"message": "Job unliked successfully"}, 
                status=status.HTTP_200_OK
            )
        else:
            # Create new like
            Like.objects.create(
                user=request.user,
                job_id=job.id
            )
            return Response(
                {"message": "Job liked successfully"}, 
                status=status.HTTP_201_CREATED
            )


class JobCommentListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating comments on a job.
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        job_id = self.kwargs['pk']
        job = get_object_or_404(Job, id=job_id)
        
        if not job.company:
            return Response(
                {"error": "Cannot comment on a job without a company"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the current count of comments for this job (both direct and via story)
        current_count = Comment.objects.filter(
            Q(job=job) | Q(story__job=job)
        ).count()
        
        # Create the comment
        response = super().create(request, *args, **kwargs)
        
        # The new count should be current_count + 1
        response.data['comment_count'] = current_count + 1
        
        # Also update the job's comment count if the field exists
        if hasattr(job, 'comment_count'):
            job.comment_count = F('comment_count') + 1
            job.save(update_fields=['comment_count'])
            
        return response
    
    def get_queryset(self):
        job_id = self.kwargs['pk']
        job = get_object_or_404(Job, id=job_id)
        
        if not job.company:
            return Comment.objects.none()
            
        # Return both direct comments and those associated with stories for this job
        return Comment.objects.filter(
            Q(job=job) | Q(story__job=job)
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        job_id = self.kwargs['pk']
        job = get_object_or_404(Job, id=job_id)
        
        if not job.company:
            raise serializers.ValidationError("Cannot comment on a job without a company")
        
        # Ensure no story is created when making a comment
        if 'story' in serializer.validated_data:
            del serializer.validated_data['story']
            
        # Save comment without any story association
        comment = serializer.save(
            user=self.request.user,
            story=None,  # Explicitly set to None
            job=job,
            content=serializer.validated_data.get('content', '')
        )
        
        # Double-check that no story was created
        if hasattr(comment, 'story') and comment.story is not None:
            # If a story was somehow created, delete it
            story = comment.story
            comment.story = None
            comment.save()
            story.delete()

class JobSaveView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Check if the job is saved by the current user"""
        is_saved = SavedItem.objects.filter(
            user=request.user,
            job_id=pk,
            item_type='job'
        ).exists()
        
        return Response({
            'is_saved': is_saved,
            'job_id': pk
        })
    
    def post(self, request, pk):
        """Save or unsave the job"""
        job = get_object_or_404(Job, pk=pk)
        
        # Check if already saved
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            job_id=job.id,
            defaults={
                'user': request.user,
                'job_id': job.id,
                'item_type': 'job'
            }
        )
        
        if not created:
            # If already saved, unsave it
            saved_item.delete()
            return Response(
                {'status': 'unsaved'},
                status=status.HTTP_200_OK
            )
            
        return Response(
            {'status': 'saved'},
            status=status.HTTP_201_CREATED
        )


# List views with interaction data
class BaseListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Get the model name
        model_name = self.model._meta.model_name
        
        # Check if user is an employer
        if hasattr(self.request.user, 'employer_profile'):
            # For employers, only allow access to candidates
            if model_name != 'candidate':
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied({
                    'error': 'Access Denied',
                    'message': 'You are not authorized to view this content. Please log in as a candidate to access this feature.'
                })
        
        # For candidates or for candidate model when user is employer
        # Start with all objects, including inactive ones
        queryset = self.model.objects.all()
        
        # Get the primary key field name for the model
        pk_field = self.model._meta.pk.name
        
        # Subquery to count likes for each item
        from django.db.models import Subquery, OuterRef, Count, Exists, Q
        
        # Subquery to check if current user has liked each item
        # Determine the field name based on the model
        model_name = self.model._meta.model_name
        
        # For models that support likes (company, project, job, candidate)
        if model_name in ['company', 'project', 'job', 'candidate']:
            field_map = {
                'company': 'company_id',
                'project': 'project_id',
                'job': 'job_id',
                'candidate': 'candidate_id'
            }
            field_name = field_map[model_name]
            
            # Subquery to check if current user has liked each item
            user_likes = Like.objects.filter(
                **{field_name: OuterRef(pk_field)},
                user=self.request.user
            )
            
            # Subquery to get like count for each item
            like_count_subquery = (
                Like.objects.filter(
                    **{field_name: OuterRef(pk_field)}
                ).values(field_name)
                .annotate(count=Count('id'))
                .values('count')[:1]
            )
        else:
            # For models that don't support likes (like candidate), return empty querysets
            user_likes = Like.objects.none()
            like_count_subquery = Like.objects.none()
        
        # Subquery to check if current user has saved each item
        user_saved = SavedItem.objects.filter(
            item_type=model_name,
            **{f"{model_name}_id": OuterRef(pk_field)},
            user=self.request.user
        )
        
        # Get counts of likes and comments for each item
        from django.db.models.functions import Coalesce, Concat
        from django.db.models import Subquery, OuterRef, IntegerField
        
        # Like count subquery is now defined above based on model type
        
        # Subquery to count comments through Story model
        if model_name == 'company':
            comment_count_subquery = (
                Comment.objects.filter(
                    story__company_id=OuterRef(pk_field)
                ).values('story__company_id')
                .annotate(count=Count('id'))
                .values('count')[:1]
            )
        elif model_name == 'candidate':
            # For candidates, we need to count comments on the story associated with the candidate
            comment_count_subquery = (
                Comment.objects.filter(
                    story__candidate_id=OuterRef(pk_field)
                ).values('story__candidate_id')
                .annotate(count=Count('id'))
                .values('count')[:1]
            )
            
            # For candidates, also ensure we're using the correct field for likes
            like_count_subquery = (
                Like.objects.filter(
                    candidate_id=OuterRef(pk_field)
                ).values('candidate_id')
                .annotate(count=Count('id'))
                .values('count')[:1]
            )
        elif model_name == 'project':
            # For projects, we'll handle the comment count in the serializer
            # since the subquery with text matching is complex
            from django.db.models import Value, IntegerField
            comment_count_subquery = Subquery(
                Project.objects.filter(id=OuterRef('id'))
                .annotate(dummy=Value(0, output_field=IntegerField()))
                .values('dummy')[:1],
                output_field=IntegerField()
            )
        elif model_name == 'job':
            # For jobs, we'll handle the comment count in the serializer
            # since the subquery with text matching is complex
            from django.db.models import Value, IntegerField
            comment_count_subquery = Subquery(
                Job.objects.filter(id=OuterRef('id'))
                .annotate(dummy=Value(0, output_field=IntegerField()))
                .values('dummy')[:1],
                output_field=IntegerField()
            )
        else:
            # For models that don't have comment relationships, return 0
            comment_count_subquery = Comment.objects.none()
        
        # Annotate the queryset with counts and user-specific flags
        queryset = queryset.annotate(
            like_count=Coalesce(Subquery(like_count_subquery, output_field=IntegerField()), 0),
            comment_count=Coalesce(Subquery(comment_count_subquery, output_field=IntegerField()), 0),
            is_liked=Exists(user_likes),
            is_saved=Exists(user_saved)
        )
        
        return queryset


class CompanyListView(generics.ListAPIView):
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    
    def get_queryset(self):
        from django.db.models import Count, Exists, OuterRef, Q, Subquery, IntegerField, Case, When, Value, BooleanField
        from django.db.models.functions import Coalesce
        from stories.models import Like, Comment, SavedItem
        
        # Get all companies including inactive ones
        queryset = Company.objects.all()
        
        # Subquery to count likes for each company
        like_count_subquery = (
            Like.objects
            .filter(company_id=OuterRef('pk'))
            .values('company_id')
            .annotate(count=Count('id'))
            .values('count')[:1]
        )
        
        # Subquery to count comments for each company
        comment_count_subquery = (
            Comment.objects
            .filter(company_id=OuterRef('pk'))
            .values('company_id')
            .annotate(count=Count('id'))
            .values('count')[:1]
        )
        
        # Check if current user has liked/saved each company
        if self.request.user.is_authenticated:
            # Subquery for is_liked
            is_liked_subquery = Like.objects.filter(
                company_id=OuterRef('pk'),
                user=self.request.user
            )
            
            # Subquery for is_saved
            is_saved_subquery = SavedItem.objects.filter(
                item_type='company',
                company_id=OuterRef('pk'),
                user=self.request.user
            )
            
            # Annotate the queryset with like, comment counts and user-specific flags
            queryset = queryset.annotate(
                like_count=Coalesce(Subquery(like_count_subquery, output_field=IntegerField()), 0),
                comment_count=Coalesce(Subquery(comment_count_subquery, output_field=IntegerField()), 0),
                is_liked=Exists(is_liked_subquery),
                is_saved=Exists(is_saved_subquery)
            )
        else:
            # For unauthenticated users, just include the counts
            queryset = queryset.annotate(
                like_count=Coalesce(Subquery(like_count_subquery, output_field=IntegerField()), 0),
                comment_count=Coalesce(Subquery(comment_count_subquery, output_field=IntegerField()), 0),
                is_liked=Value(False, output_field=BooleanField()),
                is_saved=Value(False, output_field=BooleanField())
            )
        
        # Order by creation date (newest first)
        return queryset.order_by('-created_at')

class ProjectListView(generics.ListAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    page_size = 20
    
    def get_queryset(self):
        # Base queryset with company prefetch
        return Project.objects.select_related('company').all()
    
    def list(self, request, *args, **kwargs):
        # Get the base queryset
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get project IDs before pagination for efficient querying
        project_ids = list(queryset.values_list('id', flat=True))
        
        # Get all like counts in a single query
        like_counts = {}
        if project_ids:
            like_counts = dict(Like.objects
                .filter(project_id__in=project_ids)
                .values('project_id')
                .annotate(count=Count('id'))
                .values_list('project_id', 'count')
            )
        
        # Get user's liked and saved status in single queries if user is authenticated
        user_liked = set()
        user_saved = set()
        
        if request.user.is_authenticated and project_ids:
            user_id = request.user.id
            user_liked = set(Like.objects.filter(
                project_id__in=project_ids,
                user_id=user_id
            ).values_list('project_id', flat=True))
            
            user_saved = set(SavedItem.objects.filter(
                item_type='project',
                project_id__in=project_ids,
                user_id=user_id
            ).values_list('project_id', flat=True))
            
        # Annotate the queryset with all the data
        queryset = queryset.annotate(
            like_count=Case(
                *[When(pk=pid, then=Value(count)) for pid, count in like_counts.items()],
                default=Value(0),
                output_field=IntegerField()
            ),
            is_liked=Case(
                *[When(pk=pid, then=Value(True)) for pid in user_liked],
                default=Value(False),
                output_field=BooleanField()
            ) if request.user.is_authenticated else Value(False, output_field=BooleanField()),
            is_saved=Case(
                *[When(pk=pid, then=Value(True)) for pid in user_saved],
                default=Value(False),
                output_field=BooleanField()
            ) if request.user.is_authenticated else Value(False, output_field=BooleanField())
        )
        
        # Apply pagination after annotation
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response_data = {
                'count': self.paginator.page.paginator.count,
                'next': self.paginator.get_next_link(),
                'previous': self.paginator.get_previous_link(),
                'total_pages': self.paginator.page.paginator.num_pages,
                'current_page': self.paginator.page.number,
                'results': serializer.data
            }
            return Response(response_data)
            
            # Annotate the page queryset with all the data
            page = list(page)  # Convert to list to maintain order
            for project in page:
                project.like_count = like_counts.get(project.id, 0)
                project.is_liked = project.id in user_liked if request.user.is_authenticated else False
                project.is_saved = project.id in user_saved if request.user.is_authenticated else False
            
            # Serialize the page
            serializer = self.get_serializer(page, many=True)
            
            # Get pagination data
            paginator = self.paginator
            response_data = {
                'status': 'success',
                'count': paginator.page.paginator.count,
                'total_pages': paginator.page.paginator.num_pages,
                'current_page': paginator.page.number,
                'results': serializer.data
            }
            
            return Response(response_data)
        
        # Fallback to non-paginated response if pagination is not applied
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'results': serializer.data
        })

class JobListView(generics.ListAPIView):
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    page_size = 20
    
    def get_queryset(self):
        # Base queryset with company prefetch
        return Job.objects.select_related('company').all()
    
    def list(self, request, *args, **kwargs):
        # Get the base queryset
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get job IDs before pagination for efficient querying
        job_ids = list(queryset.values_list('id', flat=True))
        
        # Get all like counts in a single query
        like_counts = {}
        if job_ids:
            like_counts = dict(Like.objects
                .filter(job_id__in=job_ids)
                .values('job_id')
                .annotate(count=Count('id'))
                .values_list('job_id', 'count')
            )
        
        # Get user's liked and saved status in single queries if user is authenticated
        user_liked = set()
        user_saved = set()
        
        if request.user.is_authenticated and job_ids:
            user_id = request.user.id
            user_liked = set(Like.objects.filter(
                job_id__in=job_ids,
                user_id=user_id
            ).values_list('job_id', flat=True))
            
            user_saved = set(SavedItem.objects.filter(
                item_type='job',
                job_id__in=job_ids,
                user_id=user_id
            ).values_list('job_id', flat=True))
        
        # Annotate the queryset with all the data
        queryset = queryset.annotate(
            like_count=Case(
                *[When(pk=jid, then=Value(count)) for jid, count in like_counts.items()],
                default=Value(0),
                output_field=IntegerField()
            ),
            is_liked=Case(
                *[When(pk=jid, then=Value(True)) for jid in user_liked],
                default=Value(False),
                output_field=BooleanField()
            ) if request.user.is_authenticated else Value(False, output_field=BooleanField()),
            is_saved=Case(
                *[When(pk=jid, then=Value(True)) for jid in user_saved],
                default=Value(False),
                output_field=BooleanField()
            ) if request.user.is_authenticated else Value(False, output_field=BooleanField())
        )
        
        # Apply pagination after annotation
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response_data = {
                'count': self.paginator.page.paginator.count,
                'next': self.paginator.get_next_link(),
                'previous': self.paginator.get_previous_link(),
                'total_pages': self.paginator.page.paginator.num_pages,
                'current_page': self.paginator.page.number,
                'results': serializer.data
            }
            return Response(response_data)
            
        # Fallback to non-paginated response if pagination is not applied
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'results': serializer.data
        })
        #         return Response({
        #             'count': count,
        #             'results': serializer.data
        #         })

class CandidateListView(BaseListView):
    model = Candidate
    serializer_class = CandidateSerializer


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



