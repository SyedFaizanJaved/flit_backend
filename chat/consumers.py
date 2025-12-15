
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import ChatMessage
from accounts.models import User

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.sender_id = self.scope['url_route']['kwargs']['sender_id']
        self.recipient_id = self.scope['url_route']['kwargs']['recipient_id']
        
        # Create a unique room name using sorted user IDs to ensure consistency
        user_ids = sorted([str(self.sender_id), str(self.recipient_id)])
        self.room_name = f"chat_{'_'.join(user_ids)}"
        
        print(f"User {self.sender_id} connecting to room: {self.room_name}")

        # Join room group
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        
        await self.accept()
        print(f"User {self.sender_id} connected successfully")

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_name'):
            await self.channel_layer.group_discard(
                self.room_name,
                self.channel_name
            )

    @database_sync_to_async
    def update_unread_count(self, sender_id, recipient_id, increment=True):
        """Update unread message counts and return counts for the sender"""
        from django.db.models import F, Count
        from .models import ChatMessage
        
        if increment:
            # Increment unread count for all unread messages from this sender to recipient
            ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(unread_count=F('unread_count') + 1)
        else:
            # Reset unread count when messages are read
            ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(
                is_read=True,
                unread_count=0
            )
        
        # Get count of unique senders with unread messages
        unique_senders_count = ChatMessage.objects.filter(
            recipient_id=recipient_id,
            is_read=False
        ).values('sender').distinct().count()
        
        # Get unread count for this specific sender
        sender_unread = ChatMessage.objects.filter(
            sender_id=sender_id,
            recipient_id=recipient_id,
            is_read=False
        ).count()
        
        return {
            'unread_count': sender_unread,    # Unread from this specific sender
            'total_count': unique_senders_count # Total number of people with unread messages
        }

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            print(f"[DEBUG] Received raw data: {data}")
            
            # Check if this is a read receipt
            if data.get('type') == 'read_messages':
                sender_id = data.get('sender_id')
                recipient_id = data.get('recipient_id')
                if sender_id and recipient_id:
                    # Mark messages as read
                    updated_count = await self.update_unread_count(sender_id, recipient_id, increment=False)
                    
                    # Notify sender that their messages were read
                    user_ids = sorted([str(sender_id), str(recipient_id)])
                    room_name = f"chat_{'_'.join(user_ids)}"
                    
                    await self.channel_layer.group_send(
                        room_name,
                        {
                            'type': 'messages_read',
                            'sender_id': sender_id,
                            'recipient_id': recipient_id,
                            'read_at': str(timezone.now())
                        }
                    )
                return
            
            # Handle new message
            message = data.get('message') or data.get('content')
            if not message:
                raise ValueError('Message content is required')
                
            message_type = data.get('messageType') or data.get('message_type', 'text')
            allowed_types = dict(ChatMessage.MESSAGE_TYPE_CHOICES).keys()
            if message_type not in allowed_types:
                message_type = 'text'

            print(f"[DEBUG] Processing message from {self.sender_id} to {self.recipient_id}")

            try:
                # Save message to database
                saved_message = await self.save_message(
                    sender_id=self.sender_id,
                    recipient_id=self.recipient_id,
                    message=message,
                    message_type=message_type
                )
            except ValueError as e:
                # Handle validation errors from save_message
                error_msg = f"Failed to save message: {str(e)}"
                print(f"[ERROR] {error_msg}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Failed to save message',
                    'details': str(e),
                    'status': 'error'
                }))
                return
                
            print(f"[DEBUG] Message saved with ID: {saved_message.id}")
            
            # Update unread counts
            unread_counts = await self.update_unread_count(self.sender_id, self.recipient_id)
            
            # Create a consistent room name
            user_ids = sorted([self.sender_id, self.recipient_id])
            room_name = f"chat_{'_'.join(user_ids)}"
            
            print(f"Sending to room: {room_name}")

            # Broadcast message to all in the room
            await self.channel_layer.group_send(
                room_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender_id': self.sender_id,
                    'recipient_id': self.recipient_id,
                    'message_id': str(saved_message.id),
                    'messageType': message_type,
                    'timestamp': str(timezone.now()),
                    'unread_count': unread_counts['unread_count'],  # Unread from this sender
                    'total_count': unread_counts['total_count']     # Total people with unread messages
                }
            )
                
        except json.JSONDecodeError:
            error_msg = 'Invalid JSON format'
            print(f"[ERROR] {error_msg}")
            await self.send(text_data=json.dumps({
                'error': error_msg,
                'status': 'error'
            }))
            
        except ValueError as ve:
            print(f"[ERROR] {str(ve)}")
            await self.send(text_data=json.dumps({
                'error': str(ve),
                'status': 'error'
            }))
            
        except Exception as e:
            error_msg = f'Error processing message: {str(e)}'
            print(f"[ERROR] {error_msg}")
            await self.send(text_data=json.dumps({
                'error': error_msg,
                'status': 'error'
            }))

    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'sender_id': event['sender_id'],
            'recipient_id': event['recipient_id'],
            'message_id': event['message_id'],
            'messageType': event['messageType'],
            'timestamp': event['timestamp'],
            'unread_count': event.get('unread_count', 0),
            'total_count': event.get('total_count', 0)  # Add total_count to the response
        }))

    async def messages_read(self, event):
        # Notify that messages were read
        await self.send(text_data=json.dumps({
            'type': 'messages_read',
            'sender_id': event['sender_id'],
            'recipient_id': event['recipient_id'],
            'read_at': event['read_at']
        }))

    @database_sync_to_async
    def save_message(self, sender_id, recipient_id, message, message_type='text'):
        try:
            # Validate users exist first
            try:
                sender = User.objects.get(id=sender_id)
                recipient = User.objects.get(id=recipient_id)
            except User.DoesNotExist as e:
                error_msg = f"User not found. Sender: {sender_id}, Recipient: {recipient_id}"
                print(f"[ERROR] {error_msg}")
                print(f"[ERROR] {str(e)}")
                raise ValueError(error_msg) from e
            
            try:
                # Create message with unread_count set to 1 by default
                message = ChatMessage.objects.create(
                    sender=sender,
                    recipient=recipient,
                    message=message,
                    messageType=message_type,
                    unread_count=1  # Set initial unread count to 1 for new messages
                )
                print(f"[DEBUG] Message saved successfully. ID: {message.id}")
                return message
                
            except Exception as e:
                error_msg = f"Error creating message: {str(e)}"
                print(f"[ERROR] {error_msg}")
                import traceback
                traceback.print_exc()
                raise ValueError(error_msg) from e
                
        except Exception as e:
            error_msg = f"Failed to save message: {str(e)}"
            print(f"[ERROR] {error_msg}")
            raise ValueError(error_msg) from e