from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def broadcast_count_update(user_id, count_type, unread_count):
    """
    Websocket ke zariye connected user ko live unread count bhejta hai.
    count_type: string representing the type (e.g. 'applications', 'notifications', etc.)
    unread_count: integer count
    """
    channel_layer = get_channel_layer()
    group_name = f"user_{user_id}"

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "send_count",
            "count_type": count_type,
            "unread_count": unread_count
        }
    )
