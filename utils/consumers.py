import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from candidates.utils import get_candidate_unread_counts
from employers.utils import get_employer_unread_counts
from accounts.models import User

logger = logging.getLogger(__name__)

class UnreadCountConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.user_id = self.scope['url_route']['kwargs'].get('user_id')
            
            if not self.user_id:
                logger.warning("UnreadCount connection attempt with missing user_id")
                await self.close(code=4003)
                return
                
            self.user_id = int(self.user_id)
            self.group_name = f"user_{self.user_id}"

            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            await self.accept()
            logger.info(f"UnreadCountConsumer connected for user {self.user_id}")

         
            @database_sync_to_async
            def get_user_data(user_id):
                try:
                    user = User.objects.select_related('role').get(id=user_id)
                    role_name = user.role.name if user.role else ''
                    if role_name == 'employer':
                        counts = get_employer_unread_counts(user)
                        count_type = 'global'
                    else:
                        counts = get_candidate_unread_counts(user)
                        count_type = 'flit_list'
                    return count_type, counts
                except User.DoesNotExist:
                    return None, None

            count_type, counts = await get_user_data(self.user_id)
            
            if count_type and counts:
                await self.send(text_data=json.dumps({
                    "type": "initial_count",
                    "count_type": count_type,
                    "unread_count": counts
                }))
            else:
                logger.warning(f"User {self.user_id} not found or no data during WS initial count")

        except Exception as e:
            logger.error(f"UnreadCount connection error: {str(e)}")
            await self.close(code=4001)

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            try:
                await self.channel_layer.group_discard(
                    self.group_name,
                    self.channel_name
                )
                logger.info(f"UnreadCountConsumer cleanly disconnected for user {self.user_id}")
            except Exception as e:
                logger.warning(f"Error in UnreadCount disconnect cleanup: {e}")

    # Receives message from group
    async def send_count(self, event):
        count_type = event.get("count_type", "global")
        unread_count = event.get("unread_count", 0)

        # Send message to WebSocket frontend
        await self.send(text_data=json.dumps({
            "type": "count_update",
            "count_type": count_type,
            "unread_count": unread_count
        }))
