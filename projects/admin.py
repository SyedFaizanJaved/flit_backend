from django.contrib import admin
from .models import Project, ProjectSkill, ProjectMilestone


class ProjectSkillInline(admin.TabularInline):
    """
    Project Skill inline admin
    """
    model = ProjectSkill
    extra = 1


class ProjectMilestoneInline(admin.TabularInline):
    """
    Project Milestone inline admin
    """
    model = ProjectMilestone
    extra = 1


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """
    Project admin
    """
    list_display = ('title', 'company', 'category', 'complexity', 'paymentType', 'paymentAmount', 'status', 'created_at')
    list_filter = ('category', 'complexity', 'paymentType', 'work_style', 'collaboration', 'status', 'is_urgent', 'created_at')
    search_fields = ('title', 'description', 'company__company_name')
    readonly_fields = ('created_at', 'updated_at', 'slug', 'views_count', 'applications_count', 'shortlisted_count', 'hired_count')
    inlines = [ProjectSkillInline, ProjectMilestoneInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'company', 'employer')
        }),
        ('Project Details', {
            'fields': ('category', 'skills', 'paymentType', 'paymentAmount', 'estimatedHours', 'complexity')
        }),
        ('Budget & Timeline', {
            'fields': ('budget_min', 'budget_max', 'budget_currency', 'is_budget_negotiable', 'duration_days', 'start_date', 'deadline', 'is_timeline_flexible')
        }),
        ('Requirements', {
            'fields': ('experience_min_years', 'experience_max_years', 'education_level', 'education_fields', 'deliverables', 'tools', 'technologies')
        }),
        ('Work Arrangement', {
            'fields': ('work_style', 'collaboration')
        }),
        ('Application Process', {
            'fields': ('application_deadline', 'max_applicants', 'is_urgent')
        }),
        ('Status & Matching', {
            'fields': ('status', 'skill_match_threshold', 'experience_weight', 'education_weight', 'portfolio_weight')
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


@admin.register(ProjectSkill)
class ProjectSkillAdmin(admin.ModelAdmin):
    """
    Project Skill admin
    """
    list_display = ('project', 'name', 'level', 'is_required')
    list_filter = ('level', 'is_required')
    search_fields = ('project__title', 'name')


@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    """
    Project Milestone admin
    """
    list_display = ('project', 'title', 'due_date', 'payment_amount')
    list_filter = ('due_date',)
    search_fields = ('project__title', 'title')
    ordering = ('due_date',)
