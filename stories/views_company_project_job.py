from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Exists, OuterRef
from django.contrib.contenttypes.models import ContentType

from .models import Like, Comment, SavedItem
from .serializers import (
    LikeSerializer, 
    CommentSerializer, 
    SavedItemSerializer
)
from .serializers_company_project_job import (
    CompanySerializer,
    ProjectSerializer,
    JobSerializer
)

# Import the models
from companies.models import Company
from projects.models import Project
from jobs.models import Job

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
    
    def get_content_type(self):
        return ContentType.objects.get_for_model(self.model)


# Company Interaction Views
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


class CompanyCommentListCreateView(generics.ListCreateAPIView, BaseInteractionView):
    model = Company
    serializer_class = CommentSerializer
    
    def get_queryset(self):
        company = self.get_object(self.kwargs['pk'])
        content_type = self.get_content_type()
        return Comment.objects.filter(
            content_type=content_type,
            object_id=company.id
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        company = self.get_object(self.kwargs['pk'])
        content_type = self.get_content_type()
        serializer.save(
            user=self.request.user,
            content_type=content_type,
            object_id=company.id
        )


class CompanySaveView(BaseInteractionView):
    model = Company
    
    def post(self, request, pk):
        company = self.get_object(pk)
        content_type = self.get_content_type()
        
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=company.id,
            defaults={'item_type': 'company'}
        )
        
        if not created:
            saved_item.delete()
            return Response({"detail": "Removed from saved"}, status=status.HTTP_200_OK)
            
        return Response({"detail": "Saved"}, status=status.HTTP_201_CREATED)


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


class ProjectCommentListCreateView(CompanyCommentListCreateView):
    model = Project

class ProjectSaveView(CompanySaveView):
    model = Project
    
    def post(self, request, pk):
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


class JobCommentListCreateView(CompanyCommentListCreateView):
    model = Job

class JobSaveView(CompanySaveView):
    model = Job
    
    def post(self, request, pk):
        job = self.get_object(pk)
        content_type = self.get_content_type()
        
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=job.id,
            defaults={'item_type': 'job'}
        )
        
        if not created:
            saved_item.delete()
            return Response({"detail": "Removed from saved"}, status=status.HTTP_200_OK)
            
        return Response({"detail": "Saved"}, status=status.HTTP_201_CREATED)


# List views with interaction data
class BaseListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Start with all objects
        queryset = self.model.objects.all()
        
        # Filter by is_active if the field exists
        if hasattr(self.model, 'is_active'):
            queryset = queryset.filter(is_active=True)
        
        # Get the content type for the current model
        content_type = ContentType.objects.get_for_model(self.model)
        
        # Get the primary key field name for the model
        pk_field = self.model._meta.pk.name
        
        # Subquery to count likes for each item
        from django.db.models import Subquery, OuterRef, Count, Exists, Q
        
        # Subquery to check if current user has liked each item
        # Determine the field name based on the model
        field_map = {
            'company': 'company_id',
            'project': 'project_id',
            'job': 'job_id'
        }
        field_name = field_map.get(self.model._meta.model_name)
        
        user_likes = Like.objects.filter(
            **{field_name: OuterRef(pk_field)},
            user=self.request.user
        )
        
        # Subquery to check if current user has saved each item
        user_saved = SavedItem.objects.filter(
            item_type=self.model._meta.model_name,
            **{f"{self.model._meta.model_name}_id": OuterRef(pk_field)},
            user=self.request.user
        )
        
        # Get counts of likes and comments for each item
        from django.db.models.functions import Coalesce
        from django.db.models import Subquery, OuterRef, IntegerField
        
        # Subquery to count likes
        like_count_subquery = (
            Like.objects.filter(
                **{field_name: OuterRef(pk_field)}
            ).values(field_name)
            .annotate(count=Count('id'))
            .values('count')
        )
        
        # Subquery to count comments
        comment_count_subquery = (
            Comment.objects.filter(
                **{field_name: OuterRef(pk_field)}
            ).values(field_name)
            .annotate(count=Count('id'))
            .values('count')[:1]
        )
        
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
    serializer_class = CompanySerializer  # You'll need to create this serializer

class ProjectListView(BaseListView):
    model = Project
    serializer_class = ProjectSerializer  # You'll need to create this serializer

class JobListView(BaseListView):
    model = Job
    serializer_class = JobSerializer  # You'll need to create this serializer
