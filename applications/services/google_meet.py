from datetime import datetime, timedelta
import os
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from django.conf import settings
from django.utils import timezone

# Google OAuth2 scopes required for Google Meet
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/meetings.space.created'
]

def get_google_meet_flow(request):
    """
    Initialize and return Google OAuth2 flow
    """
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    
    # Enable offline access so that you can refresh the access token without re-prompting for user consent
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    return flow

def create_google_meet(credentials_dict, interview):
    """
    Create a Google Meet meeting for an interview
    
    Args:
        credentials_dict (dict): Dictionary containing OAuth2 credentials
        interview (Interview): Interview instance
        
    Returns:
        dict: Meeting details including URL, ID, etc.
    """
    credentials = google.oauth2.credentials.Credentials(
        token=credentials_dict.get('token'),
        refresh_token=credentials_dict.get('refresh_token'),
        token_uri=credentials_dict.get('token_uri'),
        client_id=credentials_dict.get('client_id'),
        client_secret=credentials_dict.get('client_secret'),
        scopes=credentials_dict.get('scopes', [])
    )
    
    service = build('calendar', 'v3', credentials=credentials)
    
    # Calculate end time based on interview duration
    end_time = interview.scheduled_at + timedelta(minutes=interview.duration_minutes)
    
    # Get candidate email
    candidate_email = None
    if interview.job_application:
        candidate_email = interview.job_application.candidate.user.email
    elif interview.project_application:
        candidate_email = interview.project_application.candidate.user.email
    
    # Create event with Google Meet
    event = {
        'summary': f'Interview for {interview.job_application.job.title if interview.job_application else interview.project_application.project.title}',
        'description': f'Interview with {interview.interviewer}',
        'start': {
            'dateTime': interview.scheduled_at.isoformat(),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'UTC',
        },
        'conferenceData': {
            'createRequest': {
                'requestId': f"interview-{interview.id}-{timezone.now().timestamp()}",
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
            },
        },
        'attendees': [
            {'email': candidate_email, 'responseStatus': 'accepted'},
            {'email': interview.interviewer, 'organizer': True, 'responseStatus': 'accepted'},
        ],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                {'method': 'popup', 'minutes': 30},       # 30 minutes before
            ],
        },
    }

    try:
        event = service.events().insert(
            calendarId='primary',
            conferenceDataVersion=1,
            sendUpdates='all',
            body=event
        ).execute()
        
        return {
            'success': True,
            'meeting_url': event.get('hangoutLink'),
            'meeting_id': event.get('id'),
            'conference_id': event.get('conferenceData', {}).get('conferenceId'),
            'start_time': event['start'].get('dateTime'),
            'end_time': event['end'].get('dateTime'),
            'event_data': event
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
