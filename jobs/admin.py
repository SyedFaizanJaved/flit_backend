from django.contrib import admin
from .models import Job, JobSkill, JobLanguage


class JobSkillInline(admin.TabularInline):
    """
    Job Skill inline admin
    """
    model = JobSkill
    extra = 1


class JobLanguageInline(admin.TabularInline):
    """
    Job Language inline admin
    """
    model = JobLanguage
    extra = 1


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """
    Job admin
    """
    list_display = ('title', 'company', 'workStyle', 'category', 'experienceLevel', 'employmentType', 'status', 'created_at')
    list_filter = ('workStyle', 'category', 'experienceLevel', 'employmentType', 'status', 'is_urgent', 'created_at')
    search_fields = ('title', 'description', 'company__company_name', 'location')
    readonly_fields = ('created_at', 'updated_at', 'slug', 'views_count', 'applications_count', 'shortlisted_count', 'hired_count')
    inlines = [JobSkillInline, JobLanguageInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'company', 'employer')
        }),
        ('Job Details', {
            'fields': ('location', 'workStyle', 'category', 'skills', 'experienceLevel', 'employmentType', 'hasTemporaryOption', 'temporaryDuration')
        }),
        ('Salary Information', {
            'fields': ('salaryRangeMin', 'salaryRangeMax', 'salary_currency', 'salary_period', 'is_salary_negotiable')
        }),
        ('Benefits', {
            'fields': ('benefits',)
        }),
        ('Application Process', {
            'fields': ('applicationDeadline', 'start_date', 'is_urgent')
        }),
        ('Status & Matching', {
            'fields': ('status', 'skill_match_threshold', 'experience_weight', 'education_weight', 'location_weight')
        }),
        ('Tags & SEO', {
            'fields': ('tags', 'slug'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('views_count', 'applications_count', 'shortlisted_count', 'hired_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company', 'employer')


@admin.register(JobSkill)
class JobSkillAdmin(admin.ModelAdmin):
    """
    Job Skill admin
    """
    list_display = ('job', 'name', 'level', 'is_required')
    list_filter = ('level', 'is_required')
    search_fields = ('job__title', 'name')


@admin.register(JobLanguage)
class JobLanguageAdmin(admin.ModelAdmin):
    """
    Job Language admin
    """
    list_display = ('job', 'name', 'proficiency')
    list_filter = ('proficiency',)
    search_fields = ('job__title', 'name')
