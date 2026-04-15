from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def broadcast_count_update(user_id, count_type, unread_count):
    """
    Websocket ke zariye connected user ko live unread count bhejta hai.
    Sends to user_{id}, candidate_{candidate_id}, and employer_{employer_id} groups.
    """
    from accounts.models import User
    channel_layer = get_channel_layer()
    
    groups = [f"user_{user_id}"]
    
    try:
        user = User.objects.get(id=user_id)
        if hasattr(user, 'candidate_profile'):
            groups.append(f"candidate_{user.candidate_profile.id}")
        if hasattr(user, 'employer_profile'):
            groups.append(f"employer_{user.employer_profile.id}")
    except User.DoesNotExist:
        pass

    for group_name in groups:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "send_count",
                "count_type": count_type,
                "unread_count": unread_count
            }
        )
