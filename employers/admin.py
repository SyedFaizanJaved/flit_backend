from django.contrib import admin
from .models import Employer, EmployerPreference, EmployerCompliance


@admin.register(Employer)
class EmployerAdmin(admin.ModelAdmin):
    """
    Employer admin
    """
    list_display = ('full_name', 'company_name', 'created_at')
    list_filter = ('is_profile_public', 'created_at', 'company__industry')
    search_fields = ('first_name', 'last_name', 'company__company_name')
    readonly_fields = ('created_at', 'updated_at')
    
    def company_name(self, obj):
        return obj.company.company_name if obj.company else None
    company_name.short_description = 'Company'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'first_name', 'last_name', 'phone', 'position', 'department', 'profile_picture', 'bio')
        }),
        ('Company Information', {
            'fields': ('company',)
        }),
        ('Profile Status', {
            'fields': ('basic_info_completed', 'company_info_completed', 'is_profile_public')
        }),
        ('Statistics', {
            'fields': ('total_jobs_posted', 'total_projects_posted', 'total_applications_received', 'total_hires')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(EmployerPreference)
class EmployerPreferenceAdmin(admin.ModelAdmin):
    """
    Employer Preference admin
    """
    list_display = ('employer', 'auto_matching', 'skill_match_threshold', 'location_preference')
    list_filter = ('auto_matching', 'location_preference', 'email_notifications', 'push_notifications')
    search_fields = ('employer__full_name',)


@admin.register(EmployerCompliance)
class EmployerComplianceAdmin(admin.ModelAdmin):
    """
    Employer Compliance admin
    """
    list_display = ('employer', 'companySize', 'isFederalContractor', 'primaryState', 'autoScanEnabled', 'created_at')
    list_filter = ('isFederalContractor', 'autoScanEnabled', 'primaryState', 'created_at')
    search_fields = ('employer__full_name', 'primaryState')
    readonly_fields = ('created_at', 'updated_at')
