from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(
        r'ws/unread[-_]count/(?P<user_id>\d+)/?$',
        consumers.UnreadCountConsumer.as_asgi(),
        name='unread_count'
    ),
]
