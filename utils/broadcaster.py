import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def broadcast_count_update(user_id, count_type, unread_count):
    """
    Websocket ke zariye connected user ko live unread count bhejta hai.
    Sends to user_{id}, candidate_{candidate_id}, and employer_{employer_id} groups.

    ponytail: never raises. Redis runs on localhost with no failover, and every
    caller has already committed its DB write by the time this runs — so letting a
    Redis blip escape turned a saved application into a 500 for the user. A dropped
    broadcast only costs a stale badge until the client refetches.

    Deliberately loud: this logs at error level, because a silent swallow would let
    Redis stay down for days with no signal beyond "notifications feel broken".
    """
    from accounts.models import User

    groups = [f"user_{user_id}"]

    try:
        user = User.objects.get(id=user_id)
        if hasattr(user, 'candidate_profile'):
            groups.append(f"candidate_{user.candidate_profile.id}")
        if hasattr(user, 'employer_profile'):
            groups.append(f"employer_{user.employer_profile.id}")
    except User.DoesNotExist:
        pass

    try:
        channel_layer = get_channel_layer()
        for group_name in groups:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "send_count",
                    "count_type": count_type,
                    "unread_count": unread_count
                }
            )
    except Exception:
        logger.error(
            "broadcast_count_update failed (count_type=%s, user_id=%s) — "
            "unread badge will be stale until the client refetches",
            count_type, user_id, exc_info=True,
        )
