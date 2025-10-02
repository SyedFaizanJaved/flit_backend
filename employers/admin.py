from django.contrib import admin
from .models import Employer, EmployerPreference, EmployerCompliance


@admin.register(Employer)
class EmployerAdmin(admin.ModelAdmin):
    """
    Employer admin
    """
    list_display = ('full_name', 'companyName', 'industry', 'location', 'created_at')
    list_filter = ('industry', 'is_profile_public', 'created_at')
    search_fields = ('first_name', 'last_name', 'companyName', 'industry', 'location')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'first_name', 'last_name', 'phone', 'position', 'department', 'profile_picture', 'bio')
        }),
        ('Company Information', {
            'fields': ('companyName', 'industry', 'description', 'website', 'location', 'size', 'values', 'logoImage')
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
