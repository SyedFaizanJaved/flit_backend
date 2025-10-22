from django.contrib import admin
from .models import ChatMessage, ChatRoom, ChatRoomMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """
    Chat Message admin
    """
    list_display = ('sender', 'recipient', 'messageType', 'is_read', 'is_deleted', 'created_at')
    list_filter = ('messageType', 'is_read', 'is_deleted', 'created_at')
    search_fields = ('sender__email', 'recipient__email', 'message')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Message Information', {
            'fields': ('sender', 'recipient', 'message', 'messageType')
        }),
        ('Status', {
            'fields': ('is_read', 'is_deleted')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('sender', 'recipient')


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    """
    Chat Room admin
    """
    list_display = ('name', 'room_type', 'is_private', 'is_active', 'created_by', 'created_at')
    list_filter = ('room_type', 'is_private', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'created_by__email')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('participants',)
    
    fieldsets = (
        ('Room Information', {
            'fields': ('name', 'description', 'room_type', 'created_by')
        }),
        ('Settings', {
            'fields': ('is_private', 'is_active')
        }),
        ('Participants', {
            'fields': ('participants',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


@admin.register(ChatRoomMessage)
class ChatRoomMessageAdmin(admin.ModelAdmin):
    """
    Chat Room Message admin
    """
    list_display = ('room', 'sender', 'message_type', 'is_deleted', 'created_at')
    list_filter = ('message_type', 'is_deleted', 'created_at')
    search_fields = ('room__name', 'sender__email', 'message')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Message Information', {
            'fields': ('room', 'sender', 'message', 'message_type', 'file_url')
        }),
        ('Status', {
            'fields': ('is_deleted',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('room', 'sender')
