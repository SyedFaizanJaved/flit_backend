import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

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
