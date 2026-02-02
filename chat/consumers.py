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
from django.core.mail import send_mail
from django.conf import settings
from utils.email_service import send_chat_message_notification
            

class ChatConsumer(AsyncWebsocketConsumer):
    logger = logging.getLogger(__name__)

    @database_sync_to_async
    def user_exists(self, user_id):
        try:
            return User.objects.filter(id=user_id).exists()
        except:
            return False

    @database_sync_to_async
    def is_employer(self, user_id):
        try:
            return Employer.objects.filter(user_id=user_id).exists()
        except:
            return False

    async def handle_messages_read(self, messages_from_id: int, read_by_id: int):
        """
        Mark messages AS READ only if they are:
        FROM messages_from_id → TO read_by_id
        """
        try:
            updated = await self._mark_read_specific_direction(messages_from_id, read_by_id)
            if updated > 0:
                self.logger.info(f"Marked {updated} messages as read: {messages_from_id} → {read_by_id}")

                # Notify both users' chat lists
                for uid in [messages_from_id, read_by_id]:
                    utype = 'employer' if await self.is_employer(uid) else 'candidate'
                    await self.channel_layer.group_send(
                        f'chat_list_{utype}_{uid}',
                        {'type': 'chat_list_update'}
                    )

        except Exception as e:
            self.logger.error(f"handle_messages_read error: {str(e)}")

    @database_sync_to_async
    def _mark_read_specific_direction(self, sender_id, recipient_id):
        updated = ChatMessage.objects.filter(
            sender_id=sender_id,
            recipient_id=recipient_id,
            is_read=False
        ).update(is_read=True, unread_count=0)

        return updated

    async def connect(self):
        try:
            self.sender_id    = int(self.scope['url_route']['kwargs']['sender_id'])
            self.recipient_id = int(self.scope['url_route']['kwargs']['recipient_id'])

            ids = sorted([str(self.sender_id), str(self.recipient_id)])
            self.room_name = f"chat_{'_'.join(ids)}"

            if not await self.user_exists(self.sender_id) or not await self.user_exists(self.recipient_id):
                await self.close(code=4001)
                return

            if await self.is_employer(self.sender_id) and await self.is_employer(self.recipient_id):
                await self.close(code=4000)
                return

            await self.channel_layer.group_add(self.room_name, self.channel_name)
            await self.accept()

            self.logger.info(f"Chat opened → reader={self.sender_id} | partner={self.recipient_id}")

            await self.handle_messages_read(
                messages_from_id = self.recipient_id,   
                read_by_id       = self.sender_id   
            )

            # Periodic check — only for this conversation
            self.read_task = asyncio.create_task(self._periodic_read())

        except Exception as e:
            self.logger.error(f"connect error: {str(e)}", exc_info=True)
            await self.close(code=4002)

    async def _periodic_read(self):
        try:
            while True:
                await asyncio.sleep(3)
                if not hasattr(self, 'channel_name'):
                    return
                await self.handle_messages_read(
                    messages_from_id = self.recipient_id,
                    read_by_id       = self.sender_id
                )
        except asyncio.CancelledError:
            pass

    async def disconnect(self, close_code):
        if hasattr(self, 'read_task'):
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, 'room_name'):
            try:
                await self.channel_layer.group_discard(self.room_name, self.channel_name)
            except:
                pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)

            if data.get('type') == 'read_messages':
                s = data.get('sender_id')
                r = data.get('recipient_id')
                if s and r:
                    if int(s) != self.recipient_id or int(r) != self.sender_id:
                        await self.send(json.dumps({'error': 'Invalid read users'}))
                        return
                    await self.handle_messages_read(int(s), int(r))
                return

            msg = data.get('message') or data.get('content')
            if not msg:
                raise ValueError("No message content")

            msg_type = data.get('messageType', 'text')

            saved, err = await self._save_message(self.sender_id, self.recipient_id, msg, msg_type)
            if err or not saved:
                await self.send(json.dumps({'error': 'Save failed'}))
                return


            # Send email notification asynchronously
            asyncio.create_task(self._send_notification_email(self.sender_id, self.recipient_id, msg))

            # For new outgoing message — no need to mark anything as read
            # Just broadcast
            await self.channel_layer.group_send(
                self.room_name,
                {
                    'type': 'chat_message',
                    'message': msg,
                    'sender_id': self.sender_id,
                    'recipient_id': self.recipient_id,
                    'message_id': str(saved.id),
                    'messageType': msg_type,
                    'timestamp': str(timezone.now()),
                }
            )

            # Notify both chat lists
            for uid in [self.sender_id, self.recipient_id]:
                ut = 'employer' if await self.is_employer(uid) else 'candidate'
                await self.channel_layer.group_send(
                    f'chat_list_{ut}_{uid}',
                    {
                        'type': 'chat_message',
                        'sender_id': self.sender_id,
                        'recipient_id': self.recipient_id,
                        'is_new_message': uid == self.recipient_id
                    }
                )

        except Exception as e:
            self.logger.exception("receive error")
            await self.send(json.dumps({'error': str(e)}))

    async def chat_message(self, event):
        await self.send(json.dumps({
            'type': 'chat_message',
            **{k: v for k, v in event.items() if k != 'type'}
        }))

    @database_sync_to_async
    def _save_message(self, sender_id, recipient_id, message, message_type='text'):
        try:
            s = User.objects.get(id=sender_id)
            r = User.objects.get(id=recipient_id)
            msg = ChatMessage.objects.create(
                sender=s,
                recipient=r,
                message=message,
                messageType=message_type,
                unread_count=1
            )
            return msg, None
        except Exception as e:
            return None, str(e)

    @database_sync_to_async
    def _send_notification_email(self, sender_id, recipient_id, message_content):
        try:
            sender = User.objects.get(id=sender_id)
            recipient = User.objects.get(id=recipient_id)
            
            send_chat_message_notification(sender, recipient, message_content)
            
        except Exception as e:
            self.logger.error(f"Email sending failed: {e}")


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