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
from chat.models import ChatMessage
from accounts.models import User
from employers.models import Employer
from candidates.models import Candidate, ReferenceRequest
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

            is_sender_emp = await self.is_employer(self.sender_id)
            is_recipient_emp = await self.is_employer(self.recipient_id)
            
            self.logger.info(f"Connecting: sender={self.sender_id}, recipient={self.recipient_id}")
            self.logger.info(f"Roles: sender(Emp:{is_sender_emp}), recipient(Emp:{is_recipient_emp})")

            if not await self.user_exists(self.sender_id) or not await self.user_exists(self.recipient_id):
                self.logger.warning(f"Connection rejected: User not found. sender={self.sender_id}, recipient={self.recipient_id}")
                await self.close(code=4001)
                return

            # Only block if strictly required - for now, allow for testing
            # if is_sender_emp and is_recipient_emp:
            #    self.logger.warning("Connection rejected: Both users are employers.")
            #    await self.close(code=4000)
            #    return

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


            # Send email notification asynchronously with delay check
            asyncio.create_task(self._handle_notification(saved.id, self.sender_id, self.recipient_id, msg))

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

    async def _handle_notification(self, message_id, sender_id, recipient_id, message_content):
        """
        Wait for a short delay and then check if the message has been read.
        Only send email if the message is still unread.
        """
        try:
             # Wait 10 seconds to give the user time to read the message
            await asyncio.sleep(10)
            
            is_read = await self._is_message_read(message_id)
            if not is_read:
                await self._send_notification_email(sender_id, recipient_id, message_content)
            else:
                self.logger.info(f"Message {message_id} was read within delay, skipping email.")
        except Exception as e:
            self.logger.error(f"Notification handling error: {e}")

    @database_sync_to_async
    def _is_message_read(self, message_id):
        try:
            msg = ChatMessage.objects.get(id=message_id)
            return msg.is_read
        except ChatMessage.DoesNotExist:
            return False
            
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


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    logger = logging.getLogger(__name__)

    async def connect(self):
        try:
            self.candidate_id = self.scope['url_route']['kwargs'].get('candidate_id')
            if not self.candidate_id:
                await self.close(code=4003)
                return

            self.group_name = f'notifications_candidate_{self.candidate_id}'
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            
            self.logger.info(f"Notification socket connected for candidate {self.candidate_id}")
            
            # Send initial counts
            await self.send_dashboard_update()
            
        except Exception as e:
            self.logger.error(f"Notification connection error: {str(e)}")
            await self.close(code=4001)

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content):
        """
        Handles messages sent from the client (candidate).
        Currently supports: {"action": "mark_read", "category": "flit"}
        """
        action = content.get('action')
        category = content.get('category')
        
        if action == 'mark_read' and category:
            await self.mark_category_as_read(category)
            # After marking as read, send the updated counts back
            await self.send_dashboard_update()

    @database_sync_to_async
    def mark_category_as_read(self, category):
        """Database logic to mark items as read based on category."""
        from applications.models import JobApplication, ProjectApplication, InterviewRequest
        from vr_meet.models import Offer, MeetingRoom
        from employers.models import CandidateAction
        from candidates.models import Candidate, ReferenceRequest

        try:
            candidate = Candidate.objects.get(id=self.candidate_id)
            
            if category == 'flit':
                CandidateAction.objects.filter(candidate_id=str(candidate.id), action='pass', is_read=False).update(is_read=True)
            
            elif category == 'job_application':
                JobApplication.objects.filter(candidate=candidate, is_read=False).update(is_read=True)
            
            elif category == 'project_application':
                ProjectApplication.objects.filter(candidate=candidate, is_read=False).update(is_read=True)
            
            elif category == 'offer':
                Offer.objects.filter(candidate=candidate.user, is_read=False).update(is_read=True)
            
            elif category == 'reference':
                ReferenceRequest.objects.filter(candidate=candidate, is_read=False).update(is_read=True)
            
            elif category == 'interview':
                # Mark both systems as read
                InterviewRequest.objects.filter(
                    Q(job_application__candidate=candidate) | Q(project_application__candidate=candidate),
                    is_read=False
                ).update(is_read=True)
                
                MeetingRoom.objects.filter(candidate=candidate.user, is_read=False).update(is_read=True)

        except Exception as e:
            self.logger.error(f"Error marking {category} as read in consumer: {e}")


    async def send_dashboard_update(self, event=None):
        """
        Calculates and sends the latest unread counts to the candidate.
        """
        try:
            print(f"DEBUG: NotificationConsumer receiving send_dashboard_update for {self.candidate_id}")
            self.logger.debug(f"Calculating dashboard updates for candidate {self.candidate_id}")
            data = await self.get_unread_counts()
            await self.send_json({
                'type': 'dashboard_update',
                'counts': data
            })
        except Exception as e:
            self.logger.error(f"Error in send_dashboard_update: {e}")

    async def notify_alert(self, event):
        """
        Sends a real-time alert (toast message) to the candidate.
        Example: "Company XYZ flitted you!"
        """
        try:
            print(f"DEBUG: NotificationConsumer receiving notify_alert for {self.candidate_id}: {event.get('title')}")
            await self.send_json({
                'type': 'notification_alert',
                'title': event.get('title', 'New Notification'),
                'message': event.get('message', ''),
                'category': event.get('category', 'general')
            })
        except Exception as e:
            self.logger.error(f"Error in notify_alert: {e}")

    @database_sync_to_async
    def get_unread_counts(self):
        # Imports removed from here as they are at the top now or imported selectively
        from applications.models import JobApplication as Application, ProjectApplication, InterviewRequest
        from vr_meet.models import Offer, MeetingRoom
        from employers.models import CandidateAction

        try:
            candidate = Candidate.objects.get(id=self.candidate_id)
            cid_str = str(candidate.id)
            
            unread_flits = CandidateAction.objects.filter(
                candidate_id=cid_str, 
                action='pass', 
                is_read=False
            ).count()
            
            unread_job_apps = Application.objects.filter(candidate=candidate, is_read=False).count()
            unread_project_apps = ProjectApplication.objects.filter(candidate=candidate, is_read=False).count()
            # Offer model uses user
            unread_offers = Offer.objects.filter(candidate=candidate.user, is_read=False).count()
            unread_references = ReferenceRequest.objects.filter(candidate=candidate, is_read=False).count()
            
            # Combine InterviewRequest and MeetingRoom (which is what the UI shows)
            unread_interviews_apps = InterviewRequest.objects.filter(
                Q(job_application__candidate=candidate) | Q(project_application__candidate=candidate),
                is_read=False
            ).count()
            
            unread_interviews_vrmeet = MeetingRoom.objects.filter(
                candidate=candidate.user,
                is_read=False,
                is_deleted=False
            ).count()
            
            unread_interviews = unread_interviews_apps + unread_interviews_vrmeet

            return {
                'unread_flits_count': unread_flits,
                'unread_job_applications_count': unread_job_apps,
                'unread_project_applications_count': unread_project_apps,
                'unread_offers_count': unread_offers,
                'unread_reference_requests_count': unread_references,
                'unread_interview_requests_count': unread_interviews,

                'total_unread_count': (
                    unread_flits + unread_job_apps + unread_project_apps + 
                    unread_offers + unread_references + unread_interviews
                )
            }
        except Exception as e:
            self.logger.error(f"Error getting unread counts for candidate {self.candidate_id}: {e}")
            return {
                'unread_flits_count': 0,
                'unread_job_applications_count': 0,
                'unread_project_applications_count': 0,
                'unread_offers_count': 0,
                'unread_reference_requests_count': 0,
                'unread_interview_requests_count': 0,
                'total_unread_count': 0
            }