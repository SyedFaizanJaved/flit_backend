from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Exists, OuterRef

from .models import Story, Comment, SavedItem, Like
from .serializers import (
    LikeSerializer, 
    CommentSerializer, 
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

class AllSavedItemsView(APIView):
    """
    View to list all saved items (projects, jobs, candidates, companies) for the current user
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        # Get all saved items for the current user
        saved_items = SavedItem.objects.filter(user=request.user).order_by('-created_at')
        
        # Initialize response data
        response_data = {
            'projects': [],
            'jobs': [],
            'candidates': [],
            'companies': []
        }
        
        # Get IDs for each type
        project_ids = [item.project_id for item in saved_items if item.item_type == 'project' and item.project_id]
        job_ids = [item.job_id for item in saved_items if item.item_type == 'job' and item.job_id]
        candidate_ids = [item.candidate_id for item in saved_items if item.item_type == 'candidate' and item.candidate_id]
        company_ids = [item.company_id for item in saved_items if item.item_type == 'company' and item.company_id]
        
        # Fetch all items in bulk for better performance
        # Note: Removed is_active filter as it's not present in all models
        projects = Project.objects.filter(id__in=project_ids) if project_ids else []
        jobs = Job.objects.filter(id__in=job_ids) if job_ids else []
        candidates = Candidate.objects.filter(id__in=candidate_ids) if candidate_ids else []
        companies = Company.objects.filter(id__in=company_ids) if company_ids else []
        
        # Serialize each type of item
        project_serializer = ProjectSerializer(projects, many=True, context={'request': request})
        job_serializer = JobSerializer(jobs, many=True, context={'request': request})
        candidate_serializer = CandidateSerializer(candidates, many=True, context={'request': request})
        company_serializer = CompanySerializer(companies, many=True, context={'request': request})
        
        # Add to response data
        response_data.update({
            'projects': project_serializer.data,
            'jobs': job_serializer.data,
            'candidates': candidate_serializer.data,
            'companies': company_serializer.data
        })
        
        return Response(response_data)


class BaseInteractionView(APIView):
    """
    Base view for like/comment/save interactions
    """
    permission_classes = [IsAuthenticated]
    model = None  # Should be set by child classes
    
    def get_object(self, pk):
        # Check if the model has is_active field
        if hasattr(self.model, 'is_active'):
            return get_object_or_404(self.model, pk=pk, is_active=True)
        return get_object_or_404(self.model, pk=pk)
    

# Company Interaction Views
class CandidateLikeView(BaseInteractionView):
    model = Candidate
    
    def get(self, request, pk):
        """Check if the current user has liked the candidate"""
        candidate = self.get_object(pk)
        
        # Check if the current user has liked this candidate
        has_liked = Like.objects.filter(
            candidate_id=candidate.id,
            user=request.user
        ).exists()
        
        return Response({'has_liked': has_liked}, status=status.HTTP_200_OK)
    
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
            likes_count = Like.objects.filter(candidate_id=candidate.id).count()
            return Response(
                {'status': 'unliked', 'likes_count': likes_count},
                status=status.HTTP_200_OK
            )
        else:
            # Create new like
            Like.objects.create(
                candidate_id=candidate.id,
                user=request.user
            )
            likes_count = Like.objects.filter(candidate_id=candidate.id).count()
            return Response(
                {'status': 'liked', 'likes_count': likes_count},
                status=status.HTTP_201_CREATED
            )


class CandidateCommentListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating comments on a candidate's story.
    Creates a story for the candidate if one doesn't exist.
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        candidate_id = self.kwargs['pk']
        # Get the candidate
        candidate = get_object_or_404(Candidate, id=candidate_id)
        
        # Get or create a story for this candidate
        story, created = Story.objects.get_or_create(
            candidate=candidate,
            user_type='candidate',
            content_type='text',
            defaults={
                'user': self.request.user,  # Use the request user as the story author
                'text_content': f'Candidate: {candidate.user.get_full_name() or candidate.user.email}'
            }
        )
        
        return story.story_comments.all().order_by('-created_at')
    
    def perform_create(self, serializer):
        candidate_id = self.kwargs['pk']
        candidate = get_object_or_404(Candidate, id=candidate_id)
        
        # Get or create a story for this candidate
        story, created = Story.objects.get_or_create(
            candidate=candidate,
            user_type='candidate',
            content_type='text',
            defaults={
                'user': self.request.user,  # Use the request user as the story author
                'text_content': f'Candidate: {candidate.user.get_full_name() or candidate.user.email}'
            }
        )
        
        serializer.save(
            user=self.request.user,
            story=story,
            content=serializer.validated_data.get('content', '')
        )


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


class CompanyLikeView(BaseInteractionView):
    model = Company
    
    def get(self, request, pk):
        """Check if the current user has liked the company"""
        company = self.get_object(pk)
        
        is_liked = Like.objects.filter(
            user=request.user,
            company_id=company.id
        ).exists()
        
        return Response({'is_liked': is_liked})
    
    def post(self, request, pk):
        """Like or unlike the company"""
        company = self.get_object(pk)
        
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
    model = Company
    serializer_class = CommentSerializer

    def get_queryset(self):
        company_id = self.kwargs['pk']
        return Comment.objects.filter(company_id=company_id).order_by('-created_at')

    def perform_create(self, serializer):
        company_id = self.kwargs['pk']
        serializer.save(
            user=self.request.user,
            company_id=company_id
        )


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
        
        like, created = Like.objects.get_or_create(
            user=request.user,
            project_id=project.id,
            defaults={'project_id': project.id}
        )
        
        if not created:
            like.delete()
            return Response(
                {"message": "Project unliked successfully"}, 
                status=status.HTTP_200_OK
            )
            
        return Response(
            {"message": "Project liked successfully"}, 
            status=status.HTTP_201_CREATED
        )


class ProjectCommentListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating comments on a project's story.
    Creates a story for the project's company if one doesn't exist.
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        project_id = self.kwargs['pk']
        # Get the project and its company
        project = get_object_or_404(Project, id=project_id)
        if not project.company:
            return Comment.objects.none()
            
        # Get or create a story for this company
        story, created = Story.objects.get_or_create(
            company=project.company,
            user_type='employer',
            content_type='text',
            defaults={
                'user': self.request.user,  # Use the request user as the story author
                'text_content': f'Project: {project.title}'
            }
        )
        
        return story.story_comments.all().order_by('-created_at')

    def perform_create(self, serializer):
        project_id = self.kwargs['pk']
        project = get_object_or_404(Project, id=project_id)
        
        if not project.company:
            raise ValidationError("Cannot comment on a project without a company")
            
        # Get or create a story for this company
        story, created = Story.objects.get_or_create(
            company=project.company,
            user_type='employer',
            content_type='text',
            defaults={
                'user': self.request.user,  # Use the request user as the story author
                'text_content': f'Project: {project.title}'
            }
        )
        
        serializer.save(
            user=self.request.user,
            story=story,
            content=serializer.validated_data.get('content', '')
        )

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
        
        like, created = Like.objects.get_or_create(
            user=request.user,
            job_id=job.id,
            defaults={'job_id': job.id}
        )
        
        if not created:
            like.delete()
            return Response(
                {"message": "Job unliked successfully"}, 
                status=status.HTTP_200_OK
            )
            
        return Response(
            {"message": "Job liked successfully"}, 
            status=status.HTTP_201_CREATED
        )


class JobCommentListCreateView(generics.ListCreateAPIView):
    """
    View for listing and creating comments on a job's story.
    Creates a story for the job's company if one doesn't exist.
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        job_id = self.kwargs['pk']
        # Get the job and its company
        job = get_object_or_404(Job, id=job_id)
        if not job.company:
            return Comment.objects.none()
            
        # Get or create a story for this company
        story, created = Story.objects.get_or_create(
            company=job.company,
            user_type='employer',
            content_type='text',
            defaults={
                'user': self.request.user,  # Use the request user as the story author
                'text_content': f'Job: {job.title}'
            }
        )
        
        return story.story_comments.all().order_by('-created_at')

    def perform_create(self, serializer):
        job_id = self.kwargs['pk']
        job = get_object_or_404(Job, id=job_id)
        
        if not job.company:
            raise ValidationError("Cannot comment on a job without a company")
            
        # Get or create a story for this company
        story, created = Story.objects.get_or_create(
            company=job.company,
            user_type='employer',
            content_type='text',
            defaults={
                'user': self.request.user,  # Use the request user as the story author
                'text_content': f'Job: {job.title}'
            }
        )
        
        serializer.save(
            user=self.request.user,
            story=story,
            content=serializer.validated_data.get('content', '')
        )

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
        # Start with all objects
        queryset = self.model.objects.all()
        
        # Filter by is_active if the field exists
        if hasattr(self.model, 'is_active'):
            queryset = queryset.filter(is_active=True)
        
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
                .values('count')
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
        from django.db.models.functions import Coalesce
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
            comment_count_subquery = (
                Comment.objects.filter(
                    story__candidate_id=OuterRef(pk_field)
                ).values('story__candidate_id')
                .annotate(count=Count('id'))
                .values('count')[:1]
            )
        else:
            # For models that don't have direct comment relationships, return 0
            comment_count_subquery = Comment.objects.none()
        
        # Annotate the queryset with counts and user-specific flags
        queryset = queryset.annotate(
            like_count=Coalesce(Subquery(like_count_subquery, output_field=IntegerField()), 0),
            comment_count=Coalesce(Subquery(comment_count_subquery, output_field=IntegerField()), 0),
            is_liked=Exists(user_likes),
            is_saved=Exists(user_saved)
        )
        
        return queryset


class CompanyListView(BaseListView):
    model = Company
    serializer_class = CompanySerializer

class ProjectListView(BaseListView):
    model = Project
    serializer_class = ProjectSerializer

class CandidateListView(BaseListView):
    model = Candidate
    serializer_class = CandidateSerializer

class JobListView(BaseListView):
    model = Job
    serializer_class = JobSerializer  # You'll need to create this serializer
