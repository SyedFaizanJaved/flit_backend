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
    
    # Google Calendar will automatically send invitations to attendees
    # No need for custom email sending as it causes duplicate emails

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
        user = self.request.user
        queryset = MeetingRoom.objects.filter(
            is_deleted=False,
            candidate=user
        )
        
        tab = self.request.query_params.get('tab', 'all')
        now = timezone.now()
        
        if tab == 'scheduled':
            queryset = queryset.filter(status='active', start_time__gt=now)
        elif tab == 'invited':
            queryset = queryset.filter(status='pending')
        elif tab == 'expired':
            queryset = queryset.filter(start_time__lt=now).exclude(status__in=['ended', 'cancelled'])
        
        # Default order: scheduled items first, then by latest created
        if tab == 'scheduled':
            return queryset.order_by('start_time')
        return queryset.order_by('-start_time')
    
    def list(self, request, *args, **kwargs):
        user = request.user
        now = timezone.now()
        
        # Base queryset for calculating all statistics accurately
        base_qs = MeetingRoom.objects.filter(is_deleted=False, candidate=user)
        
        # Determine current tab/category filtering
        tab = self.request.query_params.get('tab', 'all')
        
        stats = {
            "total_requests": base_qs.count(),
            "scheduled": base_qs.filter(status='active', start_time__gt=now).count(),
            "invited": base_qs.filter(status='pending').count(),
            "expired": base_qs.filter(start_time__lt=now).exclude(status__in=['ended', 'cancelled']).count(),
        }
        
        # Note: I'm using a slightly safer way to count expired to avoid bugs
        stats["expired"] = base_qs.filter(start_time__lt=now).exclude(status__in=['ended', 'cancelled']).count()

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            "stats": stats,
            "meetings": serializer.data
        })

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

# -----------------------------------------------
#  OFFER VIEWS (Hire / Reject Functionality)
# -----------------------------------------------
from .models import Offer
from .serializers import OfferSerializer, RejectCandidateSerializer


class OfferCreateView(generics.CreateAPIView):
    """
    POST /api/vr-meet/offers/
    Create an offer and automatically hire the candidate.
    Status is set to 'hired' upon creation — no separate update needed.
    Only the employer who hosted the meeting can create an offer.
    Generates a PDF offer letter and emails it to the candidate.
    """
    serializer_class = OfferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        # Enforce employer role
        if not hasattr(user, 'role') or user.role.name != settings.USER_ROLE_EMPLOYER:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only employers can create offers.")

        meeting = serializer.validated_data['meeting']
        logger.info(
            f"Employer {user.email} hiring candidate for meeting #{meeting.id}"
        )
        # Auto-set status to 'hired' when creating an offer
        serializer.save(employer=user, status='hired')

        # Generate offer letter PDF and send email to candidate
        offer = serializer.instance
        _send_offer_letter_for_hire(offer, user)


