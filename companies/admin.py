# companies/admin.py
from django.contrib import admin
from .models import Company

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """
    Company admin
    """
    list_display = ('company_name', 'industry', 'size', 'is_verified', 'is_active', 'created_at')
    list_filter = ('industry', 'size', 'is_verified', 'is_active', 'is_completed', 'created_at')
    search_fields = ('company_name', 'industry', 'description')
    readonly_fields = ('created_at', 'updated_at', 'full_address')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company_name', 'description', 'industry', 'size', 'website', 'logo', 'location')
        }),
        ('Company Details', {
            'fields': ('values',),
            'classes': ('collapse',)
        }),
        ('Ownership & Status', {
            'fields': ('created_by', 'is_verified', 'is_active', 'is_completed')
        }),
        ('Statistics', {
            'fields': ('total_jobs', 'total_projects', 'total_hires', 'total_employees')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')