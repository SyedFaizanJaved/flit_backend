from django.urls import path
from .views import (
    MeetingRoomCreateView, MeetingRoomListView, MeetingRoomDetailView,
    MeetingRoomDeleteView, connect_google, google_callback, CandidateMeetingsView, check_google_connection
)

urlpatterns = [
    path("create/", MeetingRoomCreateView.as_view(), name="meeting-room-create"),
    path("list/", MeetingRoomListView.as_view(), name="meeting-room-list"),
    path("detail/<str:room_code>/", MeetingRoomDetailView.as_view(), name="meeting-room-detail"),
    path("delete/<int:pk>/", MeetingRoomDeleteView.as_view(), name="meeting-room-delete"),
    path("google/connect/", connect_google, name="google-connect"),
    path("google/callback/", google_callback, name="google-callback"),
    path("candidate/meetings/", CandidateMeetingsView.as_view(), name="candidate-meetings"),
    path("check-google-connection/", check_google_connection, name="check-google-connection"),
]
