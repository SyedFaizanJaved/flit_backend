import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

def send_candidate_notification(candidate_id, notification_type='dashboard_update', title=None, message=None, category=None):
    """
    Sends a notification to a candidate via WebSockets.
    - notification_type='dashboard_update': Just triggers a recalculation of counts.
    - notification_type='notification_alert': Sends a visible toast/alert + title/message.
    """
    channel_layer = get_channel_layer()
    group_name = f'notifications_candidate_{candidate_id}'
    print(f"DEBUG: send_candidate_notification to group {group_name}, type={notification_type}")
    
    try:
        if notification_type == 'dashboard_update':
            print(f"DEBUG: Triggering dashboard_update for {group_name}")
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_dashboard_update',
                }
            )
        elif notification_type == 'notification_alert':
            print(f"DEBUG: sending alert AND update to {group_name}")
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'notify_alert',
                    'title': title,
                    'message': message,
                    'category': category
                }
            )
            # Also trigger count update
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_dashboard_update',
                }
            )
    except Exception as e:
        print(f"DEBUG: ERROR sending notification: {e}")
        logger.error(f"Error sending websocket notification: {e}")
