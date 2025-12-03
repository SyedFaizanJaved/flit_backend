from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, generics, permissions, serializers
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Story, Like, Comment, SavedItem
from .serializers import StorySerializer, LikeSerializer, CommentSerializer, SavedItemSerializer


class StoryListCreateView(generics.ListCreateAPIView):
    """
    View to list all stories or create a new story
    """
    queryset = Story.objects.all()
    serializer_class = StorySerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        """
        Add request context to serializer
        """
        context = super().get_serializer_context()
        context.update({
            'request': self.request
        })
        return context

    def perform_create(self, serializer):
        user = self.request.user
        user_type = None
        company_id = None
        candidate_id = None
        
        # Determine user_type based on user's profile
        if hasattr(user, 'employer_profile'):
            user_type = 'employer'
            # Get company from employer profile if not provided
            company_id = self.request.data.get('company') or (
                user.employer_profile.company.id if user.employer_profile.company else None
            )
        elif hasattr(user, 'candidate_profile'):
            user_type = 'candidate'
            candidate_id = self.request.data.get('candidate') or user.candidate_profile.id
        else:
            raise serializers.ValidationError({
                'user': 'User must be either an employer or a candidate to create a story.'
            })
        
        # Validate required fields based on user type
        if user_type == 'employer' and not company_id:
            raise serializers.ValidationError({
                'company': 'Company is required for employer stories. Please ensure your employer profile has a company associated.'
            })
            
        if user_type == 'candidate' and not candidate_id:
            raise serializers.ValidationError({
                'candidate': 'Candidate profile is required for candidate stories'
            })
        
        # Prepare data for saving
        data = {
            'user': user,
            'user_type': user_type,
        }
        
        # Only set company_id if user is employer
        if user_type == 'employer' and company_id:
            data['company_id'] = company_id
        # Only set candidate_id if user is candidate
        elif user_type == 'candidate' and candidate_id:
            data['candidate_id'] = candidate_id
        
        # Save the story
        serializer.save(**data)

    def get_queryset(self):
        queryset = Story.objects.filter(is_active=True)
        request = self.request
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)

        # Hide stories older than 24 hours
        queryset = queryset.filter(created_at__gte=twenty_four_hours_ago)
        
        # Filter by user type if provided
        user_type = request.query_params.get('user_type')
        if user_type in ['employer', 'candidate']:
            queryset = queryset.filter(user_type=user_type)
        
        # Filter by current user's type if no specific type is requested
        elif hasattr(request.user, 'employer'):
            queryset = queryset.filter(user_type='employer')
        elif hasattr(request.user, 'candidate'):
            queryset = queryset.filter(user_type='candidate')
        
        # Filter by specific user if requested
        user_id = request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        return queryset.order_by('-created_at')
            
        return queryset.order_by('-created_at')


class StoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Story.objects.all()
    serializer_class = StorySerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.user != self.request.user:
            raise PermissionDenied("You do not have permission to update this story.")
        serializer.save()
    
    def perform_destroy(self, instance):
        if instance.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied("You do not have permission to delete this story.")
        instance.is_active = False
        instance.save()


class LikeStoryView(APIView):
    """
    View to like or unlike a story
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, story_id):
        story = get_object_or_404(Story, id=story_id, is_active=True)
        user = request.user
        
        if story.likes.filter(id=user.id).exists():
            story.likes.remove(user)
            return Response({"status": "unliked"}, status=status.HTTP_200_OK)
        else:
            story.likes.add(user)
            return Response({"status": "liked"}, status=status.HTTP_201_CREATED)


class CommentCreateView(generics.CreateAPIView):
    """
    View to create a comment on a story
    """
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        story = get_object_or_404(Story, id=self.kwargs['story_id'], is_active=True)
        serializer.save(user=self.request.user, story=story)


class CommentListView(generics.ListAPIView):
    """
    View to list all comments for a story
    """
    serializer_class = CommentSerializer
    
    def get_queryset(self):
        return Comment.objects.filter(
            story_id=self.kwargs['story_id'],
            story__is_active=True
        ).order_by('-created_at')


class CommentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    View to retrieve, update or delete a comment
    """
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Comment.objects.filter(
            story_id=self.kwargs['story_id'],
            story__is_active=True
        )
    
    def perform_destroy(self, instance):
        # Only allow the comment owner to delete the comment
        if instance.user == self.request.user:
            instance.delete()


class SaveStoryView(APIView):
    """
    View to save or unsave a story
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, story_id):
        story = get_object_or_404(Story, id=story_id, is_active=True)
        content_type = ContentType.objects.get_for_model(Story)
        
        saved_item, created = SavedItem.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=story.id,
            defaults={'item_type': 'story'}
        )
        
        if not created:
            saved_item.delete()
            return Response("Story removed from saved", status=status.HTTP_200_OK)
            
        return Response("Story saved successfully", status=status.HTTP_201_CREATED)


class SavedStoriesListView(generics.ListAPIView):
    """
    View to list all saved stories for the current user
    """
    serializer_class = SavedItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        content_type = ContentType.objects.get_for_model(Story)
        return SavedItem.objects.filter(
            user=self.request.user,
            content_type=content_type,
            content_object__is_active=True
        ).order_by('-created_at')
