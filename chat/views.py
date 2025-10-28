from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models
from django.db.models import Q, OuterRef, Subquery, Max, Count, Case, When, Value, IntegerField
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model
from .models import ChatMessage, ChatRoom, ChatRoomMessage
from .serializers import (
    ChatMessageSerializer, ChatMessageListSerializer, ChatRoomSerializer,
    ChatRoomListSerializer, ChatRoomMessageSerializer, ChatRoomMessageListSerializer,
    ChatRoomCreateSerializer, ChatRoomAddParticipantSerializer,
    EmployerConversationSummarySerializer, EmployerCompanyConversationSummarySerializer,
    CandidateConversationSummarySerializer
)
from candidates.models import Candidate
from employers.models import Employer

User = get_user_model()

class EmployerConversationListView(generics.ListAPIView):
    """
    Lists, for the authenticated employer, each candidate they have chatted with
    along with candidate id, name, title, last message time, and unread message count.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmployerConversationSummarySerializer
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Calculate number of candidates with unread messages
        candidates_with_unread = sum(1 for candidate in queryset if candidate.unread_count > 0)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # Get the paginated response data
            paginated_data = self.get_paginated_response(serializer.data).data
            # Create a new response with the desired format
            response_data = {
                'count': paginated_data['count'],
                'unread_candidates_count': candidates_with_unread,
                'next': paginated_data.get('next'),
                'previous': paginated_data.get('previous'),
                'results': paginated_data['results']
            }
            return Response(response_data)
            
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': len(serializer.data),
            'unread_candidates_count': candidates_with_unread,
            'next': None,
            'previous': None,
            'results': serializer.data
        })

    def get_queryset(self):
        # Get all unique user IDs that the current employer has chatted with
        sent_to = set(ChatMessage.objects.filter(
            sender=self.request.user
        ).values_list('recipient_id', flat=True).distinct())
        
        received_from = set(ChatMessage.objects.filter(
            recipient=self.request.user
        ).values_list('sender_id', flat=True).distinct())
        
        all_participants = sent_to.union(received_from)
        print(f"Current employer: {self.request.user.email} (ID: {self.request.user.id})")
        print(f"All participant user IDs: {all_participants}")
        
        if not all_participants:
            print("No participants found in messages")
            return Candidate.objects.none()
        
        # Get all users that the employer has chatted with, regardless of role
        User = get_user_model()
        all_chat_users = User.objects.filter(
            id__in=all_participants
        )
        
        print(f"Found {all_chat_users.count()} chat participants: {list(all_chat_users.values_list('id', 'email'))}")
        
        if not all_chat_users.exists():
            print("No users found among participants")
            return Candidate.objects.none()
            
        # Get candidate profiles for these users, including those without a role
        candidate_users = all_chat_users.filter(
            Q(role__name='candidate') | Q(role__isnull=True)
        )
        
        print(f"Found {candidate_users.count()} candidate users (including those without role): {list(candidate_users.values_list('id', 'email'))}")
            
        # Get candidate profiles for these users
        
        # Subquery to get the latest message time for each candidate
        latest_msg_subq = ChatMessage.objects.filter(
            Q(sender=self.request.user, recipient=OuterRef('user')) |
            Q(sender=OuterRef('user'), recipient=self.request.user)
        ).order_by('-created_at').values('created_at')[:1]

        # Subquery to count unread messages from candidate to employer
        unread_count_subq = ChatMessage.objects.filter(
            sender=OuterRef('user'),
            recipient=self.request.user,
            is_read=False
        ).values('sender').annotate(count=Count('id')).values('count')

        # Get candidate objects with annotations
        candidates = Candidate.objects.filter(
            user_id__in=candidate_users.values_list('id', flat=True)
        ).select_related('user').annotate(
            last_message_time=Subquery(latest_msg_subq, output_field=models.DateTimeField()),
            unread_count=Coalesce(Subquery(unread_count_subq, output_field=models.IntegerField()), 0)
        ).order_by('-last_message_time')
        
        # Debug: Print all candidates with their message info
        print(f"Found {candidates.count()} candidate profiles")
        for c in candidates:
            print(f"- {c.user.get_full_name()} (ID: {c.user_id}), last_msg: {getattr(c, 'last_message_time', None)}, unread: {getattr(c, 'unread_count', 0)}")
            
        return candidates


class CandidateEmployerConversationListView(generics.ListAPIView):
    """
    List all employers that the candidate has chatted with,
    along with employer user id, company name, industry, logo, the last message time, and the unread message count.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmployerCompanyConversationSummarySerializer
    
    def get_paginated_response(self, data):
        # Calculate number of employers with unread messages from the current page
        employers_with_unread = sum(1 for employer in self.paginator.page if hasattr(employer, 'unread_count') and employer.unread_count > 0)
        
        return Response({
            'count': self.paginator.page.paginator.count,
            'unread_employers_count': employers_with_unread,
            'next': self.paginator.get_next_link(),
            'previous': self.paginator.get_previous_link(),
            'results': data
        })

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        # For non-paginated responses
        serializer = self.get_serializer(queryset, many=True)
        employers_with_unread = sum(1 for employer in queryset if hasattr(employer, 'unread_count') and employer.unread_count > 0)
        
        return Response({
            'count': len(serializer.data),
            'unread_employers_count': employers_with_unread,
            'next': None,
            'previous': None,
            'results': serializer.data
        })

    def get_queryset(self):
        # Get all unique user IDs that the current user has chatted with
        sent_to = set(ChatMessage.objects.filter(
            sender=self.request.user
        ).values_list('recipient_id', flat=True).distinct())
        
        received_from = set(ChatMessage.objects.filter(
            recipient=self.request.user
        ).values_list('sender_id', flat=True).distinct())
        
        all_participants = sent_to.union(received_from)
        
        if not all_participants:
            print("No participants found in messages")
            return Employer.objects.none()
        
        # Get all employers that the current user has chatted with
        from django.db.models import Subquery, OuterRef, Count, Q
        from django.db.models.functions import Coalesce
        from django.contrib.auth import get_user_model
        
        # First, check if any of the participants are employers
        employers = Employer.objects.filter(user_id__in=all_participants)
        
        if not employers.exists():
            print("No employer users found among participants")
            print(f"Participant user IDs: {all_participants}")
            # Check if these users exist in the User table
            User = get_user_model()
            users = User.objects.filter(id__in=all_participants).values('id', 'email', 'first_name', 'last_name')
            print(f"User details: {list(users)}")
            return Employer.objects.none()
        
        # Subquery to get the latest message time for each employer
        latest_msg_subq = ChatMessage.objects.filter(
            Q(sender=self.request.user, recipient=OuterRef('user')) |
            Q(sender=OuterRef('user'), recipient=self.request.user)
        ).order_by('-created_at').values('created_at')[:1]

        # Subquery to count unread messages from employer to candidate
        unread_count_subq = ChatMessage.objects.filter(
            sender=OuterRef('user'),
            recipient=self.request.user,
            is_read=False
        ).values('sender').annotate(count=Count('id')).values('count')

        # Get employer objects with annotations
        employers = employers.select_related('company', 'user').annotate(
            last_message_time=Subquery(latest_msg_subq, output_field=models.DateTimeField()),
            unread_count=Coalesce(Subquery(unread_count_subq, output_field=models.IntegerField()), 0)
        ).order_by('-last_message_time')
        
        return employers


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
    ordering = ['-created_at'] 
    serializer_class = ChatMessageListSerializer

    def get_queryset(self):
        other_user_id = self.request.query_params.get('candidate_id') or self.kwargs.get('user_id')
        if not other_user_id:
            raise ValueError("candidate_id or user_id is required")
            
        # Convert to int to ensure proper type comparison
        other_user_id = int(other_user_id)
        
        # Get the conversation between the two users
        queryset = ChatMessage.objects.filter(
            models.Q(sender=self.request.user, recipient_id=other_user_id) |
            models.Q(sender_id=other_user_id, recipient=self.request.user)
        ).select_related('sender', 'recipient')
        
        # Mark unread messages as read
        unread_messages = queryset.filter(
            recipient=self.request.user,
            is_read=False
        )
        
        # Update all unread messages in a single query
        if unread_messages.exists():
            unread_messages.update(is_read=True)
        
        return queryset

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
