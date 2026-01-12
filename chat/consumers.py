import json
import logging
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

    async def handle_messages_read(self, messages_from_id: int, read_by_id: int):
        """Mark messages as read and broadcast update to chat lists"""
        try:
            result = await self.update_unread_count(messages_from_id, read_by_id, increment=False)
            updated_count = result.get('updated_count', 0)

            if updated_count > 0:
                self.logger.info(
                    f"Marked {updated_count} messages as read from {messages_from_id} to {read_by_id}"
                )

                is_from_employer = await self.is_employer(messages_from_id)
                from_type = 'employer' if is_from_employer else 'candidate'

                is_to_employer = await self.is_employer(read_by_id)
                to_type = 'employer' if is_to_employer else 'candidate'

                await self.channel_layer.group_send(
                    f'chat_list_{from_type}_{messages_from_id}',
                    {'type': 'chat_list_update'}
                )

                await self.channel_layer.group_send(
                    f'chat_list_{to_type}_{read_by_id}',
                    {'type': 'chat_list_update'}
                )

        except Exception as e:
            self.logger.error(f"Error in handle_messages_read: {str(e)}")

    async def connect(self):
        try:
            self.sender_id = self.scope['url_route']['kwargs']['sender_id']
            self.recipient_id = self.scope['url_route']['kwargs']['recipient_id']

            user_ids = sorted([str(self.sender_id), str(self.recipient_id)])
            self.room_name = f"chat_{'_'.join(user_ids)}"

            sender_exists = await self.user_exists(self.sender_id)
            recipient_exists = await self.user_exists(self.recipient_id)

            if not sender_exists or not recipient_exists:
                self.logger.error("User not found")
                await self.close(code=4001)
                return

            is_sender_employer = await self.is_employer(self.sender_id)
            is_recipient_employer = await self.is_employer(self.recipient_id)

            if is_sender_employer and is_recipient_employer:
                self.logger.warning("Employer-to-employer messaging blocked")
                await self.close(code=4000)
                return

            await self.channel_layer.group_add(self.room_name, self.channel_name)
            await self.accept()

            self.logger.info(f"Chat connected: {self.room_name}")

            # Immediately mark messages as read when chat opens
            await self.handle_messages_read(self.recipient_id, self.sender_id)

            # Start periodic read checker while chat is open
            self.read_task = asyncio.create_task(self.periodic_read_checker())

        except Exception as e:
            self.logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close(code=4002)

    async def disconnect(self, close_code):
        # Cancel periodic task if running
        if hasattr(self, 'read_task'):
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, 'room_name'):
            try:
                await asyncio.wait_for(
                    self.channel_layer.group_discard(self.room_name, self.channel_name),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                self.logger.warning(f"Group discard timed out for {self.room_name}")
            except Exception as e:
                self.logger.warning(f"Error in group_discard: {e}")

    async def periodic_read_checker(self):
        """Periodically mark unread messages as read while chat is open"""
        try:
            while True:
                await asyncio.sleep(3)  # every 3 seconds
                if not hasattr(self, 'channel_name'):
                    break
                await self.handle_messages_read(self.recipient_id, self.sender_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Periodic read checker error: {str(e)}")

    @database_sync_to_async
    def update_unread_count(self, sender_id, recipient_id, increment=True):
        if increment:
            updated = ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(unread_count=F('unread_count') + 1)

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
            updated = ChatMessage.objects.filter(
                sender_id=sender_id,
                recipient_id=recipient_id,
                is_read=False
            ).update(is_read=True, unread_count=0)

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
                'updated_count': updated
            }

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            self.logger.debug(f"Received from {self.sender_id}: {data}")

            if data.get('type') == 'read_messages':
                sender_id = data.get('sender_id')
                recipient_id = data.get('recipient_id')
                if sender_id and recipient_id:
                    if sender_id != self.recipient_id or recipient_id != self.sender_id:
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'error': 'Invalid users for read receipt'
                        }))
                        return
                    await self.handle_messages_read(sender_id, recipient_id)
                return

            message = data.get('message') or data.get('content')
            if not message:
                raise ValueError('Message content is required')

            message_type = data.get('messageType') or data.get('message_type', 'text')
            # You can add validation for allowed types here if needed

            saved_message, error = await self.save_message(
                sender_id=self.sender_id,
                recipient_id=self.recipient_id,
                message=message,
                message_type=message_type
            )

            if error or not saved_message:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Failed to save message'
                }))
                return

            unread_counts = await self.update_unread_count(self.sender_id, self.recipient_id)

            await self.channel_layer.group_send(
                self.room_name,
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

            # Notify chat list of both users
            for user_id in [self.sender_id, self.recipient_id]:
                user_type = 'employer' if await self.is_employer(user_id) else 'candidate'
                group_name = f'chat_list_{user_type}_{user_id}'

                payload = {
                    'type': 'chat_message',
                    'sender_id': self.sender_id,
                    'recipient_id': self.recipient_id,
                }

                if user_id == self.recipient_id:
                    payload.update({
                        'unread_count': unread_counts.get('unread_count', 0),
                        'total_count': unread_counts.get('total_count', 0),
                        'is_new_message': True
                    })

                await self.channel_layer.group_send(group_name, payload)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
        except ValueError as ve:
            await self.send(text_data=json.dumps({'error': str(ve)}))
        except Exception as e:
            self.logger.exception(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({'error': 'Internal server error'}))

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

    @database_sync_to_async
    def save_message(self, sender_id, recipient_id, message, message_type='text'):
        try:
            sender = User.objects.get(id=sender_id)
            recipient = User.objects.get(id=recipient_id)

            msg_obj = ChatMessage.objects.create(
                sender=sender,
                recipient=recipient,
                message=message,
                messageType=message_type,
                unread_count=1
            )
            return msg_obj, None
        except User.DoesNotExist as e:
            return None, "User not found"
        except Exception as e:
            self.logger.exception("Failed to save message")
            return None, str(e)


# ChatListConsumer remains unchanged unless you have specific issues there
            
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
                    'title': title,
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
                        'last_message_time': user.last_message_time.isoformat() if hasattr(user, 'last_message_time') and user.last_message_time else None,
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
                        'last_message_time': user.last_message_time.isoformat() if hasattr(user, 'last_message_time') and user.last_message_time else None,
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

    async def chat_list_update(self, event):
        await self.send_chat_list()