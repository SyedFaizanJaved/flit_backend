from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    # Chat Messages
    path('messages/', views.ChatMessageListView.as_view(), name='chat-message-list'),
    path('messages/with/<int:user_id>/', views.ConversationWithUserListView.as_view(), name='conversation-with-user'),
    path('messages/send/<int:recipient_id>/', views.send_message, name='send-message'),
    path('messages/<int:message_id>/read/', views.mark_message_read, name='mark-message-read'),
    path('messages/from/<int:sender_id>/read-all/', views.mark_messages_from_sender_read, name='mark-messages-from-sender-read'),
    
    # Chat Rooms
    path('rooms/', views.ChatRoomListView.as_view(), name='chat-room-list'),
    path('rooms/<int:pk>/', views.ChatRoomDetailView.as_view(), name='chat-room-detail'),
    path('rooms/<int:room_id>/participants/add/', views.add_participant, name='add-participant'),
    path('rooms/<int:room_id>/participants/<int:participant_id>/remove/', views.remove_participant, name='remove-participant'),
    
    # Room Messages
    path('rooms/<int:room_id>/messages/', views.ChatRoomMessageListView.as_view(), name='chat-room-message-list'),
    
    # Conversation Lists
    path('employers/conversations/', views.EmployerConversationListView.as_view(), name='employer-conversation-list'),
    path('candidates/conversations/', views.CandidateEmployerConversationListView.as_view(), name='candidate-employer-conversations'),
    
    # Dashboard
    path('dashboard/', views.chat_dashboard, name='chat-dashboard'),
]