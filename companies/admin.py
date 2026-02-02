from django.contrib import admin
from .models import Company, CompanyImage, CompanyMilestone

class CompanyImageInline(admin.TabularInline):
    model = CompanyImage
    extra = 1

class CompanyMilestoneInline(admin.TabularInline):
    model = CompanyMilestone
    extra = 1

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """
    Company admin
    """
    list_display = ('company_name', 'industry', 'size', 'created_at')
    list_filter = ('industry', 'size', 'created_at', 'work_mode')
    search_fields = ('company_name', 'industry', 'description')
    readonly_fields = ('created_at', 'updated_at', 'full_address')
    
    inlines = [CompanyImageInline, CompanyMilestoneInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company_name', 'description', 'industry', 'size', 'website', 'logo', 'location')
        }),
        ('Enhanced Branding', {
            'fields': ('founded_year', 'culture', 'benefits', 'social_links', 'work_mode'),
            'classes': ('collapse',)
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

@admin.register(CompanyImage)
class CompanyImageAdmin(admin.ModelAdmin):
    list_display = ('company', 'caption', 'order', 'created_at')
    list_filter = ('company', 'created_at')

@admin.register(CompanyMilestone)
class CompanyMilestoneAdmin(admin.ModelAdmin):
    list_display = ('company', 'year', 'title', 'created_at')
    list_filter = ('company', 'year')