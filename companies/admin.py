from django.contrib import admin
from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """
    Company admin
    """
    list_display = ('company_name', 'industry', 'size', 'is_verified', 'is_active', 'created_at')
    list_filter = ('industry', 'size', 'is_verified', 'is_active', 'created_at')
    search_fields = ('company_name', 'industry', 'description', 'contact_email')
    readonly_fields = ('created_at', 'updated_at', 'full_address')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company_name', 'description', 'industry', 'size', 'founded', 'website', 'logo')
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone', 'address_street', 'address_city', 'address_state', 'address_country', 'address_zip_code', 'full_address')
        }),
        ('Social Media', {
            'fields': ('linkedin_url', 'twitter_url', 'facebook_url', 'instagram_url'),
            'classes': ('collapse',)
        }),
        ('Company Details', {
            'fields': ('mission', 'vision', 'values')
        }),
        ('Company Culture', {
            'fields': ('work_style', 'benefits', 'perks', 'work_life_balance')
        }),
        ('Ownership & Status', {
            'fields': ('created_by', 'is_verified', 'is_active')
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