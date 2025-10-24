from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models
from .models import ChatMessage, ChatRoom, ChatRoomMessage
from .serializers import (
    ChatMessageSerializer, ChatMessageListSerializer, ChatRoomSerializer,
    ChatRoomListSerializer, ChatRoomMessageSerializer, ChatRoomMessageListSerializer,
    ChatRoomCreateSerializer, ChatRoomAddParticipantSerializer
)


class ChatMessageListView(generics.ListCreateAPIView):
    """
    Chat message list and create view
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['messageType', 'is_read']
    search_fields = ['message']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ChatMessageSerializer
        return ChatMessageListSerializer
    
    def get_queryset(self):
        return ChatMessage.objects.filter(
            models.Q(sender=self.request.user) | models.Q(recipient=self.request.user)
        )


class ConversationWithUserListView(generics.ListAPIView):
    """
    List all messages between the authenticated user and a specific other user
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['message']
    ordering_fields = ['created_at']
    ordering = ['created_at']
    serializer_class = ChatMessageListSerializer

    def get_queryset(self):
        other_user_id = self.kwargs.get('user_id')
        return ChatMessage.objects.filter(
            (
                models.Q(sender=self.request.user, recipient_id=other_user_id) |
                models.Q(sender_id=other_user_id, recipient=self.request.user)
            )
        ).order_by('created_at')


class ChatRoomListView(generics.ListCreateAPIView):
    """
    Chat room list and create view
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['room_type', 'is_private', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ChatRoomCreateSerializer
        return ChatRoomListSerializer
    
    def get_queryset(self):
        return ChatRoom.objects.filter(
            participants=self.request.user,
            is_active=True
        )


class ChatRoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Chat room detail view
    """
    serializer_class = ChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ChatRoom.objects.filter(
            participants=self.request.user,
            is_active=True
        )


class ChatRoomMessageListView(generics.ListCreateAPIView):
    """
    Chat room message list and create view
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['message_type', 'is_deleted']
    search_fields = ['message']
    ordering_fields = ['created_at']
    ordering = ['created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ChatRoomMessageSerializer
        return ChatRoomMessageListSerializer
    
    def get_queryset(self):
        room_id = self.kwargs.get('room_id')
        if room_id:
            return ChatRoomMessage.objects.filter(room_id=room_id)
        return ChatRoomMessage.objects.filter(
            room__participants=self.request.user
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def send_message(request, recipient_id):
    """
    Send a direct message
    """
    try:
        from accounts.models import User
        recipient = User.objects.get(id=recipient_id)
        
        message = ChatMessage.objects.create(
            sender=request.user,
            recipient=recipient,
            message=request.data.get('message', ''),
            messageType=request.data.get('messageType', 'text')
        )
        
        return Response({
            'message': 'Message sent successfully',
            'chat_message': ChatMessageSerializer(message).data
        }, status=status.HTTP_201_CREATED)
    except User.DoesNotExist:
        return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_participant(request, room_id):
    """
    Add participants to a chat room
    """
    try:
        room = ChatRoom.objects.get(id=room_id, created_by=request.user)
        serializer = ChatRoomAddParticipantSerializer(data=request.data)
        
        if serializer.is_valid():
            participants = serializer.validated_data['participant_emails']
            room.participants.add(*participants)
            
            return Response({
                'message': 'Participants added successfully',
                'room': ChatRoomSerializer(room).data
            }, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except ChatRoom.DoesNotExist:
        return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def remove_participant(request, room_id, participant_id):
    """
    Remove a participant from a chat room
    """
    try:
        room = ChatRoom.objects.get(id=room_id, created_by=request.user)
        from accounts.models import User
        participant = User.objects.get(id=participant_id)
        
        room.participants.remove(participant)
        
        return Response({
            'message': 'Participant removed successfully',
            'room': ChatRoomSerializer(room).data
        }, status=status.HTTP_200_OK)
    except ChatRoom.DoesNotExist:
        return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
    except User.DoesNotExist:
        return Response({'error': 'Participant not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_message_read(request, message_id):
    """
    Mark a message as read
    """
    try:
        message = ChatMessage.objects.get(id=message_id, recipient=request.user)
        message.is_read = True
        message.save()
        
        return Response({
            'message': 'Message marked as read',
            'chat_message': ChatMessageSerializer(message).data
        }, status=status.HTTP_200_OK)
    except ChatMessage.DoesNotExist:
        return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_messages_from_sender_read(request, sender_id):
    try:
        from accounts.models import User
        User.objects.get(id=sender_id)
    except Exception:
        return Response({'error': 'Sender not found'}, status=status.HTTP_404_NOT_FOUND)

    updated_count = ChatMessage.objects.filter(
        sender_id=sender_id,
        recipient=request.user,
        is_read=False
    ).update(is_read=True)

    return Response({
        'message': 'Messages marked as read',
        'updated_count': updated_count
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def chat_dashboard(request):
    """
    Chat dashboard data
    """
    data = {
        'unread_messages': ChatMessage.objects.filter(recipient=request.user, is_read=False).count(),
        'total_rooms': ChatRoom.objects.filter(participants=request.user, is_active=True).count(),
        'recent_messages': ChatMessageListSerializer(
            ChatMessage.objects.filter(
                models.Q(sender=request.user) | models.Q(recipient=request.user)
            )[:10], many=True
        ).data,
    }
    
    return Response(data, status=status.HTTP_200_OK)
