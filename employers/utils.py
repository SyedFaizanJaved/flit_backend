from applications.models import JobApplication, ProjectApplication
from vr_meet.models import Offer

def get_employer_unread_counts(user):
    """
    Unified function to calculate unread counts for an employer.
    Used for dashboard and other views to keep frontend in sync.
    """
    unread_applications = JobApplication.objects.filter(
        employer=user, 
        is_read_by_employer=False
    ).count() + ProjectApplication.objects.filter(
        employer=user, 
        is_read_by_employer=False
    ).count()
    
    unread_responses = Offer.objects.filter(
        employer=user, 
        is_read_by_employer=False, 
        status__in=['accepted', 'declined']
    ).count()
    
    return {
        'applications': unread_applications,
        'hired_responses': unread_responses,
        'total_unread': unread_applications + unread_responses
    }
