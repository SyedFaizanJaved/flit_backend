import json
import logging
import asyncio  # <-- Yeh add kiya timeout ke liye
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
    logger = logging.getLogger(__name__)

    @database_sync_to_async
    def user_exists(self, user_id):
        """Check if a user exists with the given ID"""
        try:
            return User.objects.filter(id=user_id).exists()
        except Exception as e:
            self.logger.error(f"Error checking if user {user_id} exists: {str(e)}")
            return False

    @database_sync_to_async
    def is_employer(self, user_id):
        """Check if the user is an employer"""
        try:
            return Employer.objects.filter(user_id=user_id).exists()
        except Exception as e:
            self.logger.error(f"Error checking if user {user_id} is employer: {str(e)}")
            return False

    async def connect(self):
        try:
            self.logger.info(f"Incoming connection request. Scope: {self.scope}")
            
            # Get user IDs from URL
            self.sender_id = self.scope['url_route']['kwargs']['sender_id']
            self.recipient_id = self.scope['url_route']['kwargs']['recipient_id']
            self.logger.info(f"Sender ID: {self.sender_id}, Recipient ID: {self.recipient_id}")
            
            # Create room name
            user_ids = sorted([str(self.sender_id), str(self.recipient_id)])
            self.room_name = f"chat_{'_'.join(user_ids)}"
            self.logger.info(f"Room name: {self.room_name}")
            
            # Check if users exist
            sender_exists = await self.user_exists(self.sender_id)
            recipient_exists = await self.user_exists(self.recipient_id)
            
            if not sender_exists or not recipient_exists:
                error_msg = f"User not found. Sender exists: {sender_exists}, Recipient exists: {recipient_exists}"
                self.logger.error(error_msg)
                await self.close(code=4001)  # Custom close code for user not found
                return
            
            # Check user types
            is_sender_employer = await self.is_employer(self.sender_id)
            is_recipient_employer = await self.is_employer(self.recipient_id)
            self.logger.info(f"Sender is employer: {is_sender_employer}, Recipient is employer: {is_recipient_employer}")
            
            # Block employer-to-employer messaging
            if is_sender_employer and is_recipient_employer:
                error_msg = f"Connection rejected: Both users are employers. Sender {self.sender_id} and Recipient {self.recipient_id}"
                self.logger.warning(error_msg)
                await self.close(code=4000)
                return
            
            # Add to channel group
            await self.channel_layer.group_add(self.room_name, self.channel_name)
            self.logger.info(f"Added to channel group: {self.room_name}")
            
            # Accept the connection
            await self.accept()
            self.logger.info(f"WebSocket connection accepted for room: {self.room_name}")
            
        except Exception as e:
            self.logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close(code=4002)  # Custom close code for server error


    async def disconnect(self, close_code):
        if hasattr(self, 'room_name'):
            try:
                # Sirf 1 second wait karo – Daphne ko zyada wait na karna pade
                await asyncio.wait_for(
                    self.channel_layer.group_discard(self.room_name, self.channel_name),
                    timeout=1.0
                )
                self.logger.info(
                    f"User {getattr(self, 'sender_id', 'unknown')} cleanly left room: {self.room_name} "
                    f"(close_code: {close_code})"
                )
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Group discard TIMED OUT for room {self.room_name} during disconnect - safe to ignore"
                )
            except Exception as e:
                self.logger.warning(f"Non-critical error during group_discard in disconnect: {e}")

    @database_sync_to_async
    def update_unread_count(self, sender_id, recipient_id, increment=True):
        from django.db.models import F, Count, Sum
        from .models import ChatMessage
        
        if increment:
            # Increment unread count for new messages
            updated = ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(unread_count=F('unread_count') + 1)
            self.logger.debug(f"Incremented unread_count for {updated} messages from {sender_id} to {recipient_id}")
            
            # Get the updated unread counts
            unread_counts = ChatMessage.objects.filter(
                recipient_id=recipient_id,
                is_read=False
            ).aggregate(
                total_unread=Count('id'),
                unique_senders=Count('sender', distinct=True)
            )
            
            return {
                'unread_count': unread_counts.get('total_unread', 0),
                'total_count': unread_counts.get('unique_senders', 0)
            }
        else:
            # Mark messages as read and get the count of updated messages
            updated = ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(is_read=True, unread_count=0)
            
            self.logger.info(f"Marked {updated} messages as read from {sender_id} to {recipient_id}")
            
            # Get the updated unread counts after marking as read
            unread_counts = ChatMessage.objects.filter(
                recipient_id=recipient_id,
                is_read=False
            ).aggregate(
                total_unread=Count('id'),
                unique_senders=Count('sender', distinct=True)
            )
            
            return {
                'unread_count': unread_counts.get('total_unread', 0),
                'total_count': unread_counts.get('unique_senders', 0),
                'updated_count': updated  # Number of messages marked as read
            }

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            self.logger.debug(f"Received data from user {self.sender_id}: {data}")
            
            if data.get('type') == 'read_messages':
                sender_id = data.get('sender_id')
                recipient_id = data.get('recipient_id')
                if sender_id and recipient_id:
                    try:
                        # Update unread count in database and get updated counts
                        result = await self.update_unread_count(sender_id, recipient_id, increment=False)
                        
                        user_ids = sorted([str(sender_id), str(recipient_id)])
                        room_name = f"chat_{'_'.join(user_ids)}"
                        
                        # Notify chat room that messages were read
                        await self.channel_layer.group_send(
                            room_name,
                            {
                                'type': 'messages_read',
                                'sender_id': sender_id,
                                'recipient_id': recipient_id,
                                'read_at': str(timezone.now()),
                                'unread_count': result.get('unread_count', 0),
                                'total_count': result.get('total_count', 0)
                            }
                        )
                        
                        # Notify both users' chat lists to update
                        for user_id in [sender_id, recipient_id]:
                            user_type = 'employer' if await self.is_employer(user_id) else 'candidate'
                            group_name = f'chat_list_{user_type}_{user_id}'
                            
                            await self.channel_layer.group_send(
                                group_name,
                                {
                                    'type': 'message_read',
                                    'sender_id': sender_id,
                                    'recipient_id': recipient_id,
                                    'unread_count': result.get('unread_count', 0),
                                    'total_count': result.get('total_count', 0)
                                }
                            )
                        
                        self.logger.info(
                            f"Read receipt processed: {sender_id} -> {recipient_id}, "
                            f"marked {result.get('updated_count', 0)} messages as read, "
                            f"new unread_count: {result.get('unread_count', 0)}"
                        )
                    except Exception as e:
                        self.logger.error(f"Error processing read receipt: {str(e)}")
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'error': 'Failed to process read receipt',
                            'details': str(e)
                        }))
                return
            
            message = data.get('message') or data.get('content')
            if not message:
                raise ValueError('Message content is required')
                
            message_type = data.get('messageType') or data.get('message_type', 'text')
            allowed_types = dict(ChatMessage.MESSAGE_TYPE_CHOICES).keys()
            if message_type not in allowed_types:
                message_type = 'text'

            self.logger.info(f"Processing new message from {self.sender_id} to {self.recipient_id} (type: {message_type})")

            saved_message, error = await self.save_message(
                sender_id=self.sender_id,
                recipient_id=self.recipient_id,
                message=message,
                message_type=message_type
            )
            
            if error or not saved_message:
                error_msg = f"Failed to save message: {error or 'Unknown error'}"
                self.logger.error(error_msg)
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Failed to save message',
                    'details': error_msg,
                    'status': 'error'
                }))
                return
                
            self.logger.debug(f"Message saved with ID: {saved_message.id}")
            
            unread_counts = await self.update_unread_count(self.sender_id, self.recipient_id)
        
            user_ids = sorted([str(self.sender_id), str(self.recipient_id)])
            room_name = f"chat_{'_'.join(user_ids)}"
            
            # Send message to the chat room
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
            
            # Notify both users' chat lists to update
            for user_id in [self.sender_id, self.recipient_id]:
                user_type = 'employer' if await self.is_employer(user_id) else 'candidate'
                group_name = f'chat_list_{user_type}_{user_id}'
                
                # For the recipient, include unread count information
                if user_id == self.recipient_id:
                    await self.channel_layer.group_send(
                        group_name,
                        {
                            'type': 'chat_message',
                            'sender_id': self.sender_id,
                            'recipient_id': self.recipient_id,
                            'unread_count': unread_counts.get('unread_count', 0),
                            'total_count': unread_counts.get('total_count', 0),
                            'is_new_message': True
                        }
                    )
                else:
                    # For the sender, just trigger an update
                    await self.channel_layer.group_send(
                        group_name,
                        {
                            'type': 'chat_message',
                            'sender_id': self.sender_id,
                            'recipient_id': self.recipient_id
                        }
                    )
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON received from {self.sender_id}: {text_data}")
            await self.send(text_data=json.dumps({'error': 'Invalid JSON format', 'status': 'error'}))
            
        except ValueError as ve:
            self.logger.warning(f"Validation error from {self.sender_id}: {str(ve)}")
            await self.send(text_data=json.dumps({'error': str(ve), 'status': 'error'}))
            
        except Exception as e:
            self.logger.exception(f"Unexpected error in receive() for user {self.sender_id}")
            await self.send(text_data=json.dumps({'error': 'Internal server error', 'status': 'error'}))

    @database_sync_to_async
    def is_employer(self, user_id):
        try:
            user = User.objects.filter(id=user_id).first()
            if not user:
                self.logger.warning(f"User {user_id} not found during employer check")
                return False
            return hasattr(user, 'employer_profile')
        except Exception as e:
            self.logger.error(f"Error checking employer status for user {user_id}: {str(e)}")
            return False
        
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
            'read_at': event['read_at'],
            'unread_count': event.get('unread_count', 0),
            'total_count': event.get('total_count', 0)
        }))

    @database_sync_to_async
    def save_message(self, sender_id, recipient_id, message, message_type='text'):
        try:
            sender = User.objects.get(id=sender_id)
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist as e:
            error_msg = f"User not found - Sender: {sender_id}, Recipient: {recipient_id}"
            self.logger.error(error_msg)
            raise ValueError(error_msg) from e
        
        try:
            msg_obj = ChatMessage.objects.create(
                sender=sender,
                recipient=recipient,
                message=message,
                messageType=message_type,
                unread_count=1
            )
            self.logger.info(f"Message saved successfully - ID: {msg_obj.id}, from {sender_id} to {recipient_id}")
            return msg_obj, None
        except Exception as e:
            self.logger.exception(f"Failed to save message from {sender_id} to {recipient_id}")
            return None, str(e)


