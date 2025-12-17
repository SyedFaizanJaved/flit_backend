from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import AccessToken

from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.utils import timezone
from django.http import HttpResponse
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
User = get_user_model()

from .models import MeetingRoom, UserGoogleToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .serializers import MeetingRoomSerializer
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from datetime import timedelta
import json
import random
import logging
logger = logging.getLogger("exceptions")
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow


# ----------------------------
#  GOOGLE EVENT CREATION
# ----------------------------
def create_google_event(user,title, description, start_time, end_time, attendees=None):
    # Get Google Calendar credentials
    try:
        token_obj = UserGoogleToken.objects.filter(user=user).first()
        if not token_obj:
            logger.error("Google account not connected due to missing token.")
            raise Exception("Please connect your Google account to create a meeting room.")
        creds = Credentials.from_authorized_user_info(token_obj.token_json)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_obj.token_json = json.loads(creds.to_json())
            token_obj.save()

        service = build("calendar", "v3", credentials=creds)

    except Exception as e:
        logger.exception("Error in Credentials")
        raise Exception("Credentials Not Found. Please Connect Calendar and try again later.")

    # Create event body
    event_body = {
        "summary": title,
        "description": description or "",
        "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        "conferenceData": {
            "createRequest": {
                "requestId": "vrmeet_" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789", k=8)),
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        },
    }

    # Add attendees to event
    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]

    event = service.events().insert(
        calendarId="primary", 
        body=event_body, 
        conferenceDataVersion=1,
        sendNotifications=True,
        sendUpdates="all",
    ).execute()

    # Get meet link from event
    meet_link = event.get("hangoutLink")
    if not meet_link:
        try:
            meet_link = event["conferenceData"]["entryPoints"][0]["uri"]
        except Exception:
            logger.exception("Error in Google API response")
            meet_link = None
    
    # Send email to attendees
    if attendees and meet_link:
        subject = f"Meeting Scheduled: {title}"
        body = (
            f"Hi there,\n\n"
            f"You have been invited to a meeting.\n\n"
            f"Title: {title}\n"
            f"Description: {description or 'No description provided.'}\n"
            f"Start Time (UTC): {start_time}\n"
            f"End Time (UTC): {end_time}\n"
            f"Google Meet Link: {meet_link}\n\n"
            f"Regards,\nVR Meet Team"
        )

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=attendees,
                fail_silently=False,
            )
            print(f"Email sent successfully to {', '.join(attendees)}")
        except Exception as e:
            logger.exception("Email sending failed")
            print(f"Email sending failed: {e}")
            pass

    return meet_link, event.get("id")


# ----------------------------
#  CREATE ROOM VIEW
# ----------------------------
class MeetingRoomCreateView(generics.CreateAPIView):
    queryset = MeetingRoom.objects.all()
    serializer_class = MeetingRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Create room logic
    def perform_create(self, serializer):
        data = serializer.validated_data

        if self.request.user.role.name != settings.USER_ROLE_EMPLOYER:
            raise PermissionDenied("You are not authorized to create a meeting room.")
        
        # Handle start/end time logic
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if not start_time and not end_time:
            start_time = timezone.now()
            end_time = start_time + timedelta(minutes=30)
        elif start_time and not end_time:
            end_time = start_time + timedelta(minutes=30)

        # Build attendees (employer + all candidate)
        attendees = []

        #employer
        attendees.append(self.request.user.email)

        #candidate
        candidate = data.get("candidate",None)
        candidate_email = None
        if candidate and getattr(candidate, 'email', None):
            attendees.append(candidate.email)
            candidate_email = candidate.email

        #extra hosts
        host_emails = data.get("host_email",[]) or []
       
        if host_emails:
            attendees.extend(host_emails)

        # Remove duplicate emails
        attendees = list({email for email in attendees if email})

        # Create Google Meet event
        try:
            meet_link, event_id = create_google_event(
                user=self.request.user,
                title=data.get("meeting_title"),
                description=data.get("description"),
                start_time=start_time,
                end_time=end_time,
                attendees=attendees
            )
        except Exception as e:
            logger.exception("Failed to create Google Meet event")
            meet_link, event_id= None,None
        
        if not meet_link:
            logger.error("Failed to generate Google Meet link. Room not created.")
            raise ValidationError("Failed to generate Google Meet link. Room not created.")


        # Save room in DB
        room = serializer.save(
            employer=self.request.user,
            start_time=start_time,
            end_time=end_time,
            meet_link=meet_link,
            candidate=candidate,
            candidate_email=candidate_email
        )

        return room


# ----------------------------
#  LIST VIEW
# ----------------------------
class MeetingRoomListView(generics.ListAPIView):
    serializer_class = MeetingRoomSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    page_size = 20

    """
    return all non-deleted rooms where:
        - current user is the employer, OR
        - room is public, OR
        - current user is assigned as candidate
    """
    def get_queryset(self):
        user = self.request.user
        return MeetingRoom.objects.filter(Q(is_deleted=False) & (Q(employer=user) | Q(privacy='public') | Q(candidate=user))).distinct()
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response_data = {
                'count': self.paginator.page.paginator.count,
                'next': self.paginator.get_next_link(),
                'previous': self.paginator.get_previous_link(),
                'total_pages': self.paginator.page.paginator.num_pages,
                'current_page': self.paginator.page.number,
                'results': serializer.data
            }
            return Response(response_data)
            
        # Fallback to non-paginated response if pagination is not applied
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'next': None,
            'previous': None,
            'total_pages': 1,
            'current_page': 1,
            'results': serializer.data
        })