def _send_offer_letter_for_hire(offer, employer_user):
    """
    Generate a PDF offer letter and email it to the hired candidate.
    Called after an offer with status='hired' is created.
    Failures are logged but do not prevent the hire from succeeding.
    """
    try:
        from utils.offer_letter_pdf import generate_offer_letter_pdf
        from utils.email_service import send_offer_letter_email

        meeting = offer.meeting
        candidate_user = offer.candidate

        # ── Get candidate profile ──────────────────────────
        candidate_profile = None
        candidate_name = candidate_user.get_full_name() or candidate_user.email
        try:
            candidate_profile = candidate_user.candidate_profile
            candidate_name = candidate_profile.full_name or candidate_name
        except Exception:
            pass

        # ── Get employer profile & company ─────────────────
        employer_name = employer_user.get_full_name() or employer_user.email
        employer_position = 'Hiring Manager'
        company_name = 'The Company'
        company_location = ''

        try:
            employer_profile = employer_user.employer_profile
            employer_name = employer_profile.full_name or employer_name
            employer_position = employer_profile.position or 'Hiring Manager'

            if employer_profile.company:
                company_name = employer_profile.company.company_name
                company_location = employer_profile.company.location or ''
        except Exception:
            pass

        # ── Determine compensation display ─────────────────
        if offer.is_hourly:
            salary_amount = int(offer.hourly_rate or 0)
            salary_label = f"USD {salary_amount:,}/hr"
        else:
            salary_amount = int(offer.salary or 0)
            salary_label = f"USD {salary_amount:,}"

        # ── Determine position title from meeting's job/project
        position_title = offer.title
        employment_type = 'full-time'

        if meeting.job:
            position_title = position_title or meeting.job.title
        elif meeting.project:
            position_title = position_title or meeting.project.title
            employment_type = 'contract'

        location = company_location or 'To be determined'
        start_date = offer.date_of_joining or ''
        offer_terms = offer.description or ''

        # ── Generate PDF ───────────────────────────────────
        pdf_bytes = generate_offer_letter_pdf({
            'candidate_name': candidate_name,
            'position_title': position_title,
            'company_name': company_name,
            'company_location': company_location,
            'employer_name': employer_name,
            'employer_position': employer_position,
            'offer_salary': salary_amount,
            'salary_currency': 'USD',
            'start_date': start_date,
            'employment_type': employment_type,
            'location': location,
            'offer_terms': offer_terms,
            'is_hourly': offer.is_hourly,
            'employer_email': employer_user.email,
        })

        # ── Send email with PDF ────────────────────────────
        # We need a candidate-like object with .full_name and .user.email
        class CandidateProxy:
            """Proxy object to match email_service expected interface."""
            def __init__(self, name, user):
                self.full_name = name
                self.user = user

        candidate_proxy = CandidateProxy(candidate_name, candidate_user)

        email_sent = send_offer_letter_email(
            candidate=candidate_proxy,
            company_name=company_name,
            position_title=position_title,
            offer_salary=salary_amount,
            salary_currency='USD',
            start_date=start_date,
            employment_type=employment_type,
            location=location,
            offer_terms=offer_terms,
            pdf_bytes=pdf_bytes,
        )

        if email_sent:
            logger.info(
                f"Offer letter email sent to {candidate_user.email} "
                f"for offer #{offer.id} ({position_title})"
            )
        else:
            logger.warning(
                f"Offer letter email FAILED for {candidate_user.email} "
                f"for offer #{offer.id}"
            )

    except Exception as e:
        logger.error(
            f"Error in _send_offer_letter_for_hire for offer #{offer.id}: {str(e)}",
            exc_info=True
        )


class OfferListView(generics.ListAPIView):
    """
    GET /api/vr-meet/offers/list/
    List offers for the authenticated user.
    - Employers see offers they sent.
    - Candidates see offers they received.
    """
    serializer_class = OfferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role_name = getattr(getattr(user, 'role', None), 'name', None)

        if role_name == settings.USER_ROLE_EMPLOYER:
            return Offer.objects.filter(employer=user).select_related(
                'meeting', 'candidate', 'employer'
            )
        else:
            # Candidates or any other role see received offers
            return Offer.objects.filter(candidate=user).select_related(
                'meeting', 'candidate', 'employer'
            )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Calculate stats for all offers of this user (not just this page)
        stats = {
            "total_sent": queryset.count(),
            "hired": queryset.filter(status='hired').count(),
            "accepted": queryset.filter(status='accepted').count(),
            "rejected": queryset.filter(status='rejected').count(),
            "declined": queryset.filter(status='declined').count(),
        }

        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            # Create a new dictionary with stats at the top
            paginated_data = response.data
            response.data = {
                "stats": stats,
                "count": paginated_data.get('count'),
                "total_pages": paginated_data.get('total_pages'),
                "current_page": paginated_data.get('current_page'),
                "next": paginated_data.get('next'),
                "previous": paginated_data.get('previous'),
                "results": paginated_data.get('results')
            }
            return response

        # Non-paginated fallback
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "stats": stats,
            "results": serializer.data
        })


