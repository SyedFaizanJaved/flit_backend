from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from .models import Story, Like, Comment, SavedItem
from .serializers import (
    StorySerializer, LikeSerializer, 
    CommentSerializer, SavedItemSerializer
)


class StoryListCreateView(generics.ListCreateAPIView):
    """
    View to list all stories or create a new story
    """
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Filter active stories and order by creation date (newest first)
        return Story.objects.filter(is_active=True).order_by('-created_at')
    
    def perform_create(self, serializer):
        # Set the user to the current user when creating a story
        serializer.save(user=self.request.user)
        
        # Handle content type and object ID if provided
        content_type_str = self.request.data.get('content_type')
        object_id = self.request.data.get('object_id')
        
        if content_type_str and object_id:
            try:
                content_type = ContentType.objects.get(model=content_type_str.lower())
                serializer.instance.content_type = content_type
                serializer.instance.object_id = object_id
                serializer.instance.save()
            except ContentType.DoesNotExist:
                pass


class StoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    View to retrieve, update or delete a story
    """
    queryset = Story.objects.all()
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_destroy(self, instance):
        # Soft delete by setting is_active to False
        instance.is_active = False
        instance.save()


class LikeStoryView(APIView):
    """
    View to like or unlike a story
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, story_id):
        story = get_object_or_404(Story, id=story_id, is_active=True)
        like, created = Like.objects.get_or_create(
            user=request.user,
            story=story
        )
        
        if not created:
            like.delete()
            return Response("Story unliked successfully", status=status.HTTP_200_OK)
            
        return Response("Story liked successfully", status=status.HTTP_201_CREATED)


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
