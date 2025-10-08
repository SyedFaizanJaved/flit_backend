from django.contrib import admin
from .models import JobApplication, ProjectApplication, Interview, ApplicationMessage, InterviewRequest


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    """
    Job Application admin
    """
    list_display = ('candidate', 'job', 'company', 'status', 'overall_match_score', 'is_shortlisted', 'is_rejected', 'applied_at')
    list_filter = ('status', 'is_shortlisted', 'is_rejected', 'is_withdrawn', 'is_archived', 'applied_at')
    search_fields = ('candidate__full_name', 'job__title', 'company__name')
    readonly_fields = ('applied_at', 'last_updated')
    
    fieldsets = (
        ('Application Information', {
            'fields': ('candidate', 'job', 'employer', 'company', 'coverLetter', 'resumeUrl', 'interestedInTemp')
        }),
        ('Status & Actions', {
            'fields': ('status', 'is_shortlisted', 'is_rejected', 'rejection_reason', 'is_withdrawn', 'is_archived')
        }),
        ('Matching Scores', {
            'fields': ('overall_match_score', 'skills_match_score', 'experience_match_score', 'education_match_score', 'location_match_score', 'salary_match_score'),
            'classes': ('collapse',)
        }),
        ('Offer Details', {
            'fields': ('offer_salary', 'offer_start_date', 'offer_terms'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('applied_at', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('candidate', 'job', 'employer', 'company')


@admin.register(ProjectApplication)
class ProjectApplicationAdmin(admin.ModelAdmin):
    """
    Project Application admin
    """
    list_display = ('candidate', 'project', 'company', 'status', 'overall_match_score', 'is_shortlisted', 'is_rejected', 'applied_at')
    list_filter = ('status', 'is_shortlisted', 'is_rejected', 'is_withdrawn', 'is_archived', 'applied_at')
    search_fields = ('candidate__full_name', 'project__title', 'company__name')
    readonly_fields = ('applied_at', 'last_updated')
    
    fieldsets = (
        ('Application Information', {
            'fields': ('candidate', 'project', 'employer', 'company', 'coverLetter')
        }),
        ('Status & Actions', {
            'fields': ('status', 'is_shortlisted', 'is_rejected', 'rejection_reason', 'is_withdrawn', 'is_archived')
        }),
        ('Matching Scores', {
            'fields': ('overall_match_score', 'skills_match_score', 'experience_match_score', 'education_match_score', 'portfolio_match_score', 'budget_match_score'),
            'classes': ('collapse',)
        }),
        ('Offer Details', {
            'fields': ('offer_amount', 'offer_start_date', 'offer_terms'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('applied_at', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('candidate', 'project', 'employer', 'company')


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    """
    Interview admin
    """
    list_display = ('job_application', 'project_application', 'interview_type', 'scheduled_at', 'status', 'rating', 'created_at')
    list_filter = ('interview_type', 'status', 'rating', 'created_at')
    search_fields = ('job_application__candidate__full_name', 'project_application__candidate__full_name', 'interviewer')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Interview Information', {
            'fields': ('job_application', 'project_application', 'interview_type', 'scheduled_at', 'duration_minutes', 'interviewer', 'notes', 'status')
        }),
        ('Feedback', {
            'fields': ('rating', 'feedback_comments', 'strengths', 'areas_for_improvement'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ApplicationMessage)
class ApplicationMessageAdmin(admin.ModelAdmin):
    """
    Application Message admin
    """
    list_display = ('job_application', 'project_application', 'sender', 'is_read', 'created_at')
    list_filter = ('sender', 'is_read', 'created_at')
    search_fields = ('job_application__candidate__full_name', 'project_application__candidate__full_name', 'message')
    readonly_fields = ('created_at',)


@admin.register(InterviewRequest)
class InterviewRequestAdmin(admin.ModelAdmin):
    """
    Interview Request admin
    """
    list_display = ('job_application', 'project_application', 'proposedTime', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('job_application__candidate__full_name', 'project_application__candidate__full_name')
    readonly_fields = ('created_at', 'updated_at')