class OfferDetailView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/vr-meet/offers/<id>/ — Retrieve offer detail
    PATCH /api/vr-meet/offers/<id>/ — Update offer fields (title, salary, etc.)
    Only the employer who created the offer can update it.
    """
    serializer_class = OfferSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'patch']  # No PUT, only PATCH

    def get_queryset(self):
        user = self.request.user
        return Offer.objects.filter(
            Q(employer=user) | Q(candidate=user)
        ).select_related('meeting', 'candidate', 'employer')

    def perform_update(self, serializer):
        """Only the employer who created the offer can update it."""
        offer = serializer.instance
        if offer.employer != self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only the employer who created this offer can update it.")
        logger.info(
            f"Employer {self.request.user.email} updating offer #{offer.id}"
        )
        serializer.save()


class RejectCandidateView(APIView):
    """
    POST /api/vr-meet/offers/reject/
    Reject a candidate by meeting_id.
    If an offer already exists for this meeting, update its status to 'rejected'.
    If no offer exists, create one with status='rejected'.
    Only the employer who hosted the meeting can reject.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = RejectCandidateSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        meeting_id = serializer.validated_data['meeting_id']
        user = request.user

        # Enforce employer role
        if not hasattr(user, 'role') or user.role.name != settings.USER_ROLE_EMPLOYER:
            return Response(
                {"detail": "Only employers can reject candidates."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get the meeting
        try:
            meeting = MeetingRoom.objects.get(pk=meeting_id, is_deleted=False)
        except MeetingRoom.DoesNotExist:
            return Response(
                {"detail": "Meeting not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Only the meeting's employer can reject
        if meeting.employer != user:
            return Response(
                {"detail": "Only the employer who hosted this meeting can reject."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Candidate must exist on the meeting
        if not meeting.candidate:
            return Response(
                {"detail": "No candidate linked to this meeting."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if an offer already exists for this meeting
        offer = Offer.objects.filter(
            meeting=meeting, candidate=meeting.candidate
        ).first()

        if offer:
            if offer.status == 'rejected':
                return Response(
                    {"detail": "Candidate is already rejected for this meeting."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Update existing offer to rejected
            offer.status = 'rejected'
            offer.save(update_fields=['status', 'updated_at'])
            logger.info(
                f"Employer {user.email} rejected candidate "
                f"{meeting.candidate.email} for meeting #{meeting.id} "
                f"(updated existing offer #{offer.id})"
            )
        else:
            # Create a new offer with rejected status
            offer = Offer.objects.create(
                meeting=meeting,
                candidate=meeting.candidate,
                employer=user,
                title=f"Rejected — {meeting.meeting_title}",
                status='rejected',
            )
            logger.info(
                f"Employer {user.email} rejected candidate "
                f"{meeting.candidate.email} for meeting #{meeting.id} "
                f"(created offer #{offer.id})"
            )

        # Return the offer data
        response_serializer = OfferSerializer(offer, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# -----------------------------------------------
#  CANDIDATE OFFER VIEWS (List + Accept/Decline)
# -----------------------------------------------

class CandidateOfferListView(generics.ListAPIView):
    """
    GET /api/vr-meet/offers/received/
    List all offer letters received by the candidate.
    Shows hired, accepted, and declined offers.
    """
    serializer_class = OfferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Offer.objects.filter(
            candidate=self.request.user,
            status__in=['hired', 'accepted', 'declined']
        ).select_related('meeting', 'candidate', 'employer')


class CandidateOfferRespondView(APIView):
    """
    POST /api/vr-meet/offers/<id>/respond/
    Candidate accepts or declines an offer.
    Body: {"action": "accept"} or {"action": "decline"}
    Sends email notification to the employer.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # Validate action
        action = request.data.get('action', '').lower()
        if action not in ('accept', 'decline'):
            return Response(
                {'detail': 'Invalid action. Must be "accept" or "decline".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the offer
        try:
            offer = Offer.objects.select_related(
                'meeting', 'candidate', 'employer'
            ).get(pk=pk, candidate=request.user)
        except Offer.DoesNotExist:
            return Response(
                {'detail': 'Offer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Only hired offers can be responded to
        if offer.status != 'hired':
            return Response(
                {'detail': f'Cannot respond to an offer with status "{offer.status}". '
                           f'Only offers with status "hired" can be accepted or declined.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update status
        new_status = 'accepted' if action == 'accept' else 'declined'
        offer.status = new_status
        offer.save(update_fields=['status', 'updated_at'])

        # Get names for email
        candidate_name = request.user.get_full_name() or request.user.email
        try:
            candidate_name = request.user.candidate_profile.full_name or candidate_name
        except Exception:
            pass

        position_title = offer.title
        company_name = 'The Company'
        try:
            employer_profile = offer.employer.employer_profile
            if employer_profile.company:
                company_name = employer_profile.company.company_name
        except Exception:
            pass

        # Send email notification to employer
        try:
            from utils.email_service import send_offer_response_email
            send_offer_response_email(
                employer_user=offer.employer,
                candidate_name=candidate_name,
                position_title=position_title,
                company_name=company_name,
                action=action,
            )
        except Exception as e:
            logger.error(f'Failed to send offer response email: {str(e)}')

        logger.info(
            f'Candidate {request.user.email} {new_status} offer #{offer.id} '
            f'({position_title})'
        )

        response_serializer = OfferSerializer(offer, context={'request': request})
        return Response({
            'status': 'success',
            'message': f'Offer {new_status} successfully.',
            'offer': response_serializer.data,
        }, status=status.HTTP_200_OK)