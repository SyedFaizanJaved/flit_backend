from django.urls import re_path
from . import consumers

# WebSocket URL patterns
websocket_urlpatterns = [
    re_path(
        r'ws/chat/(?P<sender_id>\d+)/(?P<recipient_id>\d+)/$',
        consumers.ChatConsumer.as_asgi(),
        name='chat_room'
    ),
    re_path(
        r'^ws/chat-list/(?P<user_type>employer|candidate)/(?P<user_id>\d+)/?$',
        consumers.ChatListConsumer.as_asgi(),
        name='chat_list'
    ),
]
