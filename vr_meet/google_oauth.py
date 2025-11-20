from django.conf import settings
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_user_credentials():
    creds = None
    if os.path.exists(settings.TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(settings.TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("Token missing or invalid. Run gen_token again.")
    return creds