# --------------------------
#  GET MEETING ROOM USING CODE
# --------------------------
class MeetingRoomDetailView(generics.RetrieveAPIView):
    queryset = MeetingRoom.objects.filter(is_deleted=False)
    serializer_class = MeetingRoomSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "room_code"

    def get_object(self):
        # fetch the meeting room based on room_code
        obj = super().get_object()
        user = self.request.user

        # if room is private and user is neither the employer nor the assigned candidate → deny access
        if obj.privacy == "private" and obj.employer != user and obj.candidate != user:
            raise PermissionDenied("Unauthorized access denied.")
        return obj
    
# --------------------------
#  DELETE MEETING ROOM
# --------------------------
class MeetingRoomDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        if self.request.user.role.name != settings.USER_ROLE_EMPLOYER:
            raise PermissionDenied("You are not authorized to delete a meeting room.")
        try:
            room = MeetingRoom.objects.get(pk=pk, is_deleted=False)
        except MeetingRoom.DoesNotExist:
            logger.exception("MeetingRoom.DoesNotExist : Meeting room not found")
            return Response({"detail": "Meeting room not found."}, status=status.HTTP_404_NOT_FOUND)
        
        if room.employer != request.user:
            return Response({"detail": "You are not authorized to delete this meeting room."}, status=status.HTTP_403_FORBIDDEN)
        
        room.is_deleted = True
        room.save()
        return Response({"detail": "Meeting room deleted successfully."}, status=status.HTTP_200_OK)
    
# --------------------------
#  GOOGLE OAUTH CONNECT VIEW
# --------------------------
from rest_framework.decorators import api_view
@api_view()
def connect_google(request):
    try:
        user_id = request.user.id
        if not user_id:
            logger.error("Missing user id")
            return Response({"detail": "User id missing"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user=User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.exception("User.DoesNotExist : User not found")
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if user.role.name != settings.USER_ROLE_EMPLOYER:  
            return Response({"detail": "You are not authorized to connect Google."}, status=status.HTTP_403_FORBIDDEN)
        
        flow = Flow.from_client_config(
            {
            "web":{
                "client_id": settings.CLIENT_ID,
                "client_secret": settings.CLIENT_SECRET,
                "auth_uri": settings.AUTH_URI,
                "token_uri": settings.TOKEN_URI,
                "redirect_uris": [settings.REDIRECT_URI],
                }
            },
            scopes=[settings.GOOGLE_SCOPES]
            )
        flow.redirect_uri = settings.REDIRECT_URI

        auth_url, state = flow.authorization_url(prompt='consent', login_hint="", state=str(user_id))
        
        return Response({"auth_url": auth_url})
        # return redirect(auth_url)

    except Exception as e:
        logger.exception("Exception in connect_google")
        return Response({"detail": "Something went wrong. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --------------------------
#  CANDIDATE MEETINGS VIEW
# --------------------------
class CandidateMeetingsView(generics.ListAPIView):
    serializer_class = MeetingRoomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Get all non-deleted meetings where the current user is the candidate
        return MeetingRoom.objects.filter(
            is_deleted=False,
            candidate=self.request.user
        ).order_by('-start_time')
    
    def get_queryset(self):
        # Get all non-deleted upcoming meetings where the current user is the candidate
        return MeetingRoom.objects.filter(
            is_deleted=False,
            candidate=self.request.user,
            start_time__gt=timezone.now()
        ).order_by('start_time')  # Order by start_time in ascending order
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

#--------------------------
#  GOOGLE OAUTH CALLBACK
#--------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_google_connection(request):
    """
    Check if the authenticated user has connected their Google account.
    Returns:
        Response: {"connected": bool, "message": str}
    """
    try:
        token_exists = UserGoogleToken.objects.filter(user=request.user).exists()
        if token_exists:
            return Response({
                "connected": True,
                "message": "Google account is connected"
            })
        return Response({
            "connected": False,
            "message": "Google account is not connected"
        })
    except Exception as e:
        logger.error(f"Error checking Google connection: {str(e)}")
        return Response({
            "connected": False,
            "message": "Error checking Google connection status"
        }, status=500)


def google_callback(request):
    try:
        user_id = request.GET.get("state")
        if not user_id or user_id == "None":
            logger.error("Missing user id in state param")
            return HttpResponse("User id missing", status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.exception("User.DoesNotExist : User not found")
            return HttpResponse("User not found", status=status.HTTP_404_NOT_FOUND)
        try:
            flow = Flow.from_client_config(
                {
                "web":{
                    "client_id": settings.CLIENT_ID,
                    "client_secret": settings.CLIENT_SECRET,
                    "auth_uri": settings.AUTH_URI,
                    "token_uri": settings.TOKEN_URI,
                    "redirect_uris": [settings.REDIRECT_URI],
                    }
                },
                scopes=[settings.GOOGLE_SCOPES],
                state=user_id
            )
            flow.redirect_uri = settings.REDIRECT_URI

            flow.fetch_token(authorization_response=request.build_absolute_uri())

            creds = flow.credentials
            token_json = json.loads(creds.to_json())

            UserGoogleToken.objects.update_or_create(
                user=user,
                defaults={"token_json": token_json}
            )

            return HttpResponse("Google connected successfully", status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Exception in google_callback")
            return HttpResponse("failed to connect google", status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.exception("Exception in google_callback")
        return HttpResponse("failed to connect google", status=status.HTTP_500_INTERNAL_SERVER_ERROR)