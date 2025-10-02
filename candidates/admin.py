from django.contrib import admin
from .models import Candidate, WorkDNA, Reference, ReferenceRequest, Education, Experience, Achievement, MediaFile, CandidatePreference


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    """
    Candidate admin
    """
    list_display = ('full_name', 'title', 'location', 'is_available', 'work_style', 'created_at')
    list_filter = ('is_available', 'work_style', 'profile_visibility', 'created_at')
    search_fields = ('full_name', 'title', 'location', 'bio')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'full_name', 'title', 'bio', 'location', 'time_zone')
        }),
        ('Work Preferences', {
            'fields': ('is_remote', 'work_style', 'is_available', 'availability_type')
        }),
        ('Skills & Experience', {
            'fields': ('skills', 'superpowers', 'preferred_roles', 'passion_projects')
        }),
        ('Compensation', {
            'fields': ('min_salary', 'max_salary', 'salary_currency')
        }),
        ('Portfolio & Media', {
            'fields': ('portfolio_links', 'profile_image', 'resume_url', 'video_intro_url', 'intro_video_description')
        }),
        ('Privacy Settings', {
            'fields': ('profile_visibility', 'video_visibility', 'contact_visibility', 'salary_visibility')
        }),
        ('Profile Completion', {
            'fields': ('basic_info_completed', 'work_preferences_completed', 'skills_completed', 'portfolio_completed', 'privacy_completed')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(WorkDNA)
class WorkDNAAdmin(admin.ModelAdmin):
    """
    Work DNA admin
    """
    list_display = ('candidate', 'communication_style', 'working_style', 'problem_solving_approach', 'created_at')
    list_filter = ('communication_style', 'working_style', 'problem_solving_approach', 'team_dynamics', 'created_at')
    search_fields = ('candidate__full_name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    """
    Reference admin
    """
    list_display = ('candidate', 'reference_name', 'relationship_type', 'company_name', 'overall_rating', 'is_public', 'created_at')
    list_filter = ('relationship_type', 'is_public', 'overall_rating', 'created_at')
    search_fields = ('candidate__full_name', 'reference_name', 'company_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ReferenceRequest)
class ReferenceRequestAdmin(admin.ModelAdmin):
    """
    Reference Request admin
    """
    list_display = ('candidate', 'reference_name', 'reference_email', 'suggested_relationship', 'status', 'created_at')
    list_filter = ('status', 'suggested_relationship', 'created_at')
    search_fields = ('candidate__full_name', 'reference_name', 'reference_email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    """
    Education admin
    """
    list_display = ('candidate', 'institution', 'degree', 'field_of_study', 'start_date', 'end_date', 'is_current')
    list_filter = ('degree', 'is_current', 'start_date')
    search_fields = ('candidate__full_name', 'institution', 'field_of_study')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    """
    Experience admin
    """
    list_display = ('candidate', 'company_name', 'position', 'employment_type', 'start_date', 'end_date', 'is_current')
    list_filter = ('employment_type', 'is_current', 'start_date')
    search_fields = ('candidate__full_name', 'company_name', 'position')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    """
    Achievement admin
    """
    list_display = ('candidate', 'title', 'achievement_type', 'date_achieved', 'issuer')
    list_filter = ('achievement_type', 'date_achieved')
    search_fields = ('candidate__full_name', 'title', 'issuer')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    """
    Media File admin
    """
    list_display = ('candidate', 'title', 'media_type', 'is_public', 'created_at')
    list_filter = ('media_type', 'is_public', 'created_at')
    search_fields = ('candidate__full_name', 'title')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CandidatePreference)
class CandidatePreferenceAdmin(admin.ModelAdmin):
    """
    Candidate Preference admin
    """
    list_display = ('candidate', 'auto_matching', 'skill_match_threshold', 'profile_visibility', 'job_alert_frequency')
    list_filter = ('auto_matching', 'profile_visibility', 'job_alert_frequency')
    search_fields = ('candidate__full_name',)
    readonly_fields = ('created_at', 'updated_at')
