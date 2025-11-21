from django.urls import path
from .views import *

urlpatterns = [
    path("create/", MeetingRoomCreateView.as_view(), name="meeting-room-create"),
    path("list/", MeetingRoomListView.as_view(), name="meeting-room-list"),
    path("detail/<str:room_code>/", MeetingRoomDetailView.as_view(), name="meeting-room-detail"),
]
