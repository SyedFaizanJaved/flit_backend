
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Count, Q, F, OuterRef, Subquery, Max
from django.db import models
from django.db.models.functions import Coalesce
from .models import ChatMessage
from accounts.models import User
from employers.models import Employer
from candidates.models import Candidate

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.sender_id = self.scope['url_route']['kwargs']['sender_id']
        self.recipient_id = self.scope['url_route']['kwargs']['recipient_id']
        
        # Create a unique room name using sorted user IDs to ensure consistency
        user_ids = sorted([str(self.sender_id), str(self.recipient_id)])
        self.room_name = f"chat_{'_'.join(user_ids)}"
        
        print(f"User {self.sender_id} connecting to room: {self.room_name}")
        
        # Accept the connection first
        await self.accept()
        
        # Verify at least one user is an employer and the other is a candidate
        is_sender_employer = await self.is_employer(self.sender_id)
        is_recipient_employer = await self.is_employer(self.recipient_id)
        
        # Ensure one is employer and one is candidate
        if is_sender_employer == is_recipient_employer:
            await self.close(code=4000)  # Close with custom error code
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        
        print(f"User {self.sender_id} connected successfully to chat with {self.recipient_id}")
    

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_name'):
            await self.channel_layer.group_discard(
                self.room_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            print(f"[DEBUG] Received raw data: {data}")
            
            # Ignore ping messages
            if data.get('type') == 'ping':
                return
                
            # Handle read receipt
            if data.get('type') == 'read_messages':
                sender_id = data.get('sender_id')
                recipient_id = data.get('recipient_id')
                if sender_id and recipient_id:
                    updated_count = await self.update_unread_count(sender_id, recipient_id, increment=False)
                    
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

            # Save message to database
            saved_message, error = await self.save_message(
                sender_id=self.sender_id,
                recipient_id=self.recipient_id,
                message=message,
                message_type=message_type
            )
            
            if error or not saved_message:
                error_msg = f"Failed to save message: {error or 'Unknown error'}"
                print(f"[ERROR] {error_msg}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Failed to save message',
                    'details': error_msg,
                    'status': 'error'
                }))
                return
                
            print(f"[DEBUG] Message saved with ID: {saved_message.id}")
            
            # Update unread counts
            unread_counts = await self.update_unread_count(self.sender_id, self.recipient_id)
        
            # Consistent room name
            user_ids = sorted([self.sender_id, self.recipient_id])
            room_name = f"chat_{'_'.join(user_ids)}"
            
            print(f"Sending to room: {room_name}")

            # Broadcast message
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
                    'unread_count': unread_counts.get('unread_count', 0),
                    'total_count': unread_counts.get('total_count', 0)
                }
            )
            
            # Notify chat list updates
            for user_id in [self.sender_id, self.recipient_id]:
                user_type = 'employer' if await self.is_employer(user_id) else 'candidate'
                group_name = f'chat_list_{user_type}_{user_id}'
                
                await self.channel_layer.group_send(
                    group_name,
                    {
                        'type': 'chat_message',
                        'sender_id': self.sender_id,
                        'recipient_id': self.recipient_id
                    }
                )
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format',
                'status': 'error'
            }))
            
        except ValueError as ve:
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
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'sender_id': event['sender_id'],
            'recipient_id': event['recipient_id'],
            'message_id': event['message_id'],
            'messageType': event['messageType'],
            'timestamp': event['timestamp'],
            'unread_count': event.get('unread_count', 0),
            'total_count': event.get('total_count', 0)
        }))

    async def messages_read(self, event):
        await self.send(text_data=json.dumps({
            'type': 'messages_read',
            'sender_id': event['sender_id'],
            'recipient_id': event['recipient_id'],
            'read_at': event['read_at']
        }))

    @database_sync_to_async
    def is_employer(self, user_id):
        try:
            user = User.objects.filter(id=user_id).first()
            if not user or not user.role:
                return False
            return user.role.name.lower() == 'employer'
        except Exception as e:
            print(f"[ERROR] Error checking if user {user_id} is employer: {str(e)}")
            return False

    @database_sync_to_async
    def update_unread_count(self, sender_id, recipient_id, increment=True):
        if increment:
            ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(unread_count=F('unread_count') + 1)
        else:
            ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(is_read=True, unread_count=0)
        
        unique_senders_count = ChatMessage.objects.filter(
            recipient_id=recipient_id,
            is_read=False
        ).values('sender').distinct().count()
        
        sender_unread = ChatMessage.objects.filter(
            sender_id=sender_id,
            recipient_id=recipient_id,
            is_read=False
        ).count()
        
        return {
            'unread_count': sender_unread,
            'total_count': unique_senders_count
        }

    @database_sync_to_async
    def save_message(self, sender_id, recipient_id, message, message_type='text'):
        try:
            sender = User.objects.get(id=sender_id)
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist as e:
            error_msg = f"User not found. Sender: {sender_id}, Recipient: {recipient_id}"
            print(f"[ERROR] {error_msg}")
            raise ValueError(error_msg) from e
        
        try:
            message_obj = ChatMessage.objects.create(
                sender=sender,
                recipient=recipient,
                message=message,
                messageType=message_type,
                unread_count=1
            )
            print(f"[DEBUG] Message saved successfully. ID: {message_obj.id}")
            return message_obj, None
        except Exception as e:
            error_msg = f"Error creating message: {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            return None, str(e)



class ChatListConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        try:
            self.user_type = self.scope['url_route']['kwargs'].get('user_type')
            self.user_id = self.scope['url_route']['kwargs'].get('user_id')
            
            if not self.user_type or not self.user_id:
                await self.close(code=4003)
                return
                
            self.group_name = f'chat_list_{self.user_type}_{self.user_id}'
            
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            
            # Send initial chat list
            await self.send_chat_list()
            
            # Start ping task
            self.ping_task = asyncio.create_task(self.send_ping())
            
        except Exception as e:
            print(f"[ERROR] WebSocket connection error: {str(e)}")
            await self.close(code=4001)
    
    async def disconnect(self, close_code):
        if hasattr(self, 'ping_task'):
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass
                
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
    
    async def send_ping(self):
        while True:
            try:
                await self.send(text_data=json.dumps({'type': 'ping'}))
                await asyncio.sleep(20)
            except Exception:
                break
    
    async def receive_json(self, content):
        pass  # Agar future mein kuch receive karna ho
    
    @database_sync_to_async
    def get_chat_list_data(self):
        user_id = self.user_id
        is_employer = self.user_type.lower() == 'employer'

        # Base query: users with whom the current user has chatted
        users = User.objects.filter(
            Q(sent_messages__recipient_id=user_id) | 
            Q(received_messages__sender_id=user_id),
            is_active=True
        ).distinct()

        # Prefetch related profiles efficiently
        users = users.select_related('role').prefetch_related(
            models.Prefetch(
                'employer_profile',
                queryset=Employer.objects.select_related('company').only(
                    'id', 'user_id', 'first_name', 'last_name', 'position', 'company__company_name', 'company__industry', 'company__logo'
                )
            ),
            models.Prefetch(
                'candidate_profile',
                queryset=Candidate.objects.only('id', 'user_id', 'full_name', 'title', 'profile_image')
            )
        ).annotate(
            last_message_time=Subquery(
                ChatMessage.objects.filter(
                    (Q(sender=OuterRef('id'), recipient_id=user_id) | 
                     Q(recipient=OuterRef('id'), sender_id=user_id))
                ).order_by('-created_at').values('created_at')[:1]
            ),
            unread_count=Coalesce(
                Subquery(
                    ChatMessage.objects.filter(
                        sender=OuterRef('id'),
                        recipient_id=user_id,
                        is_read=False
                    ).values('sender').annotate(cnt=Count('id')).values('cnt')
                ), 0
            )
        ).order_by('-last_message_time')

        result = []
        current_user = User.objects.filter(id=user_id).first()
        
        for user in users:
            employer_profile = getattr(user, 'employer_profile', None)
            candidate_profile = getattr(user, 'candidate_profile', None)

            latest_msg = ChatMessage.objects.filter(
                (Q(sender=user, recipient_id=user_id) | Q(recipient=user, sender_id=user_id))
            ).order_by('-created_at').first()

            unread_count = ChatMessage.objects.filter(
                sender=user,
                recipient_id=user_id,
                is_read=False
            ).count()

            # For employer viewing candidates
            if is_employer and candidate_profile:
                profile_image = candidate_profile.profile_image
                logo_url = None
                if profile_image:
                    logo_url = profile_image.url
                    if logo_url and not logo_url.startswith(('http://', 'https://')):
                        logo_url = f"https://flit.s3.us-west-1.amazonaws.com{logo_url}"

                full_name = candidate_profile.full_name or f"{user.first_name} {user.last_name}".strip() or f"User {user.id}"
                title = candidate_profile.title or ""

                result.append({
                    'id': str(user.id),  # Use user ID as main ID for consistency
                    'candidate_id': str(candidate_profile.id),  # Include candidate profile ID
                    'name': full_name,  # Show candidate name
                    'title': title,     # Show candidate title/position
                    'logo': logo_url,
                    'last_message_time': latest_msg.created_at.isoformat() if latest_msg else None,
                    'last_seen': user.last_login.isoformat() if user.last_login else None,
                    'unread_count': unread_count,
                    'user_type': 'candidate'  # Indicate this is a candidate
                })

            # For candidate viewing employers
            elif not is_employer and employer_profile:
                company = employer_profile.company
                company_name = company.company_name if company else f"{employer_profile.first_name} {employer_profile.last_name}".strip()
                industry = company.industry if company else employer_profile.position or ""
                logo_url = None
                if company and company.logo:
                    logo_url = company.logo.url
                    if logo_url and not logo_url.startswith(('http://', 'https://')):
                        logo_url = f"https://flit.s3.us-west-1.amazonaws.com{logo_url}"

                # For employers, use company ID as main ID and include employer profile ID
                company_id = str(company.id) if company else str(employer_profile.id)
                result.append({
                    'id': company_id,  # Use company ID as main ID
                    'company_id': company_id,  # Keep for backward compatibility
                    'employer_id': str(employer_profile.id),  # Add employer profile ID
                    'company_name': company_name,  # Show company name
                    'industry': industry,         # Show company industry
                    'logo': logo_url,
                    'last_message_time': latest_msg.created_at.isoformat() if latest_msg else None,
                    'last_seen': user.last_login.isoformat() if user.last_login else None,
                    'unread_count': unread_count,
                    'user_type': 'employer'  # Indicate this is an employer
                })

        # Sort by last message time
        result.sort(key=lambda x: x.get('last_message_time') or '1900-01-01', reverse=True)

        total_unread_chats = sum(1 for item in result if item['unread_count'] > 0)

        return {
            'count': len(result),
            'unread_count': total_unread_chats,
            'next': None,
            'previous': None,
            'results': result,
            'current_user_type': 'employer' if is_employer else 'candidate'
        }

    async def send_chat_list(self):
        data = await self.get_chat_list_data()
        await self.send_json(data)
    
    async def chat_message(self, event):
        await self.send_chat_list()
    
    async def message_read(self, event):
        await self.send_chat_list()