class ChatListConsumer(AsyncJsonWebsocketConsumer):
    logger = logging.getLogger(__name__)

    async def connect(self):
        try:
            self.user_type = self.scope['url_route']['kwargs'].get('user_type')
            self.user_id = self.scope['url_route']['kwargs'].get('user_id')
            self.candidate_id = self.scope['url_route']['kwargs'].get('candidate_id')
            
            if not self.user_type or not self.user_id:
                self.logger.warning("ChatList connection attempt with missing user_type or user_id")
                await self.close(code=4003)
                return
            
            # Convert user_id to int for consistency
            try:
                self.user_id = int(self.user_id)
                if self.candidate_id:
                    self.candidate_id = int(self.candidate_id)
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid user_id or candidate_id format: user_id={self.user_id}, candidate_id={self.candidate_id}")
                await self.close(code=4004)
                return
                
            # Set up group name based on user type and ID
            self.group_name = f'chat_list_{self.user_type}_{self.user_id}'
            
            # For employers viewing a specific candidate's chat
            if self.candidate_id and self.user_type == 'employer':
                self.group_name += f'_candidate_{self.candidate_id}'
            
            self.logger.info(f"ChatList connected for {self.user_type} user {self.user_id} with candidate_id {self.candidate_id}")
            
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            self.logger.info(f"ChatList connected for {self.user_type} user {self.user_id} with candidate_id {self.candidate_id}")
            await self.send_chat_list()
                
        except Exception as e:
            self.logger.error(f"ChatList connection error: {str(e)}")
            await self.close(code=4001)
    
    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            try:
                await asyncio.wait_for(
                    self.channel_layer.group_discard(self.group_name, self.channel_name),
                    timeout=1.0
                )
                self.logger.info(f"ChatList cleanly disconnected: {self.group_name} (close_code: {close_code})")
            except asyncio.TimeoutError:
                self.logger.warning(f"ChatList group discard TIMED OUT for {self.group_name} - safe to ignore")
            except Exception as e:
                self.logger.warning(f"Non-critical error in ChatList disconnect cleanup: {e}")
    
    async def receive_json(self, content):
        pass
    
    @database_sync_to_async
    def get_chat_list_data(self):
        from .models import ChatMessage
        from accounts.models import User
        from django.db.models import Q, Count, F, Subquery, OuterRef
        
        user_id = int(self.user_id)
        is_employer = self.user_type == 'employer'
        
        message_query = ChatMessage.objects.filter(
            Q(sender_id=user_id) | Q(recipient_id=user_id)
        )
        
        chat_partner_ids = set()
        for msg in message_query.values('sender', 'recipient'):
            if msg['sender'] != user_id:
                chat_partner_ids.add(msg['sender'])
            if msg['recipient'] != user_id:
                chat_partner_ids.add(msg['recipient'])
        
        users = User.objects.filter(id__in=chat_partner_ids)
        
        if is_employer:
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
                
                title = ''
                if hasattr(user, 'candidate_profile') and user.candidate_profile:
                    title = getattr(user.candidate_profile, 'title', '') or ''
                
                # Get candidate profile if it exists
                candidate_id = None
                if hasattr(user, 'candidate_profile') and user.candidate_profile:
                    candidate_id = user.candidate_profile.id
                
                user_data = {
                    'user_id': user.id,
                    'full_name': full_name,
                    'title': getattr(user, 'title', ''),
                    'profile_image': profile_image_url,
                    'last_message_time': user.last_message_time.isoformat() if hasattr(user, 'last_message_time') and user.last_message_time else None,
                    'unread_count': user.unread_count if hasattr(user, 'unread_count') else 0
                }
                
                # Add candidate_id to the response if available
                if candidate_id is not None:
                    user_data['candidate_id'] = candidate_id
                
                result.append(user_data)
        else:
            # Candidate view logic - show companies in company format
            users = users.prefetch_related(
                models.Prefetch('employer_profile', queryset=Employer.objects.select_related('company')),
                models.Prefetch('candidate_profile', queryset=Candidate.objects.all())
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
            
            result = []
            for user in users:
                employer_profile = getattr(user, 'employer_profile', None)
                candidate_profile = getattr(user, 'candidate_profile', None)
                
                latest_msg = ChatMessage.objects.filter(
                    (Q(sender=user, recipient_id=user_id) | 
                     Q(recipient=user, sender_id=user_id))
                ).order_by('-created_at').first()
                
                if employer_profile:
                    # Format for company users
                    company = getattr(employer_profile, 'company', None)
                    if company:
                        company_name = (
                            getattr(company, 'company_name', None) or
                            getattr(company, 'name', None) or
                            f"{employer_profile.first_name or ''} {employer_profile.last_name or ''}".strip() or
                            f"Employer {user.id}"
                        )
                        industry = getattr(company, 'industry', None) or getattr(employer_profile, 'position', '')
                        logo = getattr(company, 'logo', None)
                        logo_url = logo.url if logo and hasattr(logo, 'url') else None
                    else:
                        company_name = f"{employer_profile.first_name or ''} {employer_profile.last_name or ''}".strip() or f"Employer {user.id}"
                        industry = getattr(employer_profile, 'position', '')
                        logo_url = None
                    
                    user_data = {
                        'id': user.id,
                        'company_name': company_name,
                        'industry': industry,
                        'logo': logo_url,
                        'last_message_time': latest_msg.created_at.isoformat() if latest_msg else None,
                        'last_seen': user.last_login.isoformat() if user.last_login else None,
                        'unread_count': user.unread_count or 0,
                        'user_type': 'company'
                    }
                    
                    if company:
                        user_data['company_id'] = company.id
                else:
                    # Format for candidate users
                    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or f"User {user.id}"
                    title = getattr(candidate_profile, 'title', '') if candidate_profile else ''
                    profile_image = getattr(candidate_profile, 'profile_image', None) if candidate_profile else None
                    profile_image_url = profile_image.url if profile_image and hasattr(profile_image, 'url') else None
                    
                    user_data = {
                        'user_id': user.id,
                        'full_name': full_name,
                        'title': title,
                        'profile_image': profile_image_url,
                        'last_message_time': latest_msg.created_at.isoformat() if latest_msg else None,
                        'unread_count': user.unread_count or 0
                    }
                    
                    if candidate_profile:
                        user_data['candidate_id'] = candidate_profile.id
                
                result.append(user_data)
        
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
        self.logger.debug(f"Chat list update triggered for {self.group_name} - Sender: {event.get('sender_id')}, Recipient: {event.get('recipient_id')}")
        
        # Only update if this message is relevant to the current user
        current_user_id = int(self.user_id)
        sender_id = int(event.get('sender_id', 0))
        recipient_id = int(event.get('recipient_id', 0))
        
        if current_user_id in [sender_id, recipient_id]:
            await self.send_chat_list()
        else:
            self.logger.debug(f"Message not relevant for user {current_user_id}, skipping update")
    
    async def message_read(self, event):
        self.logger.debug(f"Chat list refresh on message read for {self.group_name}")
        await self.send_chat_list()