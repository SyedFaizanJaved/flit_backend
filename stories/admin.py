from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Story, Like, Comment, SavedItem


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'content_type', 'content_preview', 'is_active', 'created_at')
    list_filter = ('is_active', 'content_type', 'created_at')
    search_fields = ('user__email', 'content')
    readonly_fields = ('created_at', 'updated_at', 'content_preview')
    
    def content_preview(self, obj):
        return f"{obj.content[:50]}..." if obj.content and len(obj.content) > 50 else obj.content or ""
    content_preview.short_description = 'Content Preview'


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'get_liked_item', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'company_id', 'project_id', 'job_id')
    readonly_fields = ('created_at', 'get_liked_item')
    
    def get_liked_item(self, obj):
        if obj.company_id:
            return format_html('<a href="/admin/companies/company/{}/change/">Company ID: {}</a>', 
                             obj.company_id, obj.company_id)
        elif obj.project_id:
            return format_html('<a href="/admin/projects/project/{}/change/">Project ID: {}</a>', 
                             obj.project_id, obj.project_id)
        elif obj.job_id:
            return format_html('<a href="/admin/jobs/job/{}/change/">Job ID: {}</a>', 
                             obj.job_id, obj.job_id)
        return "Unknown"
    get_liked_item.short_description = 'Liked Item'
    get_liked_item.admin_order_field = 'company_id'  # For sorting


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'get_commented_item', 'content_preview', 'created_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__email', 'content', 'company_id', 'project_id', 'job_id')
    readonly_fields = ('created_at', 'updated_at', 'get_commented_item')
    
    def get_commented_item(self, obj):
        if obj.company_id:
            return format_html('<a href="/admin/companies/company/{}/change/">Company ID: {}</a>', 
                             obj.company_id, obj.company_id)
        elif obj.project_id:
            return format_html('<a href="/admin/projects/project/{}/change/">Project ID: {}</a>', 
                             obj.project_id, obj.project_id)
        elif obj.job_id:
            return format_html('<a href="/admin/jobs/job/{}/change/">Job ID: {}</a>', 
                             obj.job_id, obj.job_id)
        return "Unknown"
    get_commented_item.short_description = 'Commented On'
    get_commented_item.admin_order_field = 'company_id'  # For sorting
    
    def content_preview(self, obj):
        return f"{obj.content[:50]}..." if obj.content and len(obj.content) > 50 else obj.content or ""
    content_preview.short_description = 'Content Preview'


@admin.register(SavedItem)
class SavedItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'item_type', 'get_saved_item', 'created_at')
    list_filter = ('item_type', 'created_at')
    search_fields = ('user__email', 'company_id', 'project_id', 'job_id')
    readonly_fields = ('created_at', 'item_type', 'get_saved_item')
    list_select_related = ('user',)
    
    def get_saved_item(self, obj):
        if obj.company_id:
            return format_html('<a href="/admin/companies/company/{}/change/">Company ID: {}</a>', 
                             obj.company_id, obj.company_id)
        elif obj.project_id:
            return format_html('<a href="/admin/projects/project/{}/change/">Project ID: {}</a>', 
                             obj.project_id, obj.project_id)
        elif obj.job_id:
            return format_html('<a href="/admin/jobs/job/{}/change/">Job ID: {}</a>', 
                             obj.job_id, obj.job_id)
        return "Unknown"
    get_saved_item.short_description = 'Saved Item'
    get_saved_item.admin_order_field = 'company_id'  # For sorting
    
    def has_add_permission(self, request):
        return False  # Prevent adding saved items from admin
