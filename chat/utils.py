import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

def send_candidate_notification(candidate_id, notification_type='dashboard_update', title=None, message=None, category=None):
    """
    Notification sockets have been removed as per the new requirements.
    This function is now a placeholder to prevent errors in signals.
    """
    # print(f"DEBUG: send_candidate_notification triggered for {candidate_id} (DISABLED)")
    pass
