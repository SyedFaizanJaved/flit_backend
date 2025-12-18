
import json
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
            'unread_count': sender_unread,    
            'total_count': unique_senders_count 
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
                    'unread_count': unread_counts.get('unread_count', 0),
                    'total_count': unread_counts.get('total_count', 0)
                }
            )
            
            # Notify both sender and recipient's chat lists to update
            for user_id in [self.sender_id, self.recipient_id]:
                # Determine user type for the group name
                user_type = 'employer' if await self.is_employer(user_id) else 'candidate'
                group_name = f'chat_list_{user_type}_{user_id}'
                
                # Send update to chat list group
                await self.channel_layer.group_send(
                    group_name,
                    {
                        'type': 'chat_message',
                        'sender_id': self.sender_id,
                        'recipient_id': self.recipient_id
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

    @database_sync_to_async
    def is_employer(self, user_id):
     
        return Employer.objects.filter(user_id=user_id).exists()
        
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
            return message, None
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
                await self.close(code=4003)  # Missing parameters
                return
                
            self.group_name = f'chat_list_{self.user_type}_{self.user_id}'
            
            # Join user's chat list group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            await self.accept()
            await self.send_chat_list()
                
        except Exception as e:
            print(f"[ERROR] WebSocket connection error: {str(e)}")
            await self.close(code=4001)  # Other errors
    
    async def disconnect(self, close_code):
        # Leave group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
    
    async def receive_json(self, content):
        # Handle incoming WebSocket messages if needed
        pass
    
    @database_sync_to_async
    def get_chat_list_data(self):
        from .models import ChatMessage
        from accounts.models import User
        from django.db.models import Q, Count, F, Subquery, OuterRef
        
        user_id = int(self.user_id)
        is_employer = self.user_type == 'employer'
        
        # Get all messages where the user is either sender or recipient
        message_query = ChatMessage.objects.filter(
            Q(sender_id=user_id) | Q(recipient_id=user_id)
        )
        
        # Get all unique user IDs who have chatted with this user
        chat_partner_ids = set()
        for msg in message_query.values('sender', 'recipient'):
            if msg['sender'] != user_id:
                chat_partner_ids.add(msg['sender'])
            if msg['recipient'] != user_id:
                chat_partner_ids.add(msg['recipient'])
        
        # Get user details with latest message and unread count
        users = User.objects.filter(id__in=chat_partner_ids)
        
        if is_employer:
            # For employer, show candidate profiles
            users = users.prefetch_related('candidate_profile').annotate(
                last_message_time=Subquery(
                    ChatMessage.objects.filter(
                        (Q(sender=OuterRef('id'), recipient_id=user_id) | 
                         Q(recipient=OuterRef('id'), sender_id=user_id))
                    ).order_by('-created_at').values('created_at')[:1],
                    output_field=models.DateTimeField()
                ),
                unread_count=Coalesce(
                    Subquery(
                        ChatMessage.objects.filter(
                            sender=OuterRef('id'),
                            recipient_id=user_id,
                            is_read=False
                        ).values('sender').annotate(count=Count('id')).values('count'),
                        output_field=models.IntegerField()
                    ),
                    0
                )
            ).order_by('-last_message_time')
            
            # Prepare employer's view (showing candidates)
            result = []
            for user in users:
                profile_image = None
                if hasattr(user, 'candidate_profile') and user.candidate_profile:
                    profile_image = getattr(user.candidate_profile, 'profile_image', None)
                
                profile_image_url = profile_image.url if profile_image and hasattr(profile_image, 'url') else None
                full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or f"User {user.id}"
                
                latest_msg = ChatMessage.objects.filter(
                    (Q(sender=user, recipient_id=user_id) | 
                     Q(recipient=user, sender_id=user_id))
                ).order_by('-created_at').first()
                
                result.append({
                    'user_id': user.id,
                    'full_name': full_name,
                    'title': user.username or '',
                    'profile_image': profile_image_url,
                    'last_message_time': latest_msg.created_at.isoformat() if latest_msg else None,
                    'unread_count': user.unread_count or 0
                })
        else:
            # For candidate, show both employer and candidate profiles with prefetched data
            users = users.prefetch_related(
                models.Prefetch(
                    'employer_profile',
                    queryset=Employer.objects.select_related('company').only(
                        'id', 'user', 'first_name', 'last_name', 'company', 'profile_picture', 'position'
                    )
                ),
                models.Prefetch(
                    'candidate_profile',
                    queryset=Candidate.objects.only(
                        'id', 'user', 'full_name', 'title', 'profile_image'
                    )
                )
            ).annotate(
                last_message_time=Subquery(
                    ChatMessage.objects.filter(
                        (Q(sender=OuterRef('id'), recipient_id=user_id) | 
                         Q(recipient=OuterRef('id'), sender_id=user_id))
                    ).order_by('-created_at').values('created_at')[:1],
                    output_field=models.DateTimeField()
                ),
                unread_count=Coalesce(
                    Subquery(
                        ChatMessage.objects.filter(
                            sender=OuterRef('id'),
                            recipient_id=user_id,
                            is_read=False
                        ).values('sender').annotate(count=Count('id')).values('count'),
                        output_field=models.IntegerField()
                    ),
                    0
                )
            ).order_by('-last_message_time')
            
            # Prepare the chat list with all participants
            result = []
            for user in users:
                company_name = ''
                industry = ''
                logo_url = None
                
                # Check if user is an employer
                employer_profile = getattr(user, 'employer_profile', None)
                candidate_profile = getattr(user, 'candidate_profile', None)
                
                if employer_profile:
                    # Handle employer profile
                    company = getattr(employer_profile, 'company', None)
                    if company:
                        # Get company name from various possible fields
                        company_name = (
                            getattr(company, 'company_name', None) or 
                            getattr(company, 'name', None) or
                            f"{getattr(employer_profile, 'first_name', '')} {getattr(employer_profile, 'last_name', '')}".strip() or
                            f"Employer {user.id}"
                        )
                        
                        # Get industry if available
                        industry = getattr(company, 'industry', None) or getattr(employer_profile, 'position', '')
                        
                        # Get logo URL if available
                        logo = getattr(company, 'logo', None)
                        if logo and hasattr(logo, 'url'):
                            try:
                                logo_url = logo.url
                                # Make sure the URL is absolute
                                if logo_url and not (logo_url.startswith('http://') or logo_url.startswith('https://')):
                                    logo_url = f"https://flit.s3.us-west-1.amazonaws.com/{logo_url}"
                            except Exception as e:
                                print(f"Error getting logo URL for company {getattr(company, 'id', 'unknown')}: {str(e)}")
                                logo_url = None
                    else:
                        # If no company, use employer's name
                        company_name = (
                            f"{getattr(employer_profile, 'first_name', '')} {getattr(employer_profile, 'last_name', '')}".strip() or
                            f"Employer {user.id}"
                        )
                        industry = getattr(employer_profile, 'position', '')
                
                elif candidate_profile:
                    # Handle candidate profile
                    company_name = getattr(candidate_profile, 'full_name', f"User {user.id}")
                    industry = getattr(candidate_profile, 'title', 'Candidate')
                    
                    # Get candidate's profile image if available
                    profile_image = getattr(candidate_profile, 'profile_image', None)
                    if profile_image and hasattr(profile_image, 'url'):
                        try:
                            logo_url = profile_image.url
                            # Make sure the URL is absolute
                            if logo_url and not (logo_url.startswith('http://') or logo_url.startswith('https://')):
                                logo_url = f"https://flit.s3.us-west-1.amazonaws.com/{logo_url}"
                        except Exception as e:
                            print(f"Error getting profile image for candidate {user.id}: {str(e)}")
                            logo_url = None
                
                # Handle admin users (only if not already handled by employer or candidate profile)
                if (user.is_staff or user.is_superuser) and not employer_profile and not candidate_profile:
                    # For admin users, use their full name or username
                    company_name = user.get_full_name() or user.username or f"User {user.id}"
                    # Get role name from the database, default to 'admin' if not available
                    if hasattr(user, 'role') and user.role:
                        industry = getattr(user.role, 'name', '').lower() or 'admin'
                    else:
                        # If no role is set, check if user is in the admin group
                        from django.contrib.auth.models import Group
                        if user.groups.filter(name='admin').exists():
                            industry = 'admin'
                        else:
                            industry = 'staff' if user.is_staff else 'admin'
                    
                    # Try to get profile image from user profile if available
                    if hasattr(user, 'profile') and hasattr(user.profile, 'profile_picture'):
                        try:
                            logo_url = user.profile.profile_picture.url
                            # Make sure the URL is absolute
                            if logo_url and not (logo_url.startswith('http://') or logo_url.startswith('https://')):
                                logo_url = f"https://flit.s3.us-west-1.amazonaws.com/{logo_url}"
                        except Exception as e:
                            print(f"Error getting profile image for admin {user.id}: {str(e)}")
                            logo_url = None
                
                latest_msg = ChatMessage.objects.filter(
                    (Q(sender=user, recipient_id=user_id) | 
                     Q(recipient=user, sender_id=user_id))
                ).order_by('-created_at').first()
                
                result.append({
                    'id': user.id,
                    'company_name': company_name,
                    'industry': industry,
                    'logo': logo_url,
                    'last_message_time': latest_msg.created_at.isoformat() if latest_msg else None,
                    'last_seen': user.last_login.isoformat() if user.last_login else None,
                    'unread_count': user.unread_count or 0
                })
        
        # Sort by most recent message
        result.sort(key=lambda x: x.get('last_message_time') or '', reverse=True)
        
        return {
            'count': len(result),
            'unread_count': sum(1 for u in result if u.get('unread_count', 0) > 0),
            'next': None,
            'previous': None,
            'results': result
        }

    async def send_chat_list(self):
        data = await self.get_chat_list_data()
        await self.send_json(data)
    
    async def chat_message(self, event):
        # This will be called when a new message is sent
        await self.send_chat_list()
    
    async def message_read(self, event):
        # This will be called when messages are marked as read
        await self.send_chat_list()